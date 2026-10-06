"""
Log (mixin LogMixin): na tela e no arquivo da rodada (registro.py).

log() pode ser chamado de qualquer thread: as linhas vão pra uma caixa e a
tela é atualizada em lotes pela thread da interface. Cores por tipo de
linha; o log só rola sozinho se o usuário estiver no fim. Também: captura
de erros não tratados (com o local) e as configurações no início da rodada.
"""
import sys
import time
import threading
import tkinter as tk
from tkinter import messagebox

import registro
from versao import APP_TITULO


class LogMixin:
    """Log da janela (em lotes) e arquivo de log da rodada."""

    # ------------------------------------------------------------------
    # Caixa de linhas + descarga em lotes + arquivo da rodada
    # ------------------------------------------------------------------
    def log(self, message):
        """
        Adiciona mensagem ao log. Pode ser chamado de qualquer thread: a
        linha vai pro arquivo da rodada na hora e pra tela no próximo lote.
        """
        message = '' if message is None else str(message)
        try:
            message = self.registro._mascarar(message)     # chave nunca aparece, nem na tela
        except Exception:
            pass
        try:
            self.registro.linha(message)
            # Mensagem escrita DENTRO de um "except": o arquivo ganha o local
            # (arquivo:linha) e o traceback do erro, uma vez por erro.
            exc = sys.exc_info()[1]
            if exc is not None and id(exc) != getattr(self, '_ultimo_erro_registrado', None):
                self._ultimo_erro_registrado = id(exc)
                self.registro.erro(exc, message.strip()[:120])
        except Exception:
            pass
        with self._log_trava:
            self._log_caixa.append(message)
        # Na thread da janela durante trabalho longo (ex.: reler o acervo),
        # o laço do Tk não roda: descarrega aqui, no máximo ~10x/s.
        if threading.current_thread() is threading.main_thread():
            agora = time.time()
            if agora - getattr(self, '_log_ultimo_respiro', 0) >= 0.1 and hasattr(self, 'progress_text'):
                self._log_ultimo_respiro = agora
                try:
                    self._descarregar_log()
                    self.root.update_idletasks()
                except Exception:
                    pass

    def _reg(self, etiqueta, texto):
        """Linha só do arquivo de log (diagnóstico), com etiqueta pra busca."""
        try:
            self.registro.linha(texto, etiqueta)
        except Exception:
            pass

    @staticmethod
    def _tag_do_log(message):
        """Tag de cor da linha ('success', 'error', 'warning', 'divider' ou None)."""
        if any(s in message for s in ('✅', '✓', 'SUCESSO', 'sucesso')):
            return 'success'
        if any(s in message for s in ('❌', 'ERRO', 'Erro')):
            return 'error'
        if any(s in message for s in ('⚠', 'AVISO', 'Aviso')):
            return 'warning'
        if message.strip().startswith('='):
            return 'divider'
        return None

    def _iniciar_bomba_do_log(self):
        """Liga o ciclo de descarga (100ms) e o encerra ao destruir a janela."""
        if not self._log_bomba_ativa:
            self._log_bomba_ativa = True
            self._log_after = self.root.after(100, self._bomba_do_log)

            def _ao_fechar(ev):
                if ev.widget is self.root:
                    self._log_bomba_ativa = False
                    for nome in ('_log_after', '_after_pergunta_fila'):
                        try:
                            self.root.after_cancel(getattr(self, nome))
                        except Exception:
                            pass
                    try:
                        self.registro.linha('Janela fechada.', 'RODADA')
                    except Exception:
                        pass
            self.root.bind('<Destroy>', _ao_fechar, add='+')

    def _bomba_do_log(self):
        """Um ciclo: descarrega e se reagenda enquanto ativo."""
        if not self._log_bomba_ativa:
            return
        try:
            self._descarregar_log()
        finally:
            if self._log_bomba_ativa:
                try:
                    self._log_after = self.root.after(100, self._bomba_do_log)
                except Exception:
                    self._log_bomba_ativa = False

    def _descarregar_log(self):
        """Põe na tela as linhas acumuladas (thread da interface, ~10x/s)."""
        with self._log_trava:
            linhas, self._log_caixa = self._log_caixa, []
        if not linhas or not hasattr(self, 'progress_text'):
            if linhas:
                with self._log_trava:
                    self._log_caixa[:0] = linhas
            return
        t = self.progress_text
        try:
            # _log_seguindo é atualizado pela rolagem (ver _log_no_fim): só
            # rola sozinho se o usuário estiver no fim; senão conta as novas.
            no_fim = self._log_seguindo
        except Exception:
            no_fim = True
        t.config(state='normal')
        for m in linhas:
            tag = self._tag_do_log(m)
            if tag:
                t.insert(tk.END, m + "\n", tag)
            else:
                t.insert(tk.END, m + "\n")
        t.config(state='disabled')
        if no_fim:
            t.see(tk.END)
        else:
            self._log_novas += len(linhas)
            self.log_novas_btn.config(text=f"↓ {self._log_novas} linha(s) nova(s)")
            self.log_novas_btn.place(relx=1.0, rely=1.0, x=-24, y=-10, anchor='se')

    def _log_no_fim(self):
        """
        O fim do log está à vista? Usa dlineinfo da última linha (exato);
        a fração do yview é estimada e erra com linhas quebradas.
        """
        t = self.progress_text
        try:
            if not t.winfo_ismapped():
                return True
            return t.dlineinfo('end-1c') is not None
        except Exception:
            return True

    def _log_ir_para_o_fim(self):
        """Botão "↓ N linha(s) nova(s)": volta ao fim e retoma a rolagem automática."""
        self._log_novas = 0
        self._log_seguindo = True
        try:
            self.log_novas_btn.place_forget()
            self.progress_text.see(tk.END)
        except Exception:
            pass

    def _instalar_captura_de_erros(self):
        """
        Captura erros não tratados de callbacks do Tk e de threads e os grava
        no arquivo da rodada (arquivo:linha + traceback) e no log da tela.
        """
        reg = self.registro

        def _tk_erro(exc, val, tb):
            try:
                if val is not None and val.__traceback__ is None:
                    val = val.with_traceback(tb)
                onde = reg.erro(val, 'erro na janela')
                self.log(f"❌ Erro na janela: {str(val)[:150]} [{onde}]")
            except Exception:
                pass
        try:
            self.root.report_callback_exception = _tk_erro
        except Exception:
            pass
        anterior = getattr(threading, 'excepthook', None)

        def _thread_erro(args):
            try:
                onde = reg.erro(args.exc_value, f"erro na tarefa '{getattr(args.thread, 'name', '?')}'")
                self.log(f"❌ Erro em segundo plano: {str(args.exc_value)[:150]} [{onde}]")
            except Exception:
                pass
            if anterior:
                try:
                    anterior(args)
                except Exception:
                    pass
        try:
            threading.excepthook = _thread_erro
        except Exception:
            pass

    def _linhas_de_configuracao(self):
        """Resumo das configurações (registro.resumo_configuracoes), sem chaves."""
        nav = None
        try:
            escolhido = (self.config.get('settings.cookies_browser', '') or '').strip() or 'automático'
            achado = getattr(self.downloader, '_navegador_cookies', None)
            nav = f"{escolhido} ({achado})" if achado and achado != escolhido else escolhido
        except Exception:
            pass
        return registro.resumo_configuracoes(
            self.config, APP_TITULO,
            confianca_minima=self.AUTO_PROCESS_MIN_CONFIDENCE_PCT,
            navegador_cookies=nav)

    def _registrar_configuracoes(self, motivo='início'):
        """Configurações no log da tela e no arquivo - nunca as chaves."""
        try:
            self.registro.atualizar_segredos(self.config)
            self.registro.abrir(self.config.get_output_directory())
            linhas = self._linhas_de_configuracao()
            # tela: bloco legível; arquivo: as mesmas linhas com etiqueta
            with self._log_trava:
                self._log_caixa.append(f"⚙ Configurações ({motivo}):")
                self._log_caixa.extend(f"   {l}" for l in linhas)
            self._reg('CONFIG', f"Configurações ({motivo}):")
            for l in linhas:
                self._reg('CONFIG', '   ' + l)
            if self.config.has_api_key("groq"):
                self.log("🤖 Groq: usado só como sugestão (álbum que o título não traz, nome de faixa "
                         "difícil, ordem das faixas na descrição) - o Discogs e as durações confirmam; "
                         "não participa do corte.")
        except Exception as e:
            self.log(f"⚠ Não consegui listar as configurações: {str(e)[:80]}")

    def copy_log(self):
        """Copia todo o conteúdo do log pra área de transferência."""
        self._descarregar_log()
        content = self.progress_text.get(1.0, tk.END)
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.root.update()  # necessário no Tkinter para o clipboard "grudar" após a janela perder o foco
        messagebox.showinfo("Copiado", "Log copiado para a área de transferência!")

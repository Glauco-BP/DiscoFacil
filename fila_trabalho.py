"""
Fila única + trabalhador único.

Os botões "Enfileirar" (e "Baixar" em "Precisam de você") só PÕEM NA FILA
(fila_unica.py, gravada em disco). Um único trabalhador, numa thread,
consome a fila: disco único e playlist entram como próximos, pendências
depois, canal no fim. A pausa vale ENTRE itens - o álbum em andamento
sempre termina.

Sucesso é o padrão: um item só conta como falha quando vai pra "Precisam
de você" (pending_queue.add, envolvido em _ensure_acervo_and_queue) ou dá
erro. Também aqui: o painel da fila, a linha de situação, o botão de pausa
e a pergunta "retomar a fila guardada?" ao abrir.
"""
import time
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from ajustes import CutTuning
from fila_unica import FilaUnica
from ui_util import link_serve_para_o_modo, tipo_do_link
from util import onde_quebrou


LIMITE_DISCOGS_ESPERA_SEG = 600       # espera antes de tentar de novo um álbum que pegou o limite
LIMITE_DISCOGS_TENTATIVAS = 3         # por abertura do programa
LIMITE_DISCOGS_VIGIA_MS = 5 * 60 * 1000


class FilaMixin:
    """Fila única + trabalhador único: enfileirar, processar, pausar."""

    def start_processing(self):
        """Botão Enfileirar: põe o(s) link(s) do modo atual na fila (o canal é listado antes)."""
        if not self.config.get_output_directory():
            messagebox.showerror("Erro", "Configure a pasta de saída")
            return

        tipo_tela = self.process_type.get()

        if tipo_tela == "playlist":
            texto = self.playlist_text.get("1.0", tk.END).strip()
            if not texto:
                messagebox.showerror("Erro", "Insira pelo menos uma URL de playlist")
                return
            urls = [u.strip() for u in texto.splitlines() if u.strip()]
            n = 0
            ficam = []          # (linha, motivo) - continuam no campo, com aviso
            for u in urls:
                if not link_serve_para_o_modo(u, 'playlist'):
                    tipo = tipo_do_link(u)
                    ficam.append((u, f"parece {self.NOMES_LINK.get(tipo, 'outro link')}, não playlist"))
                    continue
                if self._enfileirar_e_iniciar('playlist', u, u):
                    n += 1
                else:
                    ficam.append((u, "não entrou na fila"))
            if n:
                self.log(f"➕ {n} playlist(s) na fila - assumem assim que o álbum "
                         f"atual terminar.")
            # o que entrou sai do campo (o link fica no log); o que não entrou fica, com aviso
            self.playlist_text.delete('1.0', tk.END)
            if ficam:
                self.playlist_text.insert('1.0', '\n'.join(u for u, _ in ficam))
                for u, motivo in ficam:
                    self.log(f"⚠ Ficou no campo ({motivo}): {u}")
                self.playlist_aviso.config(
                    text=f"⚠ {len(ficam)} linha(s) não entraram na fila e ficaram aqui: "
                         + "; ".join(m for _, m in ficam[:3]))
                self.playlist_aviso.pack(fill='x', padx=16, pady=(0, 12))
            else:
                self.playlist_aviso.pack_forget()
            return

        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Erro", "Insira uma URL")
            return

        if tipo_tela == "channel":
            if tipo_do_link(url) in ('video', 'playlist'):
                messagebox.showerror(
                    "Não é link de canal",
                    f"Esse link parece de {self.NOMES_LINK[tipo_do_link(url)]}, não de um canal.\n\n"
                    "Canal tem o formato youtube.com/@nome ou youtube.com/channel/...")
                return
            # Canal: listado uma vez, inteiro pro fim da fila; repetir só acrescenta
            # os vídeos novos. A trava evita duas varreduras por clique duplo.
            if getattr(self, '_listando_canal', False):
                self.log("⏳ Já estou listando esse canal - aguarde.")
                return
            self._listando_canal = True
            self._refresh_main_buttons_state()
            self.log(f"\n🔎 Listando vídeos do canal (uma vez só - depois fica na fila)...")

            def _listar():
                try:
                    videos = self.downloader.get_channel_videos(url, self.log)
                    if not videos:
                        self.log("❌ Nenhum vídeo encontrado no canal")
                        return
                    fila = self._garantir_fila()
                    if fila is None:
                        return
                    entradas = [{'url': v.get('url'), 'titulo': v.get('title', '')}
                                for v in videos if v.get('url')]
                    novos = fila.adicionar_varios('canal', entradas)
                    ja = len(entradas) - novos
                    eh_atualizacao = ja > 0

                    if eh_atualizacao and novos == 0:
                        self.log(f"🔄 Canal atualizado: nenhum vídeo novo desde a "
                                 f"última varredura ({ja} já conhecidos).")
                    elif eh_atualizacao:
                        self.log(f"🔄 Canal atualizado: {novos} vídeo(s) NOVO(S) no fim "
                                 f"da fila ({ja} já conhecidos - feitos, rejeitados ou "
                                 f"aguardando; nenhum será refeito).")
                    else:
                        self.log(f"➕ {novos} álbum(ns) do canal no FIM da fila.")

                    pend = fila.contagens()['pendente']
                    if pend:
                        self.log(f"   📋 {pend} item(ns) aguardando na fila.")
                    self.log(f"   💡 Pra buscar vídeos novos depois, é só clicar "
                             f"Enfileirar neste mesmo canal outra vez.")
                    self.root.after(0, self._iniciar_trabalhador)
                    self.root.after(0, lambda: self._limpar_campo_se(self.channel_entry, url))
                except Exception as e:
                    self.log(f"❌ Erro listando canal: {str(e)[:200]}")
                finally:
                    self._listando_canal = False
                    try:
                        self.root.after(0, self._refresh_main_buttons_state)
                    except Exception:
                        pass

            threading.Thread(target=_listar, daemon=True).start()
            return

        # Vídeo único: barra link de canal ou de playlist antes de enfileirar
        u = url.lower()
        if any(m in u for m in ('/@', '/channel/', '/c/', '/user/')):
            messagebox.showerror(
                "URL de canal",
                "Essa é a URL de um CANAL, não de um vídeo.\n\n"
                "Escolha o modo 'Canal Inteiro' pra enfileirar todos os "
                "álbuns dele.")
            return
        if 'list=' in u and 'watch?v=' not in u:
            messagebox.showerror(
                "URL de playlist",
                "Essa é a URL de uma PLAYLIST, não de um vídeo.\n\n"
                "Escolha o modo 'Playlist Completa'.")
            return
        if self._enfileirar_e_iniciar('disco_unico', url, url):
            self._limpar_campo_se(self.video_entry, url)

    def _limpar_campo_se(self, campo, url):
        """Apaga o campo se ele ainda tiver o link que acabou de entrar na fila."""
        try:
            if campo.get().strip() == url:
                campo.delete(0, tk.END)
                self._on_url_change()
        except Exception:
            pass

    def _enfileirar_e_iniciar(self, tipo, url, titulo='', **extras):
        """
        Põe na fila, garante o trabalhador rodando e mostra o painel da fila.
        Pedido explícito (disco, playlist, pendência) reabre item já feito -
        o usuário pode ter apagado a pasta pra refazer; se o álbum ainda
        estiver no disco, o índice do acervo pula sem baixar. Só o canal não
        reabre: relistar 3000 vídeos não pode refazer tudo.
        """
        fila = self._garantir_fila()
        if fila is None:
            messagebox.showerror("Erro", "Configure a pasta de saída")
            return None
        item = fila.adicionar(tipo, url, titulo,
                              reabrir_se_fechado=(tipo != 'canal'), **extras)
        if item is None:
            self.log(f"↩️  Já processado antes (está no histórico da fila): {titulo or url}")
            return None
        posicao = 'no fim da fila' if tipo == 'canal' else 'como próximo'
        self.log(f"➕ Na fila {posicao}: {titulo or url}")
        self._iniciar_trabalhador()
        try:
            self.root.after(0, lambda: self._mostrar_painel_fila(abrir_por_enfileiramento=True))
        except Exception:
            pass
        return item

    def _enfileirar_pendencias(self, itens):
        """
        Põe pendências na fila (tipo 'pendencia': depois de disco e playlist,
        antes do canal), numa só gravação. Devolve quantos entraram, ou None
        se não há fila.
        """
        fila = self._garantir_fila()
        if fila is None:
            messagebox.showerror("Erro", "Configure a pasta de saída primeiro")
            return None
        enfileirados = 0
        with fila.em_lote():
            for pendente in list(itens):
                novo = fila.adicionar(
                    'pendencia',
                    pendente.get('url', ''),
                    pendente.get('video_title', ''),
                    discogs_data=pendente.get('discogs_data'),
                    reabrir_se_fechado=True,
                    pendencia_item=pendente,
                )
                if novo:
                    enfileirados += 1
        if enfileirados:
            self.log(f"\n➕ {enfileirados} pendente(s) na fila - assumem assim que o "
                     f"álbum em processamento terminar.")
            self._iniciar_trabalhador()
            self._refresh_main_buttons_state()
        return enfileirados

    def _garantir_fila(self):
        """Abre a fila na primeira vez que alguém precisa dela."""
        if self.fila is None:
            saida = self.config.get_output_directory()
            if not saida:
                return None
            self.fila = FilaUnica(saida)
            recuperados = getattr(self.fila, '_interrompidos_ao_abrir', 0)
            if recuperados:
                self.log(f"↩️  {recuperados} item(ns) estavam em andamento quando o "
                         f"programa fechou - voltaram pra fila.")
            c = self.fila.contagens()
            if c['pendente']:
                self.log(f"📋 Fila retomada: {c['pendente']} pendente(s), "
                         f"{c['feito']} feito(s), {c['rejeitado']} rejeitado(s)")
        return self.fila

    def _iniciar_trabalhador(self):
        """Garante que existe UM trabalhador rodando - nunca dois."""
        if self.trabalhador_ativo:
            return
        fila = self._garantir_fila()
        if fila is None:
            messagebox.showerror("Erro", "Configure a pasta de saída")
            return
        if not fila.proximo():
            return
        self.trabalhador_ativo = True
        self.parar_trabalhador = False
        self._refresh_main_buttons_state()
        t = threading.Thread(target=self._trabalhador_da_fila, daemon=True)
        t.start()

    def _trabalhador_da_fila(self):
        """
        Único consumidor da fila (thread): processa item a item até esvaziar,
        respeitando pausa entre itens; marca feito/falha e limpa pendências.
        """
        try:
            # Na 1ª abertura o Deno (~40 MB) pode estar instalando; sem ele os
            # primeiros álbuns sairiam em 48kbps. Espera até 10 min.
            ger = getattr(self, 'dependencias', None)
            if ger is not None and not ger._pronto.is_set():
                self.log("⏳ Preparando os componentes de download antes de começar "
                         "(na primeira vez pode levar alguns minutos)...")
                if not ger.esperar_pronto(limite=600):
                    self.log("⚠️  O Deno ainda não terminou de instalar - começando assim "
                             "mesmo; as primeiras faixas podem sair em qualidade menor.")
            avisou_pausa = False
            while not self.parar_trabalhador:
                if self.paused:
                    if not avisou_pausa:
                        self.log("\n⏸️  Pausado - a fila continua guardada. "
                                 "Use 'Retomar fila' pra seguir.")
                        avisou_pausa = True
                    time.sleep(0.5)
                    continue
                avisou_pausa = False

                item = self.fila.proximo()
                if not item:
                    break

                self.fila.marcar_processando(item['id'])
                try:                        # interface só pela thread do Tk (root.after)
                    _t = item.get('titulo') or item.get('url', '')
                    self.root.after(0, lambda t=_t: self._atualizar_situacao(t))
                except Exception:
                    pass
                restam = self.fila.contagens()['pendente']
                self._ultimo_motivo = ''
                self._reg('DISCO', f"{item.get('tipo')} | {item.get('titulo') or ''} | {item.get('url', '')}")
                # um download antecipado de OUTRO item não serve mais
                try:
                    pd = getattr(self, 'pre_download', None)
                    if pd and pd.atual and pd.atual.get('url') != item.get('url'):
                        pd.descartar('a fila mudou de ordem')
                except Exception:
                    pass
                self.log(f"\n{'='*60}")
                self.log(f"📋 FILA [{item.get('tipo')}] - {restam} item(ns) aguardando")
                self.log(f"{'='*60}")

                try:
                    ok = self._processar_item_da_fila(item)
                except Exception as e:
                    self.log(f"\n❌ Erro processando item da fila: {str(e)[:200]} [{onde_quebrou(e)}]")
                    self._ultimo_motivo = f"erro: {str(e)[:120]} [{onde_quebrou(e)}]"
                    ok = False

                # antecipado deste item que não foi usado (pendência, já no acervo...)
                try:
                    if getattr(self, 'pre_download', None):
                        self.pre_download.descartar('não foi usado', url=item.get('url'))
                except Exception:
                    pass

                if ok:
                    self._reg('PRONTO', item.get('titulo') or item.get('url', ''))
                    self.fila.marcar_feito(item['id'])
                    # entrou no acervo: sai de "Precisam de você", venha de onde vier
                    self._tirar_das_pendencias(item.get('url'), 'concluído')
                else:
                    # talvez o YouTube tenha mudado: confere se há yt-dlp novo (no máx. a cada 30 min)
                    try:
                        if getattr(self, 'dependencias', None):
                            self.dependencias.verificar_apos_falha()
                    except Exception:
                        pass
                    estado = self.fila.marcar_falha(
                        item['id'], motivo='processamento falhou',
                        max_falhas=CutTuning.MAX_FALHAS_NA_FILA
                    )
                    self._reg('REJEITADO' if estado == 'rejeitado' else 'FILA',
                              f"{'a fila não tenta de novo' if estado == 'rejeitado' else 'não deu certo, volta pra fila'}"
                              f" | motivo: {getattr(self, '_ultimo_motivo', '') or 'ver as linhas acima'}"
                              f" | {item.get('titulo') or item.get('url', '')}")
                    if estado == 'rejeitado':
                        self.log(f"   🚫 Não será repetido. Fica no histórico da fila; "
                                 f"use 🔍 Buscar outra versão pra procurar outro upload.")
                        # só sai das pendências quem veio delas (um álbum de canal
                        # que falhou agora acabou de entrar lá)
                        if item.get('tipo') == 'pendencia':
                            self._tirar_das_pendencias(item.get('url'), 'rejeitado de vez')

            if not self.parar_trabalhador:
                c = self.fila.contagens()
                self.log(f"\n✅ Fila concluída - {c['feito']} feito(s), "
                         f"{c['rejeitado']} rejeitado(s)")
        finally:
            self.trabalhador_ativo = False
            try:
                self.root.after(0, self._refresh_main_buttons_state)
                self.root.after(0, self._atualizar_situacao)
            except Exception:
                pass

    def _tentar_de_novo_limite_discogs(self, reagendar=True):
        """
        Álbuns que foram pra "Precisam de você" só porque o Discogs não
        respondeu (limite de pedidos) voltam sozinhos pra fila depois de 10
        min, até 3 vezes por abertura. Voltam como 'nova_tentativa' (pipeline
        normal): se a nota for baixa, continuam pendentes, agora com o motivo
        certo. Só põe na fila; quem processa é o trabalhador quando estiver
        rodando. Devolve quantos entraram.
        """
        n = 0
        try:
            pq, fila = getattr(self, 'pending_queue', None), self._garantir_fila()
            if pq is not None and fila is not None:
                feitas = self.__dict__.setdefault('_retentativas_discogs', {})
                agora = time.time()
                for it in list(pq.items):
                    url = it.get('url')
                    if it.get('kind') != 'erro_discogs' or it.get('source_type') == 'playlist' or not url:
                        continue
                    vezes, ultima = feitas.get(url, (0, None))
                    if vezes >= LIMITE_DISCOGS_TENTATIVAS:
                        continue
                    if ultima is None:
                        try:
                            ultima = time.mktime(time.strptime(it.get('added_at', ''), '%Y-%m-%d %H:%M:%S'))
                        except Exception:
                            ultima = 0
                    if agora - ultima < LIMITE_DISCOGS_ESPERA_SEG:
                        continue
                    ja = fila.por_url(url)
                    if ja and ja.get('estado') in ('pendente', 'processando'):
                        continue
                    if fila.adicionar('nova_tentativa', url, it.get('video_title', ''), reabrir_se_fechado=True):
                        feitas[url] = (vezes + 1, agora)
                        n += 1
                if n:
                    self.log(f"🔁 {n} álbum(ns) que pegaram o limite do Discogs voltaram pra fila "
                             f"(tentativa automática)")
                    self._reg('FILA', f"{n} pendência(s) 'Discogs não respondeu' de volta à fila")
                    self.root.after(0, self._refresh_main_buttons_state)
        except Exception as e:
            self.log(f"   ⚠️  Nova tentativa automática do Discogs falhou: {str(e)[:80]} [{onde_quebrou(e)}]")
        if reagendar:
            try:
                self.root.after(LIMITE_DISCOGS_VIGIA_MS, self._tentar_de_novo_limite_discogs)
            except Exception:
                pass
        return n

    def _processar_item_da_fila(self, item) -> bool:
        """
        Despacha pelo TIPO DO ITEM (não pelo modo da tela): pendência de
        vídeo ou de playlist, playlist, ou um álbum (disco único e canal).
        Devolve se deu certo.
        """
        self._fila_item_ok = True       # vira False se o item for pra "Precisam de você"
        if item.get('tipo') == 'pendencia':
            guardado = item.get('pendencia_item')
            if not guardado:
                return False
            if guardado.get('source_type') == 'playlist':
                return bool(self._process_pending_playlist_item(guardado))
            return bool(self._process_pending_video_item(guardado))
        if item.get('tipo') == 'playlist':
            self.process_playlist(item['url'])
        else:
            self.process_single_video(item['url'])
        return bool(getattr(self, '_fila_item_ok', False))

    def _tirar_das_pendencias(self, url, motivo=''):
        """Remove da lista de pendências o item com esta URL, se houver."""
        if not url:
            return False
        try:
            fila_p = getattr(self, 'pending_queue', None)
            if not fila_p:
                return False
            alvos = [i for i in fila_p.items if i.get('url') == url]
            for a in alvos:
                fila_p.remove(a['id'])
            if alvos:
                titulo = (alvos[0].get('video_title') or url)[:50]
                self.log(f"   🧹 Saiu da lista de pendências ({motivo}): {titulo}")
                self._limpar_audios_pendentes()      # o áudio guardado pro ✂ Editar não serve mais
                return True
        except Exception as e:
            self.log(f"   ⚠️  Não consegui limpar as pendências: {str(e)[:80]}")
        return False

    def _antecipar_proximo(self, url_atual):
        """Começa a baixar o próximo da fila (só um), se for um disco único."""
        try:
            pd = getattr(self, 'pre_download', None)
            fila = getattr(self, 'fila', None)
            if (pd is None or fila is None or getattr(self, 'paused', False)
                    or getattr(self, 'parar_trabalhador', False)
                    or not getattr(self, 'trabalhador_ativo', False)):
                return False
            prox = fila.proximo()
            if prox and prox.get('url') != url_atual:
                return pd.iniciar(prox)
        except Exception as e:
            self.log(f"   ⚠️  Não deu pra antecipar o próximo download ({str(e)[:80]})")
        return False

    @staticmethod
    def _descrever_fonte(cand, n_candidatos=None):
        """Uma linha com a fonte escolhida, pro arquivo de log."""
        try:
            artistas = ', '.join(cand.get('artists') or []) or '?'
            durs = [t.get('duration', 0) for t in (cand.get('tracks') or [])]
            tem_dur = sum(1 for d in durs if isinstance(d, (int, float)) and d > 0)
            return (f"Discogs release {cand.get('release_id')} (master {cand.get('master_id')}) | "
                    f"{artistas} - {cand.get('title')} ({cand.get('year') or '?'}) | "
                    f"{len(durs)} faixas, {tem_dur} com duração | confiança {cand.get('confidence_pct', 0)}% "
                    f"| score {cand.get('score', 0):.0f}"
                    + (f" | {n_candidatos} edição(ões) candidatas" if n_candidatos else ''))
        except Exception as e:
            return f"Discogs (não consegui descrever: {e})"

    def toggle_pause(self):
        """Botão do rodapé: fila parada -> retoma; rodando -> pausa/continua (entre itens)."""
        if not self.trabalhador_ativo:
            self.paused = False
            self._update_pause_button_state()
            self._iniciar_trabalhador()
            return
        self.paused = not self.paused
        if self.paused:
            self.log("\n⏸️  Pausa solicitada - o processamento para entre um álbum e outro "
                     "(o álbum em andamento no momento não é interrompido).")
        else:
            self.log("\n▶️  Retomando processamento...")
        self._update_pause_button_state()

    def _update_pause_button_state(self):
        """Texto do botão: 'Pausar fila' / 'Retomar fila' / 'Retomar (N)' (fila parada com N aguardando)."""
        if self.trabalhador_ativo:
            self.pause_button.config(text="▶  Retomar fila" if self.paused else "⏸  Pausar fila", state='normal')
            return
        try:
            n = self.fila.contagens()['pendente'] if self.fila is not None else 0
        except Exception:
            n = 0
        if n:
            self.pause_button.config(text=f"▶  Retomar ({n})", state='normal')
        else:
            self.pause_button.config(text="▶  Retomar fila", state='disabled')

    def _atualizar_situacao(self, atual=None):
        """Linha de situação: o que está baixando agora, a posição na fila e o placar."""
        if not hasattr(self, 'status_line'):
            return
        try:
            if self.fila is None:
                self.status_line.config(text="Pronto para começar.")
                return
            c = self.fila.contagens()
            pend, feito, rej = c['pendente'], c['feito'], c['rejeitado']
            # 'processando' entra no total (sem ele dava "3 de 2")
            total = pend + feito + rej + c.get('processando', 0)

            if atual:
                nome = atual[:52] + ('…' if len(atual) > 52 else '')
                cabeca = f"▶ Baixando: {nome}"
            elif self.paused:
                cabeca = "⏸ Pausado"
            elif pend:
                cabeca = "Fila parada"
            else:
                cabeca = "Nada na fila"

            partes = []
            if total:
                pos = min(feito + rej + (1 if atual else 0), total)
                partes.append(f"{pos} de {total}")
            if feito:
                partes.append(f"{feito} pronto(s)")
            if rej:
                partes.append(f"{rej} recusado(s)")
            if pend:
                partes.append(f"{pend} na fila")

            self.status_line.config(text=cabeca + ("   ·   " + "  ·  ".join(partes) if partes else ""))
        except Exception:
            pass

    def _refresh_main_buttons_state(self):
        """
        Botões do rodapé conforme o estado. Enfileirar nunca trava (quem
        processa é um trabalhador só); só durante a listagem de um canal,
        pra não disparar duas varreduras.
        """
        self._update_pause_button_state()
        if hasattr(self, 'process_button'):
            if getattr(self, '_listando_canal', False):
                self.process_button.config(state='disabled', text="🔎  Listando canal…")
            else:
                modo = self.process_type.get() if hasattr(self, 'process_type') else 'video'
                rotulos = {'video': "➕  Enfileirar álbum",
                           'channel': "➕  Enfileirar canal inteiro",
                           'playlist': "➕  Enfileirar playlists"}
                self.process_button.config(state='normal',
                                            text=rotulos.get(modo, "▶  Processar"))

        if hasattr(self, 'pendentes_button'):
            try:
                n = len(self.pending_queue.items) if self.pending_queue else 0
                self.pendentes_button.config(
                    text=f"⏳  Precisam de você ({n})" if n else "⏳  Precisam de você")
            except Exception:
                pass

    def _mostrar_painel_fila(self, abrir_por_enfileiramento=False):
        """
        Painel da fila: abre pelo botão 'Fila' do cabeçalho e sozinho a cada
        item enfileirado. Marcar + "Tirar da lista" remove itens; mostra no
        máximo LIMITE itens (com ~3000, um widget por item congelaria a janela).
        """
        fila = self._garantir_fila()
        if fila is None:
            messagebox.showerror("Erro", "Configure a pasta de saída primeiro")
            return

        # uma janela só: fecha a anterior
        antiga = getattr(self, '_janela_fila', None)
        if antiga is not None:
            try:
                if antiga.winfo_exists():
                    antiga.destroy()
            except Exception:
                pass

        LIMITE = 60
        pendentes = sorted(
            fila.por_estado('pendente'),
            key=lambda i: (i.get('prioridade', 9), i.get('ordem', 0))
        )
        marcados = set()

        win = tk.Toplevel(self.root)
        self._janela_fila = win
        win.title("Fila de processamento")
        win.configure(bg=self.COLOR_BG)
        win.transient(self.root)
        win.resizable(True, True)
        win.geometry("620x560")
        win.bind('<Escape>', lambda e: win.destroy())

        topo = tk.Frame(win, bg=self.COLOR_BG, padx=20, pady=16)
        topo.pack(fill='x')
        tk.Label(topo, text="Fila de processamento", font=('Segoe UI', 14, 'bold'),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor='w')
        resumo = tk.Label(topo, text="", font=('Segoe UI', 9),
                          bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED)
        resumo.pack(anchor='w', pady=(2, 0))

        area = tk.Frame(win, bg=self.COLOR_BG, padx=20)
        area.pack(fill='both', expand=True)
        canvas = tk.Canvas(area, bg=self.COLOR_BG, highlightthickness=0)
        barra = ttk.Scrollbar(area, orient='vertical', command=canvas.yview)
        lista = tk.Frame(canvas, bg=self.COLOR_BG)
        lista.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.create_window((0, 0), window=lista, anchor='nw')
        canvas.configure(yscrollcommand=barra.set)
        canvas.pack(side='left', fill='both', expand=True)
        barra.pack(side='right', fill='y')

        rotulos = {}

        def _pintar(item_id):
            b = rotulos.get(item_id)
            if not b:
                return
            if item_id in marcados:
                b.config(text="☑", fg='#b91c1c')
            else:
                b.config(text="☐", fg=self.COLOR_TEXT_MUTED)

        def _alternar(item_id):
            if item_id in marcados:
                marcados.discard(item_id)
            else:
                marcados.add(item_id)
            _pintar(item_id)
            _atualizar_resumo()

        def _atualizar_resumo():
            c = fila.contagens()
            extra = f" · {len(marcados)} marcado(s)" if marcados else ""
            oculto = len(pendentes) - min(len(pendentes), LIMITE)
            cauda = f" (mostrando {LIMITE} dos {len(pendentes)})" if oculto > 0 else ""
            resumo.config(text=f"{c['pendente']} aguardando · {c['feito']} concluído(s) · "
                               f"{c['rejeitado']} rejeitado(s){extra}{cauda}")

        nomes_tipo = {'disco_unico': 'disco', 'playlist': 'playlist', 'pendencia': 'pendência',
                      'nova_tentativa': 'nova tentativa (Discogs)', 'canal': 'canal'}

        for it in pendentes[:LIMITE]:
            linha = tk.Frame(lista, bg=self.COLOR_CARD, bd=1, relief='solid')
            linha.pack(fill='x', pady=2, padx=(0, 6))
            marca = tk.Label(linha, text="☐", font=('Segoe UI', 12),
                             bg=self.COLOR_CARD, fg=self.COLOR_TEXT_MUTED,
                             cursor='hand2', padx=8)
            marca.pack(side='left')
            rotulos[it['id']] = marca
            titulo = (it.get('titulo') or it.get('url') or '?')[:64]
            corpo = tk.Frame(linha, bg=self.COLOR_CARD)
            corpo.pack(side='left', fill='x', expand=True, pady=5)
            tk.Label(corpo, text=titulo, font=('Segoe UI', 9), bg=self.COLOR_CARD,
                     fg=self.COLOR_TEXT, anchor='w').pack(anchor='w')
            tk.Label(corpo, text=nomes_tipo.get(it.get('tipo'), it.get('tipo', '')),
                     font=('Segoe UI', 8), bg=self.COLOR_CARD,
                     fg=self.COLOR_TEXT_MUTED, anchor='w').pack(anchor='w')
            for alvo in (marca, corpo, linha):
                alvo.bind('<Button-1>', lambda e, i=it['id']: _alternar(i))
            for filho in corpo.winfo_children():
                filho.bind('<Button-1>', lambda e, i=it['id']: _alternar(i))

        if not pendentes:
            tk.Label(lista, text="Nada aguardando na fila.", font=('Segoe UI', 10),
                     bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED).pack(pady=30)

        _atualizar_resumo()

        rodape = tk.Frame(win, bg=self.COLOR_BG, padx=20, pady=14)
        rodape.pack(fill='x')

        def _marcar_todos():
            if len(marcados) == len(rotulos):
                marcados.clear()
            else:
                marcados.update(rotulos.keys())
            for i in rotulos:
                _pintar(i)
            _atualizar_resumo()

        def _tirar_da_lista():
            if not marcados:
                return
            for i in list(marcados):
                fila.remover(i)
            self.log(f"🗑️  {len(marcados)} item(ns) tirados da fila.")
            win.destroy()
            self._mostrar_painel_fila()

        def _retomar():
            win.destroy()
            self.paused = False
            self._update_pause_button_state()
            if not self.trabalhador_ativo:
                self._iniciar_trabalhador()

        tk.Button(rodape, text="Marcar todos", command=_marcar_todos,
                  bg=self.COLOR_CARD, fg=self.COLOR_TEXT, bd=1, relief='solid',
                  font=('Segoe UI', 9), cursor='hand2', padx=12,
                  pady=6).pack(side='left')
        tk.Button(rodape, text="🗑️  Tirar da lista", command=_tirar_da_lista,
                  bg=self.COLOR_CARD, fg='#b91c1c', bd=1, relief='solid',
                  font=('Segoe UI', 9), cursor='hand2', padx=12,
                  pady=6).pack(side='left', padx=(8, 0))

        tk.Button(rodape, text="Voltar", command=win.destroy,
                  bg=self.COLOR_ACCENT, fg='white', bd=0,
                  font=('Segoe UI', 10, 'bold'), cursor='hand2', padx=22,
                  pady=7, activebackground=self.COLOR_ACCENT_DARK).pack(side='right')

        # "Retomar" só quando há o que retomar
        if pendentes and not self.trabalhador_ativo:
            tk.Button(rodape, text="▶  Retomar", command=_retomar,
                      bg=self.COLOR_CARD, fg=self.COLOR_ACCENT, bd=1, relief='solid',
                      font=('Segoe UI', 9, 'bold'), cursor='hand2', padx=14,
                      pady=6).pack(side='right', padx=(0, 8))

        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + 60
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        return win

    def _perguntar_sobre_fila_ao_abrir(self):
        """Ao abrir: "Há N álbuns na fila. [Retomar agora] [Depois]"."""
        try:
            if self.trabalhador_ativo:
                return
            fila = self._garantir_fila()
            if fila is None:
                return
            n = fila.contagens()['pendente']
            if not n:
                return
        except Exception:
            return
        win = tk.Toplevel(self.root)
        self._janela_pergunta_fila = win
        win.title("Fila guardada")
        win.configure(bg=self.COLOR_BG)
        win.transient(self.root)
        win.resizable(False, False)
        quadro = tk.Frame(win, bg=self.COLOR_BG, padx=24, pady=20)
        quadro.pack(fill='both', expand=True)
        tk.Label(quadro, text=f"Há {n} álbum(ns) na fila.", font=('Segoe UI', 12, 'bold'),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor='w')
        tk.Label(quadro, text="Retomar agora, ou deixar pra depois (o botão "
                              "\"Retomar fila\" continua ali).",
                 font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 wraplength=340, justify='left').pack(anchor='w', pady=(4, 16))
        botoes = tk.Frame(quadro, bg=self.COLOR_BG)
        botoes.pack(fill='x')

        def _agora():
            win.destroy()
            self.paused = False
            self.log("▶️  Retomando a fila guardada.")
            self._iniciar_trabalhador()

        def _depois():
            win.destroy()
        tk.Button(botoes, text="Depois", command=_depois, bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                  bd=1, relief='solid', font=('Segoe UI', 10), cursor='hand2',
                  padx=14, pady=6).pack(side='right')
        agora = tk.Button(botoes, text="▶  Retomar agora", command=_agora, bg=self.COLOR_ACCENT,
                          fg='white', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2',
                          activebackground=self.COLOR_ACCENT_DARK, padx=16, pady=7)
        agora.pack(side='right', padx=(0, 8))
        win.bind('<Escape>', lambda e: _depois())
        win.bind('<Return>', lambda e: _agora())
        win._agora, win._depois = _agora, _depois          # usados pelos testes
        try:
            win.update_idletasks()
            x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
            y = self.root.winfo_rooty() + 120
            win.geometry(f"+{max(0, x)}+{max(0, y)}")
            agora.focus_set()
        except Exception:
            pass
        return win

"""
Ligações da tela "Conferir cortes" (janela_editor.py) com o resto do programa:

- abrir_editor_pendencia(item): de "Precisam de você" (botão ✂ Editar). Usa o
  áudio guardado em .audios_pasta_pendencia (ou baixa); ao salvar, os cortes
  viram tempos exatos do item e ele vai pra fila.
- abrir_editor_pasta(pasta): disco já cortado (botão ✂ Editar disco da tela
  principal). Junta os MP3, abre a tela e, ao salvar, regrava a pasta.
- _limpar_audios_pendentes(): apaga os áudios guardados de discos que não
  estão mais em "Precisam de você".
"""
import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import edicao_cortes as EC
import saida
from versao import APP_VERSION

TAMANHO_MINIMO_AUDIO = 100_000
KINDS_CONFIRMADOS = ('falha_corte', 'falha_download')   # o disco é este; o que falhou foi o corte/download
PALPITE_MIN_PCT = 30                 # palpite do Discogs abaixo disso nem aparece como nome sugerido


class EditorMixin:
    """Mixin da janela principal (precisa de root, config, downloader, pending_queue, log, _reg)."""

    # ------------------------------------------------------------------ limpeza
    def _em_uso_pelo_editor(self):
        if not hasattr(self, '_arquivos_do_editor'):
            self._arquivos_do_editor = set()
        return self._arquivos_do_editor

    def _limpar_sobras_do_editor(self, base):
        try:
            return EC.limpar_sobras(base, self._em_uso_pelo_editor())
        except Exception:
            return 0

    def _limpar_audios_pendentes(self):
        try:
            base = self.config.get_output_directory()
            pq = getattr(self, 'pending_queue', None)
            if not base or pq is None:
                return 0
            return EC.limpar_audios(base, [i.get('url') for i in pq.items])
        except Exception:
            return 0

    # ------------------------------------------------------------------ espera
    def _preparar_em_segundo_plano(self, titulo, trabalho, pronto, ao_falhar=None):
        """Janelinha "Preparando..." enquanto `trabalho(avisar)` roda numa thread; depois `pronto(resultado)`."""
        jan = tk.Toplevel(self.root)
        jan.title(titulo)
        jan.configure(bg=self.COLOR_BG)
        jan.transient(self.root)
        jan.resizable(False, False)
        q = tk.Frame(jan, bg=self.COLOR_BG, padx=24, pady=18)
        q.pack()
        tk.Label(q, text=titulo, font=('Segoe UI', 11, 'bold'), bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor='w')
        etapa = tk.Label(q, text="Começando...", font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                         width=60, anchor='w', justify='left')
        etapa.pack(anchor='w', pady=(6, 0))
        self._janela_preparando = jan

        def prender(tentativas=10):
            # enquanto trabalha, as outras janelas esperam (ex.: o editor ao regravar); só dá depois de aparecer
            try:
                if jan.winfo_exists():
                    jan.grab_set()
            except Exception:
                if tentativas:
                    jan.after(50, lambda: prender(tentativas - 1))
        prender()

        # a thread não mexe na tela: deixa o recado aqui e a tela olha a cada 100 ms
        estado = {'texto': None, 'fim': False, 'resultado': None, 'erro': None}

        def avisar(texto):
            estado['texto'] = str(texto)[:90]

        def rodar():
            try:
                estado['resultado'] = trabalho(avisar)
            except Exception as e:
                estado['erro'] = e
            estado['fim'] = True

        def olhar():
            if estado['texto'] is not None:
                try:
                    etapa.config(text=estado['texto'])
                except Exception:
                    pass
                estado['texto'] = None
            if not estado['fim']:
                self.root.after(100, olhar)
                return
            try:
                jan.grab_release()
            except Exception:
                pass
            try:
                jan.destroy()
            except Exception:
                pass
            if estado['erro'] is not None:
                if ao_falhar:
                    try:
                        ao_falhar()
                    except Exception:
                        pass
                messagebox.showerror(titulo, f"Não deu: {estado['erro']}", parent=self.root)
            elif estado['resultado'] is not None:
                pronto(estado['resultado'])
        threading.Thread(target=rodar, daemon=True).start()
        self.root.after(100, olhar)
        return jan

    def _nova_janela_editor(self, edicao, ao_salvar, **k):
        from janela_editor import JanelaEditor
        tocador = getattr(self, '_tocador_teste', None)       # os testes trocam por um tocador falso
        self._janela_editor = JanelaEditor(self.root, edicao, ao_salvar, tocador=tocador, **k)
        return self._janela_editor

    # ------------------------------------------------------------------ pendência
    def _nomes_do_video(self, url, avisar):
        """
        Listas de nomes que o próprio vídeo traz: [(fonte, nomes, inicios ou None)] - capítulos,
        tracklist da descrição e, se nenhuma das duas tem tempos, a lista com tempos de um comentário.
        Sem rede (ou com erro), lista vazia: o editor abre do mesmo jeito.
        """
        from catalogo import inicios_de_texto, pistas_do_video
        from youtube_chapters_extractor import YouTubeChaptersExtractor
        fontes = []
        try:
            avisar("Lendo o vídeo (capítulos e descrição, pros nomes das músicas)...")
            info = self.downloader.get_video_info(url) or {}
        except Exception:
            info = {}
        dur = info.get('duration')
        try:
            caps = YouTubeChaptersExtractor.extract_from_video_info(info) if info else None
            if caps:
                fontes.append(('capítulos do vídeo', [c['title'] for c in caps], [c['start_time'] for c in caps]))
            desc = inicios_de_texto(info.get('description') or '', dur) if info else None
            if desc:
                fontes.append(('descrição do vídeo', [d['title'] for d in desc], [d['start_time'] for d in desc]))
            elif info:
                pistas = pistas_do_video(dict(info, chapters=[]))
                if pistas and len(pistas['tracks']) >= 3:
                    fontes.append(('descrição do vídeo', [t['title'] for t in pistas['tracks']], None))
        except Exception:
            pass
        if not any(f[2] for f in fontes) and info:
            try:
                avisar("Procurando uma lista com os tempos nos comentários do vídeo...")
                melhor = None
                for texto in self.downloader.comentarios(url) or []:
                    lista = inicios_de_texto(texto, dur)
                    if lista and len(lista) >= 3 and (melhor is None or len(lista) > len(melhor)):
                        melhor = lista
                if melhor:
                    fontes.append(('comentário do vídeo', [d['title'] for d in melhor],
                                   [d['start_time'] for d in melhor]))
            except Exception:
                pass
        return fontes

    def abrir_editor_pendencia(self, item):
        """
        ✂ Editar de "Precisam de você". Disco identificado (o corte é que falhou): nomes e durações do
        Discogs. Disco NÃO confirmado (confiança baixa, não achado, talvez outro disco): o palpite do
        Discogs não entra - pode ser outro disco (ex.: "Ruth Brown - Sotfly" com "Peaks Iration - Zen
        Garden"); o título vem do vídeo, os cortes e nomes vêm dos capítulos/descrição/comentário (se
        houver), e você confere artista, álbum e ano na própria tela.
        """
        base = self.config.get_output_directory()
        url = item.get('url')
        dados = item.get('discogs_data') or {}
        confirmado = item.get('kind') in KINDS_CONFIRMADOS and bool(dados.get('tracks'))
        if confirmado:
            titulo = f"{', '.join(dados.get('artists') or []) or item.get('title_artist', '')} - {dados.get('title')}"
            disco = None
        else:
            # artista/álbum do TÍTULO do vídeo (ou os que você digitou em Corrigir busca), nunca os do
            # palpite: num "talvez outro disco" os campos do item têm os nomes do disco errado
            vt = item.get('video_title') or ''
            if item.get('busca_corrigida') or not vt:
                art, alb = (item.get('title_artist') or '').strip(), (item.get('title_album') or '').strip()
                ano = str(item.get('year') or '') if item.get('busca_corrigida') else ''
            else:
                art, alb, ano = self._extract_artist(vt).strip(), self._extract_album(vt).strip(), self._extract_year(vt)
            titulo = f"{art} - {alb}" if art and alb else (vt or url)
            disco = {'artista': art, 'album': alb, 'ano': ano}

        def trabalho(avisar):
            audio = EC.audio_guardado(base, url)
            if audio is None:
                avisar("Baixando o áudio do vídeo (só desta vez: fica guardado)...")
                # uma pasta por download: o downloader pega o maior áudio novo da pasta
                temp = EC.pasta_audios(base) / EC.nome_unico(f"_baixando_{EC.id_do_video(url) or 'video'}_")
                temp.mkdir(parents=True, exist_ok=True)
                self._em_uso_pelo_editor().add(temp.name)
                try:
                    arq = saida.baixar_audio(self.downloader, url, temp, avisar, TAMANHO_MINIMO_AUDIO)
                    if not arq:
                        raise RuntimeError(getattr(self.downloader, 'last_error', None) or "o download falhou")
                    audio = EC.guardar_audio(base, url, arq)
                finally:
                    shutil.rmtree(temp, ignore_errors=True)
                    self._em_uso_pelo_editor().discard(temp.name)
            fontes = self._nomes_do_video(url, avisar)
            avisar("Medindo o áudio, os silêncios e as mudanças no som (alguns segundos)...")
            ed = EC.Edicao(audio, dados.get('tracks') if confirmado else [], titulo=titulo)
            ed.carregar(medidas=EC.arquivo_de_medidas(base, url))
            if not confirmado:
                com_tempos = next((f for f in fontes if f[2]), None)
                if com_tempos:
                    # sem Discogs confirmado: os cortes sugeridos vêm dos tempos do vídeo (ajustados à pausa)
                    ed.fonte_dos_cortes = com_tempos[0]
                    ed.nomes_fixos = list(com_tempos[1])
                    ed.marcas = ed.marcas_dos_tempos(com_tempos[2][1:])
                    ed.rotular()
            if confirmado:
                ed.adicionar_candidatos('Discogs', [t.get('title') for t in dados.get('tracks') or []])
            elif dados.get('tracks') and (item.get('confidence_pct') or 0) >= PALPITE_MIN_PCT:
                ed.adicionar_candidatos('palpite do Discogs', [t.get('title') for t in dados['tracks']])
            for fonte, nomes, _ in fontes:
                ed.adicionar_candidatos(fonte, nomes)
            return ed

        def ao_salvar(ed):
            extra = {'editor_sem_discogs': False}
            if disco is not None:
                d = janela_box['janela'].dados_do_disco() if janela_box.get('janela') else disco
                if not d['artista'] or not d['album']:
                    raise RuntimeError("escreva o artista e o álbum (no quadro amarelo, em cima da tabela)")
                extra = {'editor_sem_discogs': True, 'title_artist': d['artista'], 'title_album': d['album'],
                         'year': d['ano']}
            novo = self.pending_queue.informar_tempos(item['id'], ed.texto_tempos(), extra=extra)
            if not novo:
                raise RuntimeError("o disco não está mais em Precisam de você")
            self.log(f"✂️  Cortes conferidos por você ({len(ed.marcas) + 1} faixas): "
                     f"{(item.get('video_title') or '')[:60]} - na fila")
            self._reg('PENDENTE', f"cortes do editor | {len(ed.marcas) + 1} faixas | {url}")
            self._anotar_correcoes(ed, {'url': url, 'motivo': item.get('kind'), 'confirmado': confirmado})
            self._enfileirar_pendencias([novo])

        janela_box = {}

        def abrir(ed):
            je = self._nova_janela_editor(ed, ao_salvar, disco=disco)
            janela_box['janela'] = je
            return je

        return self._preparar_em_segundo_plano("Preparando o disco pra conferir", trabalho, abrir)

    def _anotar_correcoes(self, ed, extra):
        """Arquivo de correções do editor (pra ajustar os cortes automáticos) e o resumo no log."""
        try:
            if not self.config.get('settings.gravar_correcoes_editor', True):
                return
            base = self.config.get_output_directory()
            if not base:
                return
            EC.gravar_correcao(base, EC.registro_de_correcoes(ed, dict(extra, versao=APP_VERSION)))
            resumo = EC.resumo_correcoes(base)
            if resumo:
                self.log(f"   📊 Editor: {resumo}")
        except Exception:
            pass

    # ------------------------------------------------------------------ disco já cortado
    def abrir_editor_pasta(self, pasta=None):
        base = self.config.get_output_directory()
        if pasta is None:
            pasta = filedialog.askdirectory(title="Qual disco você quer editar? (a pasta com os MP3)",
                                            initialdir=base or None, parent=self.root)
            if not pasta:
                return None
        pasta = Path(pasta)
        if not EC.mp3s_da_pasta(pasta):
            messagebox.showinfo("Editar disco", "Essa pasta não tem arquivos MP3. Escolha a pasta de um disco "
                                                "(ex.: \"Artista - Álbum (Ano)\").", parent=self.root)
            return None
        base = base or str(pasta.parent)
        juntado = EC.pasta_audios(base) / f"{EC.nome_unico('_editando_')}.mp3"
        self._em_uso_pelo_editor().add(juntado.name)
        info_box, janela_box = {}, {}

        def soltar_juntado():
            Path(juntado).unlink(missing_ok=True)
            self._em_uso_pelo_editor().discard(juntado.name)

        def trabalho(avisar):
            avisar("Lendo as faixas da pasta...")
            info = EC.ler_pasta(pasta)
            info_box['info'] = info
            avisar(f"Juntando as {len(info['arquivos'])} faixas num arquivo só...")
            EC.juntar_pasta(pasta, juntado)
            ed = EC.Edicao(juntado, [], titulo=pasta.name, nomes_fixos=info['nomes'], origem='pasta',
                           duracoes_fixas=info['duracoes'])
            marcas, acc = [], 0.0
            for d in info['duracoes'][:-1]:
                acc += d
                marcas.append({'pos': acc, 'tipo': 'usuario'})
            avisar("Medindo o áudio, os silêncios e as mudanças no som (alguns segundos)...")
            ed.carregar(marcas=marcas)
            ed.adicionar_candidatos('nomes de antes', info['nomes'])
            # marcas de antes que caem num silêncio aparecem como "silêncio"
            for m in ed.marcas:
                if any(a - 1.0 <= m['pos'] <= b + 1.0 for a, b, _ in ed.silencios):
                    m['tipo'] = 'silencio'
            ed.rotular()                      # a sugestão inicial (pro arquivo de correções) já com os tipos
            return ed

        def ao_salvar(ed):
            if not ed.mudou:
                messagebox.showinfo("Editar disco", "Nada mudou: o disco ficou como estava.", parent=self.root)
                soltar_juntado()
                return None                   # fecha sem regravar (regravar à toa perderia qualidade)
            info = info_box['info']

            self._anotar_correcoes(ed, {'pasta': pasta.name})

            def regravar(avisar):
                avisar(f"Recortando e gravando as {len(ed.marcas) + 1} faixas...")
                r = EC.regravar_pasta(pasta, base, ed, info, log=self.log)
                self._reg('EDICAO', f"disco reeditado | {r['faixas']} faixas | {pasta} | antes em {r['antes']}")
                return r

            def pronto(r):
                je = janela_box.get('janela')
                if je is not None:
                    je.salvo()                # só agora a tela fecha: se der erro, as marcas continuam lá
                soltar_juntado()
                messagebox.showinfo("Editar disco", f"Pronto: {r['faixas']} faixas em\n{pasta}\n\nOs arquivos "
                                                    f"de antes estão em\n{r['antes']}", parent=self.root)
            self._preparar_em_segundo_plano("Gravando o disco editado", regravar, pronto)
            return False                      # a tela espera o fim da gravação

        def abrir(ed):
            je = self._nova_janela_editor(
                ed, ao_salvar, texto_salvar="💾  Salvar e regravar o disco",
                explicacao_salvar="Ao salvar, o disco é recortado nesses pontos e regravado na mesma pasta, com as "
                                  "mesmas tags e a capa; os arquivos de antes ficam guardados em "
                                  f"{EC.PASTA_AUDIOS}/{EC.PASTA_ANTES}.",
                ao_fechar=soltar_juntado)
            janela_box['janela'] = je
            return je

        return self._preparar_em_segundo_plano("Preparando o disco pra editar", trabalho, abrir,
                                               ao_falhar=soltar_juntado)

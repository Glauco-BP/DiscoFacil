"""
Janela principal do DiscoFácil.

FullTracksDownloaderGUI junta as partes (mixins), cada uma num arquivo:
  log_janela.LogMixin           log na tela + arquivo da rodada
  fila_trabalho.FilaMixin       fila única, trabalhador, pausa, painel da fila
  processo_album.AlbumMixin     modo álbum (um vídeo = um álbum)
  escolha_edicao.EdicaoMixin    qual edição encaixa no áudio
  processo_playlist.PlaylistMixin  modo playlist (um vídeo por faixa)
  identificacao_titulo.TituloMixin artista/álbum/ano do título
  janela_busca.BuscaMixin       "Buscar Playlists"
Aqui ficam o __init__ (as peças), o desenho da janela e a troca de modo.
"""
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from pathlib import Path

import dependencias
import registro
from acervo_index import AcervoIndex
from catalogo import Catalogo
from config import ConfigManager
from editor_acoes import EditorMixin
from downloader import YouTubeDownloader
from escolha_edicao import EdicaoMixin
from fila_trabalho import LIMITE_DISCOGS_VIGIA_MS, FilaMixin
from groq_ajuda import AjudaGroq
from identificacao_titulo import TituloMixin
from janela_busca import BuscaMixin
from janela_config import SettingsWindow
from janela_pendentes import JanelaPendentes
from log_janela import LogMixin
from metadata_manager import MetadataManager
from pending_queue import PendingQueue
from pre_download import PreDownload
from processo_album import AlbumMixin
from processo_playlist import PlaylistMixin
from ui_util import ICON_PATH, Cores, ICON_PNG_PATH, instalar_menu_contexto, link_serve_para_o_modo, make_help_button, tipo_do_link
from versao import APP_TITULO, APP_VERSION


class FullTracksDownloaderGUI(Cores, LogMixin, FilaMixin, AlbumMixin, EdicaoMixin, PlaylistMixin, TituloMixin, BuscaMixin,
                              EditorMixin):
    """Janela principal: monta as peças (config, downloader, catálogo, fila) e a interface."""

    # Nota de identificação (0-100) a partir da qual baixa sem perguntar;
    # padrão de fábrica, sobrescrito pelas Configurações (_carregar_confianca_minima).
    AUTO_PROCESS_MIN_CONFIDENCE_PCT = 80
    NOMES_MODO = {'video': 'Vídeo Único', 'channel': 'Canal Inteiro', 'playlist': 'Playlist Completa'}
    NOMES_LINK = {'video': 'um vídeo', 'channel': 'um canal', 'playlist': 'uma playlist'}

    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITULO)
        self.root.geometry("980x800")
        self.root.minsize(820, 650)
        self.root.resizable(True, True)
        self.root.configure(bg=self.COLOR_BG)

        # Log em lotes: qualquer thread põe na caixa; a interface atualiza ~10x/s (log_janela.py).
        self._log_caixa = []
        self._log_trava = threading.Lock()
        self._log_novas = 0
        self._log_bomba_ativa = False
        self.registro = registro.RegistroDaRodada(APP_VERSION)

        # .ico (barra de tarefas do Windows) e .png (Tk), independentes
        if ICON_PATH:
            try:
                self.root.iconbitmap(default=ICON_PATH)
            except Exception:
                pass
        if ICON_PNG_PATH:
            try:
                self._icon_photo_ref = tk.PhotoImage(file=ICON_PNG_PATH)
                self.root.iconphoto(True, self._icon_photo_ref)
            except Exception:
                pass

        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('TEntry', padding=6, font=('Segoe UI', 10))
        style.configure('TScrollbar', background=self.COLOR_BORDER)

        self.mode_cards = {}
        # Carregados em _ensure_acervo_and_queue, quando houver pasta de saída
        self.acervo_index = None        # dedupe por master/release do Discogs
        self.pending_queue = None       # "Precisam de você"

        self.config = ConfigManager()
        self.registro.atualizar_segredos(self.config)
        self.registro.abrir(self.config.get_output_directory())
        self._instalar_captura_de_erros()
        self.downloader = YouTubeDownloader(self.config)
        # Um download de cada vez (normal e antecipado, pre_download.py): o
        # yt-dlp e o contorno de cookies guardam estado no downloader.
        self._trava_download = threading.Lock()
        _baixar_original = self.downloader.download_audio

        def _baixar_com_trava(*a, **k):
            with self._trava_download:
                return _baixar_original(*a, **k)
        self.downloader.download_audio = _baixar_com_trava
        self.pre_download = PreDownload(self.downloader.download_audio, self.config.get_output_directory,
                                        log=self.log, reg=self._reg)
        self.groq = AjudaGroq(lambda: self.config.get("api_keys.groq", ""), log=self.log, reg=self._reg)
        self.metadata_manager = MetadataManager()
        # Discogs + MusicBrainz; o token é relido ao salvar as Configurações.
        self.catalogo = Catalogo({'discogs_token': self.config.get("api_keys.discogs_token", "")})

        self.paused = False             # pausa da fila (vale entre um item e outro)
        self.fila = None                # fila_unica.FilaUnica, aberta em _garantir_fila
        self.trabalhador_ativo = False
        self.parar_trabalhador = False
        self._fila_item_ok = False
        self._carregar_confianca_minima()

        # yt-dlp e Deno: estado no log e atualização automática
        self.dependencias = dependencias.GerenciadorDeDependencias(log=self.log)
        try:
            self.root.after(200, self._informar_e_verificar_dependencias)
        except Exception:
            pass
        # descobre o navegador dos cookies já na abertura (sem rede)
        try:
            self.downloader._log_cookies = self.log
            self.root.after(300, lambda: self.downloader._opcoes_de_cookies())
        except Exception:
            pass

        instalar_menu_contexto(self.root)
        self.create_widgets()
        self._largura_para_os_botoes()
        self._iniciar_bomba_do_log()
        self.check_initial_setup()
        # pendências que só pegaram o limite do Discogs voltam sozinhas pra fila
        try:
            self.root.after(LIMITE_DISCOGS_VIGIA_MS, self._tentar_de_novo_limite_discogs)
        except Exception:
            pass
        # pergunta sobre a fila guardada só depois que a janela aparece
        try:
            self._after_pergunta_fila = self.root.after(700, self._perguntar_sobre_fila_ao_abrir)
        except Exception:
            pass

    def _largura_para_os_botoes(self):
        """A linha de botões (com o Enfileirar) cabe inteira na largura mínima, com a fonte deste computador."""
        try:
            self.root.update_idletasks()
            precisa = self.action_frame.winfo_reqwidth() + 2 * 25 + 30      # margens do conteúdo e a barra de rolar
            self.root.minsize(max(820, precisa), 650)
            if precisa > 980:                                              # 980x800: o tamanho de abertura
                self.root.geometry(f"{precisa}x800")
        except Exception:
            pass

    def create_widgets(self):
        """Desenha a janela: cabeçalho, cards de modo, campos de link, botões, situação e log."""
        # ===================== CABEÇALHO =====================
        header = tk.Frame(self.root, bg=self.COLOR_ACCENT)
        header.pack(fill='x', side='top')

        # Os botões da direita são empacotados primeiro: se a janela ficar
        # estreita, quem encolhe é o subtítulo, não o botão "Configurações".
        header_right = tk.Frame(header, bg=self.COLOR_ACCENT)
        header_right.pack(side='right', padx=25)
        header_left = tk.Frame(header, bg=self.COLOR_ACCENT)
        header_left.pack(side='left', padx=25, pady=16)
        tk.Label(header_left, text="💿  DiscoFácil", font=('Segoe UI', 19, 'bold'),
                 bg=self.COLOR_ACCENT, fg='white').pack(anchor='w')
        tk.Label(header_left, text=f"Álbuns do YouTube separados em faixas  ·  versão {APP_VERSION}",
                 font=('Segoe UI', 9), bg=self.COLOR_ACCENT, fg='#C7D2FE').pack(anchor='w', pady=(3, 0))

        help_general_btn = make_help_button(
            header_right,
            title="Como funciona o DiscoFácil",
            text="Este programa baixa álbuns completos do YouTube e separa "
                 "automaticamente em faixas individuais, com nome, artista, "
                 "álbum, ano e capa preenchidos - tudo identificado através "
                 "do Discogs (a única fonte de metadados do programa).\n\n"
                 "MODOS DE USO:\n"
                 "• Vídeo Único - cole o link de um vídeo com o álbum completo\n"
                 "• Canal Inteiro - processa todos os vídeos de álbum de um canal\n"
                 "• Playlist Completa - cole uma ou mais playlists (uma por linha)\n\n"
                 "ANTES DE COMEÇAR:\n"
                 "Clique em 'Configurações' e cadastre a chave do Discogs "
                 "(obrigatória - sem ela o programa não identifica nenhum "
                 "álbum) - o campo lá tem seu próprio botão de ajuda (?) "
                 "explicando como conseguir a chave.\n\n"
                 "PRECISAM DE VOCÊ:\n"
                 "Quando o Discogs não encontra um álbum, encontra com "
                 "baixa confiança ou o corte não bate, ele vai para "
                 "'Precisam de você' (botão abaixo do link) em vez de ser "
                 "baixado errado - você decide ali se baixa mesmo assim, "
                 "corrige a busca, ouve e acerta os cortes (✂ Editar) ou descarta.\n\n"
                 "EDITAR DISCO:\n"
                 "Um disco já na pasta com um corte no lugar errado? "
                 "'✂ Editar disco': escolha a pasta, ouça, acerte os cortes "
                 "e salve. Os arquivos de antes ficam guardados.\n\n"
                 "Se algo der errado, o log embaixo mostra o que aconteceu - "
                 "mensagens em vermelho são erros, em laranja são avisos.",
            button_bg=self.COLOR_ACCENT,
            footer_note=f"Versão {APP_VERSION} · Elaborado por Glauco - Barra do Piraí - RJ",
        )
        # cores do cabeçalho (fundo roxo, texto branco)
        help_general_btn.configure(bg=self.COLOR_ACCENT, fg='white',
                                    activebackground=self.COLOR_ACCENT_DARK,
                                    highlightbackground='white', highlightthickness=1)
        help_general_btn.pack(side='left', padx=(0, 10))
        
        # Painel da fila acessível a qualquer momento (o botão de pausa fica
        # ocupado pausando enquanto a fila roda).
        self.fila_btn = tk.Button(header_right, text="📋  Fila", command=self._mostrar_painel_fila,
                                bg=self.COLOR_ACCENT, fg='white', bd=0, font=('Segoe UI', 10, 'bold'),
                                activebackground=self.COLOR_ACCENT_DARK, activeforeground='white',
                                cursor='hand2', padx=14, pady=8, relief='flat')
        self.fila_btn.pack(side='left', padx=(0, 10))

        search_btn = tk.Button(header_right, text="🔍  Buscar Playlists", command=self._show_playlist_search,
                                bg=self.COLOR_ACCENT, fg='white', bd=0, font=('Segoe UI', 10, 'bold'),
                                activebackground=self.COLOR_ACCENT_DARK, activeforeground='white',
                                cursor='hand2', padx=14, pady=8, relief='flat')
        search_btn.pack(side='left', padx=(0, 10))
        
        settings_btn = tk.Button(header_right, text="⚙  Configurações", command=self.open_settings,
                                  bg=self.COLOR_ACCENT, fg='white', bd=0, font=('Segoe UI', 10, 'bold'),
                                  activebackground=self.COLOR_ACCENT_DARK, activeforeground='white',
                                  cursor='hand2', padx=14, pady=8, relief='flat')
        settings_btn.pack(side='left')

        # ===================== CORPO =====================
        body = tk.Frame(self.root, bg=self.COLOR_BG)
        body.pack(fill='both', expand=True)

        content = tk.Frame(body, bg=self.COLOR_BG)
        content.pack(fill='both', expand=True, padx=25, pady=20)

        # --- Seleção de modo ---
        mode_title_row = tk.Frame(content, bg=self.COLOR_BG)
        mode_title_row.pack(anchor='w', fill='x', pady=(0, 10))
        tk.Label(mode_title_row, text="Modo de processamento", font=('Segoe UI', 12, 'bold'),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(side='left')
        make_help_button(
            mode_title_row, title="Modos de processamento",
            text="📹 Vídeo Único\nCole o link de UM vídeo do YouTube que tenha o "
                 "álbum completo (geralmente títulos com \"Full Album\").\n\n"
                 "📺 Canal Inteiro\nCola o link de um canal do YouTube e o programa "
                 "processa automaticamente todos os vídeos de álbum que encontrar "
                 "nele. Pode demorar bastante se o canal tiver muitos vídeos.\n\n"
                 "📋 Playlist Completa\nCole uma ou mais playlists do YouTube (uma "
                 "URL por linha) onde cada vídeo da playlist é uma faixa do álbum.",
        ).pack(side='left', padx=(6, 0))

        self.process_type = tk.StringVar(value="")

        cards_frame = tk.Frame(content, bg=self.COLOR_BG)
        cards_frame.pack(fill='x', pady=(0, 20))
        cards_frame.columnconfigure(0, weight=1)
        cards_frame.columnconfigure(1, weight=1)
        cards_frame.columnconfigure(2, weight=1)

        self._make_mode_card(cards_frame, 0, "📹", "Vídeo Único", "Baixa e separa um álbum", "video")
        self._make_mode_card(cards_frame, 1, "📺", "Canal Inteiro", "Todos os vídeos de um canal", "channel")
        self._make_mode_card(cards_frame, 2, "📋", "Playlist Completa", "Uma ou mais playlists", "playlist")

        # --- Card de URL (Vídeo Único e Canal; oculto no modo playlist) ---
        self.url_frame = tk.Frame(content, bg=self.COLOR_CARD, highlightthickness=1,
                                   highlightbackground=self.COLOR_BORDER)
        self.url_frame.columnconfigure(1, weight=1)
        # empacotado só por _on_type_change

        url_label_row = tk.Frame(self.url_frame, bg=self.COLOR_CARD)
        url_label_row.grid(row=0, column=0, sticky='w', padx=(16, 16), pady=16)
        self.url_label = tk.Label(url_label_row, text="URL do YouTube:", font=('Segoe UI', 10, 'bold'),
                                   bg=self.COLOR_CARD, fg=self.COLOR_TEXT)
        self.url_label.pack(side='left')
        make_help_button(
            url_label_row, title="URL do vídeo/canal",
            text="Cole aqui o link (URL) da página do YouTube.\n\n"
                 "• Vídeo Único: link de um vídeo específico "
                 "(ex: youtube.com/watch?v=...)\n\n"
                 "• Canal Inteiro: link da página principal do canal "
                 "(ex: youtube.com/@nomedocanal)",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))

        # Um campo por modo, pra trocar de modo não levar o texto junto;
        # self.url_entry (propriedade) é sempre o campo do modo atual.
        self.video_entry = ttk.Entry(self.url_frame, width=55, font=('Segoe UI', 10))
        self.channel_entry = ttk.Entry(self.url_frame, width=55, font=('Segoe UI', 10))
        for campo in (self.video_entry, self.channel_entry):
            campo._menu_limpar = True
            campo.bind('<Return>', lambda e: self.start_processing())
            campo.bind('<KeyRelease>', self._on_url_change)
            campo.bind('<<Paste>>', lambda e: self.root.after(10, self._on_url_change))
            campo.bind('<<Colado>>', lambda e: self.root.after(10, self._on_url_change))
        self.video_entry.grid(row=0, column=1, sticky='ew', padx=(0, 16), pady=16)

        # aviso quando o link colado não combina com o modo escolhido
        self.url_aviso = tk.Frame(self.url_frame, bg='#FFF7ED')
        self.url_aviso_txt = tk.Label(self.url_aviso, text='', font=('Segoe UI', 9),
                                      bg='#FFF7ED', fg=self.COLOR_WARNING, anchor='w',
                                      justify='left')
        self.url_aviso_txt.pack(side='left', padx=(12, 8), pady=6)
        self.url_aviso_btn = tk.Button(self.url_aviso, text='', bd=1, relief='solid',
                                       bg=self.COLOR_CARD, fg=self.COLOR_ACCENT,
                                       font=('Segoe UI', 9, 'bold'), cursor='hand2',
                                       padx=10, pady=2)
        self.url_aviso_btn.pack(side='left', pady=6)

        # --- Card de playlists (oculto, só aparece no modo playlist) ---
        self.playlist_frame = tk.Frame(content, bg=self.COLOR_CARD, highlightthickness=1,
                                        highlightbackground=self.COLOR_BORDER)

        playlist_label_row = tk.Frame(self.playlist_frame, bg=self.COLOR_CARD)
        playlist_label_row.pack(anchor='w', fill='x', padx=16, pady=(14, 6))
        tk.Label(playlist_label_row, text="URLs das playlists (uma por linha):", font=('Segoe UI', 10, 'bold'),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT).pack(side='left')
        make_help_button(
            playlist_label_row, title="URLs das playlists",
            text="Cole aqui o link de uma ou mais playlists do YouTube, "
                 "uma URL por linha (aperte Enter para pular de linha).\n\n"
                 "Cada playlist deve ter uma música por vídeo (não um vídeo "
                 "único com o álbum inteiro) - cada vídeo da playlist vira "
                 "uma faixa do álbum.\n\n"
                 "Pode colar várias playlists de uma vez; elas serão "
                 "processadas uma de cada vez, em sequência.",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))
        self.playlist_text = scrolledtext.ScrolledText(self.playlist_frame, height=4, wrap=tk.WORD,
                                                         font=('Segoe UI', 10), relief='flat',
                                                         highlightthickness=1,
                                                         highlightbackground=self.COLOR_BORDER)
        self.playlist_text.pack(fill='x', padx=16, pady=(0, 16))
        self.playlist_text._menu_limpar = True
        self.playlist_text.bind('<KeyRelease>', lambda e: self._on_url_change())
        self.playlist_text.bind('<<Paste>>', lambda e: self.root.after(10, self._on_url_change))
        self.playlist_text.bind('<<Colado>>', lambda e: self.root.after(10, self._on_url_change))
        self.playlist_aviso = tk.Label(self.playlist_frame, text='', font=('Segoe UI', 9),
                                       bg='#FFF7ED', fg=self.COLOR_WARNING, anchor='w',
                                       justify='left', padx=12, pady=6)

        # --- Linha de ações: utilitários à esquerda, Enfileirar à direita ---
        self.action_frame = tk.Frame(content, bg=self.COLOR_BG)
        
        utility_frame = tk.Frame(self.action_frame, bg=self.COLOR_BG)
        utility_frame.pack(side='left')
        self._make_footer_button(utility_frame, "📋  Copiar Log", self.copy_log)
        self._make_footer_button(utility_frame, "📁  Abrir Pasta", self.open_output_folder)
        # disco já cortado: escolher a pasta e conferir/acertar os cortes (editor_acoes.py)
        self._make_footer_button(utility_frame, "✂  Editar disco", self.abrir_editor_pasta)
        # Nasce "Retomar fila" desabilitado (nada rodando ainda);
        # _update_pause_button_state ajusta quando houver fila.
        self.pause_button = self._make_footer_button(utility_frame, "▶  Retomar fila", self.toggle_pause)
        try:
            self.pause_button.config(state='disabled')
        except Exception:
            pass
        # Fila = o que o programa faz sozinho; "Precisam de você" = o que
        # depende de uma decisão do usuário.
        self.pendentes_button = self._make_footer_button(
            utility_frame, "⏳  Precisam de você", self.open_pending_queue_manually)
        
        self.process_button = tk.Button(self.action_frame, text="▶  Processar", command=self.start_processing,
                                         bg=self.COLOR_ACCENT, fg='white', bd=0, font=('Segoe UI', 10, 'bold'),
                                         activebackground=self.COLOR_ACCENT_DARK, activeforeground='white',
                                         cursor='hand2', padx=22, pady=10, relief='flat')
        self.process_button.pack(side='right')

        # --- Área de progresso ---
        # Âncora: url_frame/playlist_frame/action_frame entram antes dela (pack(before=...)).
        self._progress_anchor = tk.Label(content, text="Progresso", font=('Segoe UI', 12, 'bold'),
                                          bg=self.COLOR_BG, fg=self.COLOR_TEXT)
        self._progress_anchor.pack(anchor='w', pady=(6, 4))

        # Linha de situação: o que está baixando, posição e placar da fila de
        # relance (com milhares de itens, o log sozinho não dá essa visão).
        self.status_line = tk.Label(
            content, text="Pronto para começar.", font=('Segoe UI', 10),
            bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED, anchor='w', justify='left')
        self.status_line.pack(anchor='w', fill='x', pady=(0, 8))

        log_card = tk.Frame(content, bg=self.COLOR_CARD, highlightthickness=1,
                             highlightbackground=self.COLOR_BORDER)
        log_card.pack(fill='both', expand=True, pady=(0, 15))

        self.progress_text = scrolledtext.ScrolledText(log_card, height=16, wrap=tk.WORD, state='disabled',
                                                         font=('Consolas', 9), bg='#FAFBFC',
                                                         fg=self.COLOR_TEXT, relief='flat', padx=12, pady=10,
                                                         borderwidth=0)
        self.progress_text.pack(fill='both', expand=True, padx=1, pady=1)

        # Rolagem do log: se o usuário rolou pra cima, o log para e aparece
        # este aviso; clicar (ou rolar até o fim) volta a acompanhar.
        self.log_novas_btn = tk.Button(log_card, text='', command=self._log_ir_para_o_fim,
                                       bg=self.COLOR_ACCENT, fg='white', bd=0,
                                       font=('Segoe UI', 9, 'bold'), cursor='hand2',
                                       activebackground=self.COLOR_ACCENT_DARK,
                                       activeforeground='white', padx=12, pady=4)
        # "Acompanhando o fim" só muda quando o USUÁRIO rola (mouse, barra,
        # teclado); redimensionar a janela não conta.
        self._log_seguindo = True

        def _usuario_rolou(_ev=None):
            def _conferir():
                self._log_seguindo = self._log_no_fim()
                if self._log_seguindo and self._log_novas:
                    self._log_novas = 0
                    self.log_novas_btn.place_forget()
            self.root.after(30, _conferir)
        for ev in ('<MouseWheel>', '<Button-4>', '<Button-5>', '<KeyRelease>'):
            self.progress_text.bind(ev, _usuario_rolou, add='+')
        for ev in ('<B1-Motion>', '<ButtonRelease-1>', '<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.progress_text.vbar.bind(ev, _usuario_rolou, add='+')
        self._log_usuario_rolou = _usuario_rolou

        def _redimensionou(_ev=None):
            if self._log_seguindo:
                self.progress_text.see(tk.END)
        self.progress_text.bind('<Configure>', _redimensionou, add='+')

        # tags de cor do log
        self.progress_text.tag_configure('success', foreground=self.COLOR_SUCCESS)
        self.progress_text.tag_configure('error', foreground=self.COLOR_ERROR)
        self.progress_text.tag_configure('warning', foreground=self.COLOR_WARNING)
        self.progress_text.tag_configure('divider', foreground='#94A3B8')

        # Abre já com um modo (o último usado, ou Vídeo Único), pra o campo
        # de link e a linha de botões aparecerem desde o início.
        self.action_frame.pack(fill='x', pady=(0, 15), before=self._progress_anchor)
        modo = 'video'
        try:
            salvo = self.config.get('settings.ultimo_modo', 'video')
            if salvo in ('video', 'channel', 'playlist'):
                modo = salvo
        except Exception:
            pass
        self._select_mode(modo, salvar=False)

    def _make_mode_card(self, parent, col, icon, title, subtitle, value):
        """Cria um card clicável de seleção de modo (Vídeo/Canal/Playlist)."""
        card = tk.Frame(parent, bg=self.COLOR_CARD, highlightthickness=2,
                         highlightbackground=self.COLOR_BORDER, cursor='hand2')
        card.grid(row=0, column=col, sticky='nsew', padx=8)

        icon_lbl = tk.Label(card, text=icon, font=('Segoe UI Emoji', 24), bg=self.COLOR_CARD, fg=self.COLOR_ACCENT)
        icon_lbl.pack(pady=(18, 6))
        title_lbl = tk.Label(card, text=title, font=('Segoe UI', 11, 'bold'), bg=self.COLOR_CARD, fg=self.COLOR_TEXT)
        title_lbl.pack()
        sub_lbl = tk.Label(card, text=subtitle, font=('Segoe UI', 9), bg=self.COLOR_CARD,
                            fg=self.COLOR_TEXT_MUTED, wraplength=170, justify='center')
        sub_lbl.pack(pady=(3, 18))

        widgets = [card, icon_lbl, title_lbl, sub_lbl]
        for w in widgets:
            w.bind('<Button-1>', lambda e, v=value: self._select_mode(v))

        self.mode_cards[value] = {'frame': card, 'widgets': widgets}
        return card

    def _select_mode(self, value, salvar=True):
        """Marca o card escolhido, troca o modo e (se salvar) lembra pra próxima abertura."""
        self.process_type.set(value)
        if salvar:
            try:
                if self.config.get('settings.ultimo_modo', None) != value:
                    self.config.set('settings.ultimo_modo', value)
            except Exception:
                pass
        for v, data in self.mode_cards.items():
            selected = (v == value)
            bg = self.COLOR_ACCENT_LIGHT if selected else self.COLOR_CARD
            border = self.COLOR_ACCENT if selected else self.COLOR_BORDER
            for w in data['widgets']:
                w.configure(bg=bg)
            data['frame'].configure(highlightbackground=border, highlightcolor=border)
        self._on_type_change()

    def _make_footer_button(self, parent, text, command):
        """Botão utilitário da linha de ações (empacotado à esquerda)."""
        btn = tk.Button(parent, text=text, command=command, bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                         font=('Segoe UI', 10), bd=1, relief='solid',
                         highlightbackground=self.COLOR_BORDER, activebackground=self.COLOR_ACCENT_LIGHT,
                         cursor='hand2', padx=14, pady=8)
        btn.pack(side=tk.LEFT, padx=5)
        return btn

    def check_initial_setup(self):
        """
        Na abertura: cabeçalho do arquivo da rodada, configurações no log,
        avisos (pasta de saída, chave do Discogs, fila guardada) e botões
        com as contagens certas.
        """
        try:
            self.registro.cabecalho([])
        except Exception:
            pass
        self._registrar_configuracoes('início')
        for linha in getattr(self.config, 'migracao', []) or []:
            self.log(f"🔧 config.json atualizado: {linha}")
            self._reg('CONFIG', f"config.json atualizado: {linha}")
        if self.registro.caminho:
            self.log(f"📝 Log desta rodada (anexe este arquivo se algo der errado): {self.registro.caminho}")
        output_dir = self.config.get_output_directory()
        if not output_dir:
            self.log("⚠ Configure a pasta de saída nas Configurações")
        else:
            self._ensure_acervo_and_queue()
        
        apis = []
        if self.config.get("api_keys.discogs_token", ""):
            apis.append("Discogs")
        else:
            self.log("⚠ Chave do Discogs não configurada - é a única fonte de identificação usada pelo programa")
        
        if apis:
            # avisa que há fila guardada (senão a janela parece parada sem motivo)
            try:
                _f = self._garantir_fila()
                if _f is not None:
                    _c = _f.contagens()
                    if _c['pendente']:
                        self.log(f"📋 Há {_c['pendente']} álbum(ns) aguardando na fila. "
                                 f"Clique em 'Fila' pra retomar de onde parou.")
            except Exception:
                pass
        else:
            self.log("ℹ Nenhuma API configurada")
        # contagens nos botões ("Retomar (N)", "Precisam de você (N)") desde a abertura
        try:
            self._refresh_main_buttons_state()
        except Exception:
            pass

    def _ensure_acervo_and_queue(self):
        """
        Garante índice do acervo (dedupe por master_id) e fila de pendentes
        da pasta de saída ATUAL (pode mudar nas Configurações). O índice é
        reconstruído do disco uma vez por sessão/pasta (pastas apagadas ou
        copiadas à mão); depois, os álbuns novos entram por add().
        Devolve False se não há pasta de saída.
        """
        output_dir = self.config.get_output_directory()
        if not output_dir:
            return False
        
        if self.acervo_index is None or str(self.acervo_index.output_dir) != str(Path(output_dir)):
            self.acervo_index = AcervoIndex(output_dir, metadata_manager=self.metadata_manager)
            self.acervo_index.load_or_rebuild(log_func=self.log, force_rebuild=True)
        
        if self.pending_queue is None or str(self.pending_queue.output_dir) != str(Path(output_dir)):
            self.pending_queue = PendingQueue(output_dir)
            self._limpar_audios_pendentes()      # áudios de discos que já saíram da lista
            self._limpar_sobras_do_editor(output_dir)   # trabalhos do ✂ Editar interrompidos

            # Ir pra pendências = falha do item: envolver add() marca a falha
            # pro trabalhador em qualquer caminho, sem lembrar em cada um.
            if not getattr(self.pending_queue, '_envolvido', False):
                _add_original = self.pending_queue.add
                def _add_marcando_falha(*a, **k):
                    self._fila_item_ok = False
                    try:
                        motivo = k.get('reason') or ''
                        self._ultimo_motivo = motivo
                        self._reg('PENDENTE', f"{k.get('kind', '?')} | confiança {k.get('confidence_pct', 0)}% | "
                                              f"{motivo} | {k.get('video_title') or k.get('url', '')}")
                    except Exception:
                        pass
                    return _add_original(*a, **k)
                self.pending_queue.add = _add_marcando_falha
                self.pending_queue._envolvido = True
        
        return True

    @property
    def url_entry(self):
        """O campo de link do modo atual (Vídeo Único ou Canal)."""
        if self.process_type.get() == 'channel':
            return self.channel_entry
        return self.video_entry

    def _on_url_change(self, event=None):
        """
        Confere o link colado contra o modo escolhido e avisa (sem bloquear)
        se não combinar, com um botão pra trocar de modo levando o link.
        """
        modo = self.process_type.get()
        try:
            if modo == 'playlist':
                linhas = [l.strip() for l in self.playlist_text.get('1.0', tk.END).splitlines() if l.strip()]
                ruins = [l for l in linhas if not link_serve_para_o_modo(l, 'playlist')]
                if ruins:
                    tipos = {tipo_do_link(l) for l in ruins}
                    qual = ' / '.join(self.NOMES_LINK.get(t, '?') for t in tipos if t)
                    self.playlist_aviso.config(
                        text=f"⚠ {len(ruins)} linha(s) não parecem playlist ({qual}). "
                             f"Playlist tem \"list=\" no link.")
                    self.playlist_aviso.pack(fill='x', padx=16, pady=(0, 12))
                else:
                    self.playlist_aviso.pack_forget()
                return
            url = self.url_entry.get().strip()
            tipo = tipo_do_link(url)
            if url and tipo and not link_serve_para_o_modo(url, modo):
                self.url_aviso_txt.config(
                    text=f"⚠ Este link parece de {self.NOMES_LINK[tipo]}, mas o modo "
                         f"escolhido é {self.NOMES_MODO.get(modo, modo)}.")
                self.url_aviso_btn.config(text=f"Usar {self.NOMES_MODO[tipo]}",
                                          command=lambda t=tipo, u=url: self._trocar_modo_levando(t, u))
                self.url_aviso.grid(row=1, column=0, columnspan=2, sticky='ew', padx=16, pady=(0, 12))
            else:
                self.url_aviso.grid_remove()
                if url and len(url) > 10:
                    self.process_button.focus_set()
        except Exception:
            pass

    def _trocar_modo_levando(self, novo_modo, url):
        """Botão do aviso: troca de modo e leva o link pro campo certo."""
        atual = self.url_entry
        try:
            if atual.get().strip() == url:
                atual.delete(0, tk.END)
        except Exception:
            pass
        self._select_mode(novo_modo)
        if novo_modo == 'playlist':
            texto = self.playlist_text.get('1.0', tk.END).strip()
            self.playlist_text.insert(tk.END, ('\n' if texto else '') + url)
        else:
            self.url_entry.delete(0, tk.END)
            self.url_entry.insert(0, url)
        self._on_url_change()

    def _on_type_change(self):
        """Mostra o campo do modo atual (link único ou lista de playlists) e reconfere o link."""
        mode = self.process_type.get()
        
        if mode:  # Se algum modo foi escolhido
            if mode in ("video", "channel"):
                self.url_label.config(text="URL do Vídeo:" if mode == "video" else "URL do Canal:")
                mostrar, esconder = ((self.video_entry, self.channel_entry) if mode == "video"
                                     else (self.channel_entry, self.video_entry))
                esconder.grid_remove()
                mostrar.grid(row=0, column=1, sticky='ew', padx=(0, 16), pady=16)
                self.url_frame.pack(fill='x', pady=(0, 15), before=self._progress_anchor)
                self.playlist_frame.pack_forget()
            elif mode == "playlist":
                # só o campo de várias URLs; o de link único fica oculto
                self.url_frame.pack_forget()
                self.playlist_frame.pack(fill='x', pady=(0, 15), before=self._progress_anchor)
            
            # a linha de botões fica sempre visível; só o campo muda
            self.action_frame.pack(fill='x', pady=(0, 15), before=self._progress_anchor)
            self._refresh_main_buttons_state()
            self._on_url_change()
        else:
            self.url_frame.pack_forget()
            self.playlist_frame.pack_forget()

    def open_pending_queue_manually(self):
        """Botão "Precisam de você": abre a janela de pendências (ou avisa que está vazia)."""
        self._ensure_acervo_and_queue()
        if not self.pending_queue or (len(self.pending_queue) == 0 and not self.pending_queue.descartados):
            messagebox.showinfo("Precisam de você", "Nenhum álbum precisa de você no momento.")
            return
        self._show_pending_queue()

    def _informar_e_verificar_dependencias(self):
        """
        Uma linha no log com o estado do yt-dlp e do Deno (sem Deno o áudio
        sai em 48kbps sem outro aviso) e a verificação em fundo.
        """
        try:
            versao = dependencias.versao_ytdlp_em_uso() or '?'
            origem = "atualizado" if dependencias.YTDLP_LOCAL_ATIVO else "do programa"
            deno = dependencias.localizar_deno()
            self.log(f"🔧 Componente do YouTube: yt-dlp {versao} ({origem}) · "
                     f"Deno: {'ok' if deno else 'ausente - vou instalar'}")
        except Exception:
            pass
        self.dependencias.verificar_ao_abrir()

    def _carregar_confianca_minima(self):
        """
        Lê das Configurações a confiança mínima pra baixar sem perguntar.
        Com 0% nada vai pra pendências por falta de confiança: baixa com o
        melhor palpite do Discogs.
        """
        try:
            valor = self.config.get("settings.auto_process_min_confidence_pct", None)
            if valor is None:
                return
            valor = int(valor)
            if 0 <= valor <= 100:
                self.AUTO_PROCESS_MIN_CONFIDENCE_PCT = valor
        except Exception:
            pass

    def _show_pending_queue(self):
        """
        Janela "Precisam de você" (janela_pendentes.py): tabela com
        seleção normal, filtro por motivo, busca, ações em lote e Descartados.
        Uma janela só: se já estiver aberta, só vem pra frente e atualiza.
        """
        if not self.pending_queue:
            return
        atual = getattr(self, '_janela_pendentes', None)
        if atual is not None:
            try:
                if atual.win.winfo_exists():
                    atual.recarregar()
                    atual.win.deiconify()
                    atual.win.lift()
                    return atual
            except Exception:
                pass
        if len(self.pending_queue) == 0 and not self.pending_queue.descartados:
            return
        self._janela_pendentes = JanelaPendentes(self)
        return self._janela_pendentes

    def open_settings(self):
        """Abre a janela de Configurações."""
        SettingsWindow(self.root, self.config, self)

    def open_output_folder(self):
        """Abre a pasta de saída no gerenciador de arquivos do sistema."""
        import os
        import subprocess
        import platform
        
        output_dir = self.config.get_output_directory()
        if output_dir and Path(output_dir).exists():
            if platform.system() == 'Windows':
                os.startfile(output_dir)
            elif platform.system() == 'Darwin':
                subprocess.Popen(['open', output_dir])
            else:
                subprocess.Popen(['xdg-open', output_dir])
        else:
            messagebox.showwarning("Aviso", "Pasta não existe")

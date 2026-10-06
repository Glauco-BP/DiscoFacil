"""
Janela de Configurações: pasta de saída, chaves (Discogs, Groq), bitrate
mínimo, navegador dos cookies e confiança mínima pra baixar sem perguntar.
As chaves nunca aparecem no log (só "configurada"/"não configurada").
"""
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ui_util import Cores, make_help_button


class SettingsWindow(Cores):
    """Janela de Configurações (abre por cima da principal; salvar vale na hora)."""

    def __init__(self, parent, config, main_app):
        self.config = config
        self.main_app = main_app
        
        self.window = tk.Toplevel(parent)
        self.window.title("Configurações")
        # Esc fecha, como nas outras janelas.
        self.window.bind('<Escape>', lambda e: self.window.destroy())
        self.window.geometry("640x700")
        self.window.minsize(580, 620)
        self.window.configure(bg=self.COLOR_BG)
        self.window.resizable(True, True)
        self.window.transient(parent)
        
        self.create_widgets()
    
    def create_widgets(self):
        """Monta as abas "Pasta de Saída" (pasta, bitrate, confiança, cookies) e "Chaves de API"."""
        # Cabeçalho
        header = tk.Frame(self.window, bg=self.COLOR_ACCENT)
        header.pack(fill='x', side='top')
        tk.Label(header, text="⚙  Configurações", font=('Segoe UI', 15, 'bold'),
                 bg=self.COLOR_ACCENT, fg='white').pack(anchor='w', padx=22, pady=14)

        # Estilo do Notebook (abas)
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass
        style.configure('Settings.TNotebook', background=self.COLOR_BG, borderwidth=0)
        style.configure('Settings.TNotebook.Tab', padding=(16, 10), font=('Segoe UI', 10, 'bold'))
        style.map('Settings.TNotebook.Tab', background=[('selected', self.COLOR_CARD)],
                  foreground=[('selected', self.COLOR_ACCENT)])

        # Botões empacotados ANTES do notebook (expansível) pra nunca serem espremidos.
        button_frame = tk.Frame(self.window, bg=self.COLOR_BG)
        button_frame.pack(side='bottom', fill='x', pady=(0, 18))

        btn_inner = tk.Frame(button_frame, bg=self.COLOR_BG)
        btn_inner.pack()
        self._make_button(btn_inner, "Salvar", self.save_settings, primary=True).pack(side='left', padx=5)
        self._make_button(btn_inner, "Cancelar", self.window.destroy, primary=False).pack(side='left', padx=5)

        notebook = ttk.Notebook(self.window, style='Settings.TNotebook')
        notebook.pack(side='top', fill='both', expand=True, padx=18, pady=18)
        
        # Tab 1: Pasta
        output_frame = tk.Frame(notebook, bg=self.COLOR_CARD, padx=20, pady=20)
        notebook.add(output_frame, text="📁  Pasta de Saída")
        
        output_label_row = tk.Frame(output_frame, bg=self.COLOR_CARD)
        output_label_row.pack(anchor='w', fill='x', pady=(0, 8))
        tk.Label(output_label_row, text="Onde as músicas serão salvas:", font=('Segoe UI', 10, 'bold'),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT).pack(side='left')
        make_help_button(
            output_label_row, title="Pasta de Saída",
            text="Escolha a pasta onde os álbuns baixados serão salvos.\n\n"
                 "Cada álbum vira uma subpasta organizada como "
                 "\"Artista - Álbum (Ano)\", com as faixas em MP3 numeradas "
                 "e a capa dentro. Pode ser qualquer pasta do seu computador "
                 "com espaço livre suficiente.",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))
        
        path_frame = tk.Frame(output_frame, bg=self.COLOR_CARD)
        path_frame.pack(fill='x', pady=5)
        
        self.output_path_var = tk.StringVar(value=self.config.get_output_directory())
        ttk.Entry(path_frame, textvariable=self.output_path_var, font=('Segoe UI', 10)).pack(
            side='left', fill='x', expand=True, ipady=4)
        self._make_button(path_frame, "Selecionar...", self.select_output_folder, primary=False).pack(
            side='left', padx=(8, 0))

        tk.Label(output_frame, text="Todos os álbuns baixados serão organizados nessa pasta,\n"
                                     "em subpastas no formato \"Artista - Álbum (Ano)\".",
                 font=('Segoe UI', 9), bg=self.COLOR_CARD, fg=self.COLOR_TEXT_MUTED,
                 justify='left').pack(anchor='w', pady=(14, 0))

        # --- Bitrate mínimo ---
        bitrate_row = tk.Frame(output_frame, bg=self.COLOR_CARD)
        bitrate_row.pack(anchor='w', fill='x', pady=(20, 8))
        tk.Label(bitrate_row, text="Bitrate mínimo aceito (kbps):", font=('Segoe UI', 10, 'bold'),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT).pack(side='left')
        make_help_button(
            bitrate_row, title="Bitrate mínimo",
            text="Áudios do YouTube com bitrate abaixo desse valor são "
                 "descartados (o programa tenta achar um formato melhor "
                 "antes de baixar; se não achar, pula o álbum em vez de "
                 "salvar num bitrate ruim).\n\n"
                 "Padrão: 80 kbps. Valores mais altos (ex: 128, 192, 256) "
                 "exigem que o YouTube tenha uma versão de melhor "
                 "qualidade disponível para aquele vídeo específico.",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))

        saved_bitrate = self.config.get("settings.min_bitrate_kbps", 80)
        self.min_bitrate_var = tk.StringVar(value=str(saved_bitrate if saved_bitrate else 80))
        ttk.Entry(output_frame, textvariable=self.min_bitrate_var, font=('Segoe UI', 10),
                  width=10).pack(anchor='w', ipady=3)

        # --- Confiança mínima pra baixar sem perguntar ---
        conf_row = tk.Frame(output_frame, bg=self.COLOR_CARD)
        conf_row.pack(anchor='w', fill='x', pady=(20, 0))
        tk.Label(conf_row, text="Confiança mínima para baixar sozinho (%):",
                 font=('Segoe UI', 10, 'bold'),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT).pack(side='left')
        make_help_button(
            conf_row,
            title="Confiança mínima",
            text="Quando o programa procura o álbum no Discogs, ele dá uma nota "
                 "de confiança à escolha. Abaixo do valor configurado aqui, o "
                 "álbum NÃO é baixado sozinho: vai pra lista 'Precisam de você', "
                 "pra você decidir.\n\n"
                 "Padrão: 80%. É um meio-termo entre não errar o disco e não "
                 "encher a lista de pendências.\n\n"
                 "Com 0% nada vai pra pendências por falta de confiança - o "
                 "programa baixa sempre, com o melhor palpite do Discogs. "
                 "Mais álbuns baixados, e mais chance de vir um com nome de "
                 "faixa errado.\n\n"
                 "Com 100% só baixa quando a identificação for perfeita.",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))

        saved_conf = self.config.get("settings.auto_process_min_confidence_pct",
                                      self.main_app.AUTO_PROCESS_MIN_CONFIDENCE_PCT)
        self.min_confidence_var = tk.StringVar(value=str(saved_conf))
        ttk.Entry(output_frame, textvariable=self.min_confidence_var,
                  font=('Segoe UI', 10), width=10).pack(anchor='w', ipady=3)

        # --- Cookies do navegador ---
        ck_row = tk.Frame(output_frame, bg=self.COLOR_CARD)
        ck_row.pack(anchor='w', fill='x', pady=(20, 0))
        tk.Label(ck_row, text="Usar cookies do navegador:", font=('Segoe UI', 10, 'bold'),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT).pack(side='left')
        make_help_button(
            ck_row,
            title="Cookies do navegador",
            text="Isto resolve o problema da QUALIDADE na raiz.\n\n"
                 "Sem cookies, o YouTube às vezes bloqueia o programa "
                 "(erro 403, 'confirm you're not a bot'). Pra passar, ele "
                 "recorre a um modo alternativo que funciona mas só oferece "
                 "áudio de baixa qualidade - tipicamente 60kbps em vez dos "
                 "130kbps que o vídeo tem.\n\n"
                 "Com os cookies do seu navegador, o YouTube reconhece uma "
                 "sessão normal, não bloqueia, e o programa baixa na melhor "
                 "qualidade disponível.\n\n"
                 "Em 'automático' (recomendado) o programa testa os "
                 "navegadores instalados e usa o primeiro cujos cookies "
                 "consiga ler. Ele faz isso uma vez ao abrir e repete só "
                 "depois de uma falha - não a cada música.\n\n"
                 "Ou escolha um navegador específico. Deixe em 'nenhum' "
                 "pra não usar cookies.\n\n"
                 "Observações: o navegador precisa estar instalado e logado. "
                 "No Windows, o Chrome criptografa os cookies e às vezes a "
                 "leitura falha - nesse caso o programa avisa e segue sem "
                 "eles, sem travar. Fechar o navegador antes costuma ajudar.",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))

        self.cookies_browser_var = tk.StringVar(
            value=self.config.get("settings.cookies_browser", "automático") or "automático")
        ttk.Combobox(output_frame, textvariable=self.cookies_browser_var,
                     values=["automático", "nenhum", "chrome", "firefox", "edge",
                             "brave", "opera", "vivaldi", "chromium"],
                     state="readonly", font=('Segoe UI', 10),
                     width=18).pack(anchor='w', ipady=3)

        # --- Arquivo de correções do editor (pra ajustar o programa) ---
        cor_row = tk.Frame(output_frame, bg=self.COLOR_CARD)
        cor_row.pack(anchor='w', fill='x', pady=(20, 0))
        self.gravar_correcoes_var = tk.BooleanVar(value=bool(self.config.get("settings.gravar_correcoes_editor", True)))
        tk.Checkbutton(cor_row, text="Guardar as correções feitas no ✂ Editar", variable=self.gravar_correcoes_var,
                       font=('Segoe UI', 10, 'bold'), bg=self.COLOR_CARD, fg=self.COLOR_TEXT,
                       activebackground=self.COLOR_CARD, selectcolor=self.COLOR_CARD).pack(side='left')
        make_help_button(
            cor_row,
            title="Correções do editor",
            text="Cada vez que você salva no ✂ Editar, o programa anota o que tinha sugerido e o que você "
                 "deixou: cortes mantidos, movidos (quanto), apagados e novos, e os nomes trocados.\n\n"
                 "Fica num arquivo só: <pasta dos discos>\\logs\\correcoes_do_editor.txt. De tempos em "
                 "tempos, mande esse arquivo na conversa de suporte: é com ele que os cortes automáticos são "
                 "ajustados.\n\n"
                 "Não tem chave, senha nem nada pessoal: só tempos, nomes de discos e de músicas.\n\n"
                 "Desmarque quando o ajuste estiver pronto.",
            button_bg=self.COLOR_CARD,
        ).pack(side='left', padx=(6, 0))

        # Tab 2: API Keys, num Canvas com rolagem (DPI/fonte grande não corta o último campo)
        api_tab_container = tk.Frame(notebook, bg=self.COLOR_CARD)
        notebook.add(api_tab_container, text="🔑  Chaves de API")

        api_canvas = tk.Canvas(api_tab_container, bg=self.COLOR_CARD, highlightthickness=0)
        api_scrollbar = ttk.Scrollbar(api_tab_container, orient='vertical', command=api_canvas.yview)
        api_frame = tk.Frame(api_canvas, bg=self.COLOR_CARD, padx=20, pady=18)

        api_frame.bind(
            "<Configure>",
            lambda e: api_canvas.configure(scrollregion=api_canvas.bbox("all"))
        )
        api_canvas_window = api_canvas.create_window((0, 0), window=api_frame, anchor="nw")
        api_canvas.configure(yscrollcommand=api_scrollbar.set)

        api_canvas.pack(side='left', fill='both', expand=True)
        api_scrollbar.pack(side='right', fill='y')

        # Faz o frame interno acompanhar a largura do canvas
        def _on_api_canvas_resize(event):
            api_canvas.itemconfig(api_canvas_window, width=event.width)
        api_canvas.bind('<Configure>', _on_api_canvas_resize)

        # Scroll com a roda do mouse, só quando o cursor está sobre esta aba
        def _on_api_mousewheel(event):
            api_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        api_canvas.bind('<Enter>', lambda e: api_canvas.bind_all('<MouseWheel>', _on_api_mousewheel))
        api_canvas.bind('<Leave>', lambda e: api_canvas.unbind_all('<MouseWheel>'))

        self.groq_key_var = tk.StringVar(value=self.config.get("api_keys.groq", ""))
        self._make_api_field(
            api_frame, "Groq (opcional)", "https://console.groq.com/keys", self.groq_key_var,
            help_text="IA usada para ajudar a identificar álbuns em casos difíceis. "
                      "É opcional, mas melhora os resultados.\n\n"
                      "Como conseguir:\n"
                      "1. Crie uma conta gratuita em console.groq.com\n"
                      "2. Vá em 'API Keys' e clique em 'Create API Key'\n"
                      "3. Copie a chave gerada (começa com 'gsk_') e cole aqui"
        )

        self.discogs_key_var = tk.StringVar(value=self.config.get("api_keys.discogs_token", ""))
        self._make_api_field(
            api_frame, "Discogs (obrigatório)",
            "https://www.discogs.com/settings/developers", self.discogs_key_var,
            help_text="ÚNICA fonte de identificação do programa: nomes de faixas, "
                      "artista, álbum, ano e capa vêm todos dela. Sem essa chave, "
                      "o programa não consegue identificar nenhum álbum.\n\n"
                      "Como conseguir:\n"
                      "1. Crie uma conta gratuita em discogs.com\n"
                      "2. Vá em Configurações > Desenvolvedor (o link abaixo já leva lá)\n"
                      "3. Clique em 'Generate new token'\n"
                      "4. Copie o token gerado e cole aqui"
        )

        self.google_key_var = tk.StringVar(value=self.config.get("api_keys.google_custom_search.api_key", ""))
        self._make_api_field(
            api_frame, "YouTube Data API Key (opcional)",
            "https://console.cloud.google.com/apis", self.google_key_var,
            help_text="NÃO tem relação com identificação de álbuns (isso é só o "
                      "Discogs, acima). Serve pra duas coisas:\n"
                      "• 'Buscar Playlists' - sem ela, essa busca não funciona;\n"
                      "• 'Canal Inteiro' - lista os vídeos do canal mais rápido. Sem "
                      "ela, o canal ainda é listado, por um método alternativo (mais "
                      "lento em canais muito grandes).\n\n"
                      "Como conseguir:\n"
                      "1. Acesse o Google Cloud Console (link abaixo)\n"
                      "2. Crie um projeto novo (ou use um existente)\n"
                      "3. Ative a 'YouTube Data API v3' na biblioteca de APIs\n"
                      "4. Vá em Credenciais e gere uma chave de API"
        )

    def _make_api_field(self, parent, label_text, help_url, var, show='*', help_text=None, link_label=None):
        """Cria um campo de API padronizado: rótulo + botão de ajuda (?) + link + entrada."""
        label_row = tk.Frame(parent, bg=self.COLOR_CARD)
        label_row.pack(anchor='w', pady=(10, 1), fill='x')
        tk.Label(label_row, text=label_text, font=('Segoe UI', 10, 'bold'),
                 bg=self.COLOR_CARD, fg=self.COLOR_TEXT).pack(side='left')
        if help_text:
            make_help_button(
                label_row, title=label_text, text=help_text,
                link_url=help_url, link_label=link_label or "Abrir página para gerar a chave",
                button_bg=self.COLOR_CARD,
            ).pack(side='left', padx=(6, 0))
        if help_url:
            tk.Label(parent, text=help_url, font=('Segoe UI', 8), bg=self.COLOR_CARD,
                     fg=self.COLOR_ACCENT).pack(anchor='w', pady=(0, 4))
        ttk.Entry(parent, textvariable=var, font=('Segoe UI', 10), show=show).pack(
            fill='x', pady=(0, 2), ipady=3)

    def _make_button(self, parent, text, command, primary=True):
        """Botão no estilo do programa (primário = cor de destaque)."""
        if primary:
            btn = tk.Button(parent, text=text, command=command, bg=self.COLOR_ACCENT, fg='white', bd=0,
                             font=('Segoe UI', 10, 'bold'), activebackground=self.COLOR_ACCENT_DARK,
                             activeforeground='white', cursor='hand2', padx=18, pady=8, relief='flat')
        else:
            btn = tk.Button(parent, text=text, command=command, bg=self.COLOR_CARD, fg=self.COLOR_TEXT, bd=1,
                             relief='solid', font=('Segoe UI', 10), highlightbackground=self.COLOR_BORDER,
                             activebackground=self.COLOR_BG, cursor='hand2', padx=18, pady=8)
        return btn
    
    def select_output_folder(self):
        folder = filedialog.askdirectory(title="Pasta de saída")
        if folder:
            self.output_path_var.set(folder)
    
    def save_settings(self):
        """Valida e grava tudo, aplica na janela principal na hora e registra no log."""
        self.config.set_output_directory(self.output_path_var.get())
        
        # Salva API keys
        self.config.set("api_keys.groq", self.groq_key_var.get())
        self.config.set("api_keys.discogs_token", self.discogs_key_var.get())
        self.config.set("api_keys.google_custom_search.api_key", self.google_key_var.get())

        # Bitrate inválido usa o padrão (80 kbps), sem impedir o resto de salvar.
        try:
            min_bitrate = int(self.min_bitrate_var.get())
            if min_bitrate <= 0:
                raise ValueError
        except (ValueError, AttributeError):
            min_bitrate = 80
            self.main_app.log("⚠ Bitrate mínimo inválido - usando o padrão de 80kbps")
        self.config.set("settings.min_bitrate_kbps", min_bitrate)

        # Confiança: 0 é válido (baixa tudo), por isso a checagem é por faixa.
        try:
            conf = int(self.min_confidence_var.get())
            if not (0 <= conf <= 100):
                raise ValueError
        except (ValueError, AttributeError):
            conf = 80
            self.main_app.log("⚠ Confiança mínima inválida (use 0 a 100) - usando 80%")
        self.config.set("settings.auto_process_min_confidence_pct", conf)

        try:
            nav = (self.cookies_browser_var.get() or 'nenhum').strip().lower()
        except AttributeError:
            nav = 'nenhum'
        self.config.set("settings.cookies_browser", nav)
        try:
            self.config.set("settings.gravar_correcoes_editor", bool(self.gravar_correcoes_var.get()))
        except AttributeError:
            pass
        if nav in ('automático', 'automatico'):
            self.main_app.log("🍪 Cookies: o programa vai procurar sozinho um navegador "
                               "com login no YouTube.")
            try:
                self.main_app.downloader.esquecer_navegador_de_cookies()
            except Exception:
                pass
        elif nav != 'nenhum':
            self.main_app.log(f"🍪 Cookies do {nav} serão usados nos downloads.")
        self.main_app.AUTO_PROCESS_MIN_CONFIDENCE_PCT = conf
        if conf == 0:
            self.main_app.log("ℹ️  Confiança mínima 0%: nada vai pra pendências "
                               "por falta de confiança - o programa baixa sempre.")
        
        messagebox.showinfo("Sucesso", "Configurações salvas!")
        self.window.destroy()
        
        # chave nova vale já, sem reiniciar (o Groq relê a chave a cada uso)
        self.main_app.catalogo.config['discogs_token'] = self.config.get("api_keys.discogs_token", "")
        self.main_app.log("\n✓ Configurações atualizadas")
        self.main_app._registrar_configuracoes('salvas')

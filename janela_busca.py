"""
Janela "Buscar Playlists" (mixin BuscaMixin): procura playlists de um
álbum no YouTube e enfileira as escolhidas.
"""
import re
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, ttk


class BuscaMixin:
    """Janela "Buscar Playlists" (buscar outra versão de um disco)."""

    def _show_playlist_search(self, artista_inicial=None, album_inicial=None):
        """
        Busca playlists do YouTube por artista (+ álbum opcional) e acrescenta
        as escolhidas à caixa do modo "Playlist Completa"; não baixa nada.
        Sem álbum: seleção múltipla (vários álbuns do artista). Com álbum:
        seleção única (qual candidata é a certa). Requer a YouTube Data API
        Key. Os argumentos pré-preenchem os campos ("Buscar outra versão").
        """
        win = tk.Toplevel(self.root)
        win.title("Buscar playlists no YouTube")
        win.bind('<Escape>', lambda e: win.destroy())
        win.geometry("760x640")
        win.configure(bg=self.COLOR_BG)
        win.transient(self.root)

        header = tk.Frame(win, bg=self.COLOR_ACCENT)
        header.pack(fill='x')
        tk.Label(header, text="🔍  Buscar playlists no YouTube", font=('Segoe UI', 14, 'bold'),
                 bg=self.COLOR_ACCENT, fg='white').pack(anchor='w', padx=20, pady=14)

        tk.Label(win, text="Busca playlists do YouTube por artista (e álbum, opcional). Sem álbum, "
                            "traz vários álbuns do artista pra você escolher quantos quiser. Com "
                            "álbum, traz candidatas a serem aquele álbum específico, pra escolher "
                            "a certa. O resultado vira entrada pronta pro modo \"Playlist Completa\" "
                            "- nada é baixado direto daqui.",
                 font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED,
                 wraplength=720, justify='left').pack(anchor='w', padx=20, pady=(12, 8))

        # --- Campos de busca ---
        form = tk.Frame(win, bg=self.COLOR_BG)
        form.pack(fill='x', padx=20, pady=(0, 10))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        tk.Label(form, text="Artista *", font=('Segoe UI', 9, 'bold'),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).grid(row=0, column=0, sticky='w', pady=(0, 2))
        artist_entry = tk.Entry(form, font=('Segoe UI', 10))
        artist_entry.grid(row=1, column=0, sticky='we', padx=(0, 10))

        tk.Label(form, text="Álbum (opcional)", font=('Segoe UI', 9, 'bold'),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT).grid(row=0, column=1, sticky='w', pady=(0, 2))
        album_entry = tk.Entry(form, font=('Segoe UI', 10))
        album_entry.grid(row=1, column=1, sticky='we', padx=(0, 10))

        # Pré-preenchido quando vem de "Buscar outra versão" (pendências).
        if artista_inicial:
            artist_entry.insert(0, artista_inicial)
        if album_inicial:
            album_entry.insert(0, album_inicial)

        search_btn_action = tk.Button(form, text="🔍  Buscar", bg=self.COLOR_ACCENT, fg='white', bd=0,
                                       font=('Segoe UI', 10, 'bold'), cursor='hand2', padx=14, pady=8,
                                       relief='flat', activebackground=self.COLOR_ACCENT_DARK)
        search_btn_action.grid(row=1, column=2, sticky='w')

        status_label = tk.Label(win, text="", font=('Segoe UI', 9), bg=self.COLOR_BG, fg=self.COLOR_TEXT_MUTED)
        status_label.pack(anchor='w', padx=20, pady=(4, 0))

        # --- Área de resultados (scroll) ---
        list_container = tk.Frame(win, bg=self.COLOR_BG)
        list_container.pack(fill='both', expand=True, padx=20, pady=(8, 10))

        canvas = tk.Canvas(list_container, bg=self.COLOR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient='vertical', command=canvas.yview)
        items_frame = tk.Frame(canvas, bg=self.COLOR_BG)

        items_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=items_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(canvas_window, width=e.width))

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _on_mousewheel))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # --- Rodapé ---
        footer = tk.Frame(win, bg=self.COLOR_BG)
        footer.pack(fill='x', padx=20, pady=(0, 16))

        tk.Button(footer, text="Fechar", command=win.destroy,
                  bg=self.COLOR_CARD, fg=self.COLOR_TEXT, bd=1, relief='solid',
                  font=('Segoe UI', 10), cursor='hand2', padx=14, pady=8,
                  highlightbackground=self.COLOR_BORDER).pack(side='right', padx=(8, 0))

        use_btn = tk.Button(footer, text="➕  Adicionar à lista",
                             bg=self.COLOR_ACCENT, fg='white', bd=0, font=('Segoe UI', 10, 'bold'),
                             cursor='hand2', padx=14, pady=8, relief='flat',
                             activebackground=self.COLOR_ACCENT_DARK, state='disabled')
        use_btn.pack(side='right')

        # --- Estado da busca/seleção ---
        state = {'results': [], 'selected': set(), 'single_mode': False}

        def _update_use_button():
            n = len(state['selected'])
            if n == 0:
                use_btn.config(state='disabled', text="➕  Adicionar à lista")
            else:
                use_btn.config(state='normal', text=f"▶  Usar {n} selecionada(s) na Playlist Completa")

        def _render_results():
            """Redesenha os cartões de resultado com o estado de seleção atual."""
            for w in items_frame.winfo_children():
                w.destroy()

            for res in state['results']:
                pid = res['playlist_id']
                card = tk.Frame(items_frame, bg=self.COLOR_CARD, highlightthickness=1,
                                 highlightbackground=self.COLOR_BORDER)
                card.pack(fill='x', pady=6)
                inner = tk.Frame(card, bg=self.COLOR_CARD, padx=14, pady=12)
                inner.pack(fill='x')

                top_row = tk.Frame(inner, bg=self.COLOR_CARD)
                top_row.pack(fill='x', anchor='w')
                tk.Label(top_row, text=res['title'], font=('Segoe UI', 10, 'bold'),
                         bg=self.COLOR_CARD, fg=self.COLOR_TEXT, wraplength=480,
                         justify='left').pack(side='left', anchor='w')

                count_text = f"{res['item_count']} vídeo(s)" if res.get('item_count') is not None else "? vídeos"
                tk.Label(top_row, text=count_text, font=('Segoe UI', 9, 'bold'),
                         bg=self.COLOR_CARD, fg=self.COLOR_TEXT_MUTED).pack(side='right')

                tk.Label(inner, text=f"Canal: {res.get('channel_title', '?')}", font=('Segoe UI', 9),
                         bg=self.COLOR_CARD, fg=self.COLOR_TEXT_MUTED,
                         wraplength=680, justify='left').pack(anchor='w', pady=(2, 8))

                btn_row = tk.Frame(inner, bg=self.COLOR_CARD)
                btn_row.pack(anchor='w')

                is_selected = pid in state['selected']

                def _toggle(pid=pid):
                    if state['single_mode']:
                        state['selected'] = set() if pid in state['selected'] else {pid}
                    else:
                        state['selected'].discard(pid) if pid in state['selected'] else state['selected'].add(pid)
                    _update_use_button()
                    _render_results()

                if state['single_mode']:
                    select_label = "◉ Selecionada" if is_selected else "○ Selecionar"
                else:
                    select_label = "☑ Selecionada" if is_selected else "☐ Selecionar"
                tk.Button(
                    btn_row, text=select_label, command=_toggle,
                    bg=(self.COLOR_SUCCESS if is_selected else self.COLOR_CARD),
                    fg=('white' if is_selected else self.COLOR_TEXT),
                    bd=1, relief='solid', font=('Segoe UI', 9), cursor='hand2', padx=12, pady=5,
                    highlightbackground=self.COLOR_BORDER
                ).pack(side='left', padx=(0, 6))

                tk.Button(btn_row, text="▶ Abrir no YouTube", command=lambda u=res['url']: webbrowser.open(u),
                          bg=self.COLOR_ACCENT, fg='white', bd=0, font=('Segoe UI', 9), cursor='hand2',
                          padx=12, pady=5, relief='flat', activebackground=self.COLOR_ACCENT_DARK).pack(side='left')

            _update_use_button()

        def _do_search():
            """Dispara a busca numa thread e mostra o resultado na thread da janela."""
            artist = artist_entry.get().strip()
            album = album_entry.get().strip()
            if not artist:
                messagebox.showwarning("Aviso", "Digite pelo menos o nome do artista.")
                return

            state['single_mode'] = bool(album)
            state['selected'] = set()
            state['results'] = []

            # "full album" só enviesa o ranking do YouTube pra álbuns de
            # verdade (não mixes/coletâneas); não exclui nada.
            query = f"{artist} {album} full album" if album else f"{artist} full album"

            search_btn_action.config(state='disabled', text="Buscando...")
            status_label.config(text="Buscando e conferindo qualidade de áudio...")
            for w in items_frame.winfo_children():
                w.destroy()

            def _run():
                results = self.downloader.search_playlists(query, max_results=15)

                def _finish():
                    search_btn_action.config(state='normal', text="🔍  Buscar")
                    if results is None:
                        status_label.config(text="")
                        messagebox.showerror(
                            "Erro",
                            "Não foi possível buscar. Confira se a 'YouTube Data API Key' está "
                            "configurada em Configurações (a mesma usada pra listar vídeos de "
                            "canal) e se o programa tem acesso à internet."
                        )
                        return
                    state['results'] = results
                    if not results:
                        status_label.config(text="Nenhuma playlist encontrada.")
                    else:
                        modo = "escolha UMA (a certa)" if state['single_mode'] else "marque quantas quiser"
                        status_label.config(text=f"{len(results)} playlist(s) encontrada(s) - {modo}.")
                    _render_results()

                self.root.after(0, _finish)

            threading.Thread(target=_run, daemon=True).start()

        search_btn_action.config(command=_do_search)
        artist_entry.bind('<Return>', lambda e: _do_search())
        album_entry.bind('<Return>', lambda e: _do_search())
        artist_entry.focus_set()

        def _use_selected():
            """Acrescenta as URLs escolhidas (sem repetir) e mantém a janela aberta."""
            urls = [r['url'] for r in state['results'] if r['playlist_id'] in state['selected']]
            if not urls:
                return
            # Acrescenta (não substitui) pra permitir buscar vários discos
            # seguidos e ir somando à lista.
            ja = self.playlist_text.get("1.0", tk.END).strip()
            existentes = [u.strip() for u in ja.splitlines() if u.strip()]
            novas = [u for u in urls if u not in existentes]
            repetidas = len(urls) - len(novas)

            if novas:
                if existentes:
                    self.playlist_text.insert(tk.END, "\n" + "\n".join(novas))
                else:
                    self.playlist_text.delete("1.0", tk.END)
                    self.playlist_text.insert("1.0", "\n".join(novas))
            self._select_mode('playlist')

            total = len(existentes) + len(novas)
            recado = f"✓ {len(novas)} adicionada(s) — {total} na lista"
            if repetidas:
                recado += f" ({repetidas} já estava(m))"
            try:
                status_label.config(text=recado + ".  Busque outro disco ou feche pra processar.")
            except Exception:
                pass
            # Limpa a seleção pra próxima busca começar do zero
            state['selected'].clear()
            try:
                _render_results()
            except Exception:
                pass

        use_btn.config(command=_use_selected)

    def _dados_para_busca(self, item):
        """
        (artista, álbum) de um item de pendência, para pré-preencher a busca.
        Prefere os dados do Discogs; senão divide o título do vídeo no
        primeiro separador (– — - |) e tira ano/gênero do fim
        ("Fulano – Disco -1962 (Bop)" -> "Fulano", "Disco").
        """
        disc = item.get('discogs_data') or {}
        artistas = disc.get('artists') or []
        artista = ''
        if artistas:
            primeiro = artistas[0]
            artista = primeiro if isinstance(primeiro, str) else (primeiro.get('name') or '')
        album = (disc.get('title') or '').strip()

        if not artista or not album:
            bruto = (item.get('video_title') or '').strip()
            for sep in ('\u2013', '\u2014', ' - ', '|'):
                if sep in bruto:
                    esq, _, dir_ = bruto.partition(sep)
                    artista = artista or esq.strip()
                    if not album:
                        # tira ano e gênero do fim: "Disco -1962 (Bop)"
                        limpo = re.sub(r'\s*[-\u2013]\s*(19|20)\d{2}.*$', '', dir_)
                        limpo = re.sub(r'\s*\([^)]*\)\s*$', '', limpo)
                        album = limpo.strip()
                    break
            else:
                artista = artista or bruto

        return artista.strip(), album.strip()

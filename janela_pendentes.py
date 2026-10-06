"""
Janela "Precisam de você": tabela dos itens de PendingQueue (título,
motivo, confiança, data, "▶ YouTube"), com filtro por motivo, busca,
ordenação por coluna e seleção múltipla.

Ações nos selecionados: Enfileirar (na fila única), Remover (vai pra
"Descartados", recuperável), Editar (tela "Conferir cortes": ouvir e marcar
os cortes), Informar tempos (lista colada pelo usuário; o
corte é feito nesses tempos), Corrigir busca (artista/álbum digitados por
você; a busca é refeita e o item vai pra fila) e Buscar outra versão. Cada ação grava uma vez
e só atualiza as linhas afetadas; mudanças vindas do trabalhador são
detectadas por PendingQueue.versao.
"""
import time
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from catalogo import inicios_de_texto

# kind -> rótulo curto da coluna "Motivo"
MOTIVOS = {
    'nao_encontrado': 'Não achado no Discogs',
    'baixa_confianca': 'Confiança baixa',
    'falha_corte': 'Corte não bateu',
    'outro_disco': 'Talvez outro disco',
    'falha_download': 'Download falhou',
    'erro_discogs': 'Discogs não respondeu',
}
TODOS = 'Todos os motivos'
COL_YT = '#5'          # coluna "▶ YouTube" (a 5ª de dados)


def rotulo_motivo(item):
    """Rótulo curto do motivo (kind) de um item."""
    return MOTIVOS.get(item.get('kind'), item.get('kind') or 'Outro')


def data_curta(texto):
    """'2026-10-01 22:15:03' -> '01/10 22:15' (o que não reconhecer, devolve igual)."""
    try:
        t = time.strptime(texto, '%Y-%m-%d %H:%M:%S')
        return time.strftime('%d/%m %H:%M', t)
    except Exception:
        return texto or ''


class JanelaPendentes:
    """Janela de pendências; `app` é a janela principal (cores, fila, log)."""

    def __init__(self, app):
        self.app = app
        self.fila_p = app.pending_queue
        self.vendo_descartados = False
        self._versao_vista = None
        self._ordem = ('added_at', False)       # coluna, decrescente?
        self._montar()
        self.recarregar()
        self._vigiar()

    # ------------------------------------------------------------------ montagem
    def _montar(self):
        """Cria os widgets: topo, filtro/busca, tabela, detalhe e botões."""
        app = self.app
        C = app
        win = self.win = tk.Toplevel(app.root)
        win.title("Precisam de você")
        win.geometry("940x600")
        win.minsize(760, 420)
        win.configure(bg=C.COLOR_BG)
        win.transient(app.root)
        win.bind('<Escape>', lambda e: self.fechar())
        win.protocol('WM_DELETE_WINDOW', self.fechar)

        topo = tk.Frame(win, bg=C.COLOR_WARNING)
        topo.pack(fill='x')
        self.titulo = tk.Label(topo, text='', font=('Segoe UI', 13, 'bold'),
                               bg=C.COLOR_WARNING, fg='white')
        self.titulo.pack(side='left', padx=18, pady=10)
        self.btn_descartados = tk.Button(topo, text='', command=self.alternar_descartados,
                                         bg=C.COLOR_WARNING, fg='white', bd=1, relief='solid',
                                         font=('Segoe UI', 9, 'bold'), cursor='hand2',
                                         activebackground='#B45309', activeforeground='white',
                                         padx=10, pady=3)
        self.btn_descartados.pack(side='right', padx=18)

        self.explica = tk.Label(win, text='', font=('Segoe UI', 9), bg=C.COLOR_BG,
                                fg=C.COLOR_TEXT_MUTED, wraplength=900, justify='left')
        self.explica.pack(anchor='w', padx=18, pady=(10, 6))

        # filtro + busca
        barra = tk.Frame(win, bg=C.COLOR_BG)
        barra.pack(fill='x', padx=18, pady=(0, 8))
        tk.Label(barra, text='Motivo:', font=('Segoe UI', 9, 'bold'), bg=C.COLOR_BG,
                 fg=C.COLOR_TEXT).pack(side='left')
        self.filtro = tk.StringVar(value=TODOS)
        self.combo = ttk.Combobox(barra, textvariable=self.filtro, state='readonly', width=30)
        self.combo.pack(side='left', padx=(6, 16))
        self.combo.bind('<<ComboboxSelected>>', lambda e: self.recarregar())
        tk.Label(barra, text='Buscar:', font=('Segoe UI', 9, 'bold'), bg=C.COLOR_BG,
                 fg=C.COLOR_TEXT).pack(side='left')
        self.busca = tk.StringVar()
        self.campo_busca = ttk.Entry(barra, textvariable=self.busca, width=34)
        self.campo_busca._menu_limpar = True
        self.campo_busca.pack(side='left', padx=(6, 0), fill='x', expand=True)
        self.busca.trace_add('write', lambda *a: self._busca_mudou())

        # tabela
        meio = tk.Frame(win, bg=C.COLOR_BG)
        meio.pack(fill='both', expand=True, padx=18)
        estilo = ttk.Style(win)
        estilo.configure('Pend.Treeview', rowheight=26, font=('Segoe UI', 9))
        estilo.configure('Pend.Treeview.Heading', font=('Segoe UI', 9, 'bold'))
        colunas = ('titulo', 'motivo', 'conf', 'data', 'yt')
        self.tree = ttk.Treeview(meio, columns=colunas, show='headings', selectmode='extended',
                                 style='Pend.Treeview')
        cab = {'titulo': ('Título', 400, 'w'), 'motivo': ('Motivo', 170, 'w'),
               'conf': ('Confiança', 80, 'center'), 'data': ('Data', 90, 'center'),
               'yt': ('▶ YouTube', 90, 'center')}
        chave_ordem = {'titulo': 'video_title', 'motivo': 'kind', 'conf': 'confidence_pct',
                       'data': 'added_at'}
        for c in colunas:
            texto, largura, ancora = cab[c]
            if c in chave_ordem:
                self.tree.heading(c, text=texto, command=lambda k=chave_ordem[c]: self._ordenar(k))
            else:
                self.tree.heading(c, text=texto)
            self.tree.column(c, width=largura, anchor=ancora, stretch=(c == 'titulo'))
        barra_v = ttk.Scrollbar(meio, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra_v.set)
        self.tree.pack(side='left', fill='both', expand=True)
        barra_v.pack(side='right', fill='y')
        self.tree.tag_configure('na_fila', foreground=C.COLOR_TEXT_MUTED)
        self.tree.tag_configure('zero', foreground=C.COLOR_ERROR)
        self.tree.bind('<Button-1>', self._clique, add='+')
        self.tree.bind('<Double-1>', self._duplo_clique)
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._seleção_mudou())
        self.tree.bind('<Control-a>', lambda e: (self.selecionar_tudo(), 'break')[1])
        self.tree.bind('<Delete>', lambda e: self.remover())
        self.tree.bind('<Return>', lambda e: self.enfileirar())

        # detalhe do item em foco (o motivo completo não cabe na coluna) e,
        # embaixo, a confirmação da última ação
        self.detalhe = tk.Label(win, text='', font=('Segoe UI', 9), bg=C.COLOR_BG,
                                fg=C.COLOR_WARNING, wraplength=900, justify='left', anchor='w')
        self.detalhe.pack(fill='x', padx=18, pady=(6, 0))
        self.aviso = tk.Label(win, text='', font=('Segoe UI', 9, 'bold'), bg=C.COLOR_BG,
                              fg=C.COLOR_SUCCESS, anchor='w')
        self.aviso.pack(fill='x', padx=18)

        # rodapé
        # ações numa linha própria (com "Informar tempos" não cabiam todas numa só). As duas
        # linhas do rodapé são as primeiras no pack, de baixo pra cima: com a janela baixa,
        # quem encolhe é a tabela, nunca os botões.
        primeiro = win.pack_slaves()[0]
        rod_acoes = tk.Frame(win, bg=C.COLOR_BG)
        rod_acoes.pack(side='bottom', fill='x', padx=18, pady=(0, 12), before=primeiro)
        rod = tk.Frame(win, bg=C.COLOR_BG)
        rod.pack(side='bottom', fill='x', padx=18, pady=(12, 6), before=primeiro)

        def botao(pai, texto, cmd, primario=False, cor=None):
            if primario:
                b = tk.Button(pai, text=texto, command=cmd, bg=C.COLOR_ACCENT, fg='white', bd=0,
                              font=('Segoe UI', 10, 'bold'), cursor='hand2', padx=14, pady=7,
                              activebackground=C.COLOR_ACCENT_DARK, activeforeground='white')
            else:
                b = tk.Button(pai, text=texto, command=cmd, bg=C.COLOR_CARD, fg=cor or C.COLOR_TEXT,
                              bd=1, relief='solid', font=('Segoe UI', 9), cursor='hand2',
                              padx=10, pady=5)
            return b

        self.b_tudo = botao(rod, 'Selecionar tudo', self.selecionar_tudo)
        self.b_tudo.pack(side='left')
        self.b_motivo = botao(rod, 'Todos com este motivo', self.selecionar_mesmo_motivo)
        self.b_motivo.pack(side='left', padx=(6, 0))
        self.b_fechar = botao(rod, 'Fechar', self.fechar)
        self.b_fechar.pack(side='right')
        # dois grupos de ações, um de cada vez: pendentes / descartados
        self.acoes_pend = tk.Frame(rod_acoes, bg=C.COLOR_BG)
        self.b_corrigir = botao(self.acoes_pend, '✏️ Corrigir busca', self.corrigir_busca, cor=C.COLOR_ACCENT)
        self.b_corrigir.pack(side='left', padx=(0, 6))
        self.b_editar = botao(self.acoes_pend, '✂ Editar', self.editar, cor=C.COLOR_ACCENT)
        self.b_editar.pack(side='left', padx=(0, 6))
        self.b_tempos = botao(self.acoes_pend, '⏱ Informar tempos', self.informar_tempos, cor=C.COLOR_ACCENT)
        self.b_tempos.pack(side='left', padx=(0, 6))
        self.b_buscar = botao(self.acoes_pend, '🔍 Buscar outra versão', self.buscar_outra, cor=C.COLOR_ACCENT)
        self.b_buscar.pack(side='left', padx=(0, 6))
        self.b_remover = botao(self.acoes_pend, '', self.remover, cor=C.COLOR_ERROR)
        self.b_remover.pack(side='left')
        self.b_enfileirar = botao(self.acoes_pend, '', self.enfileirar, primario=True)
        self.b_enfileirar.pack(side='left', padx=(8, 0))
        self.acoes_desc = tk.Frame(rod_acoes, bg=C.COLOR_BG)
        self.b_recuperar = botao(self.acoes_desc, '', self.recuperar, primario=True)
        self.b_recuperar.pack(side='left')
        self.acoes_pend.pack(side='right')
        # largura mínima: a linha de ações inteira (com as contagens "(99)") tem de caber
        win.update_idletasks()
        self.b_enfileirar.config(text='➕ Enfileirar (99)'); self.b_remover.config(text='🗑 Remover (99)')
        win.update_idletasks()
        win.minsize(max(760, self.acoes_pend.winfo_reqwidth() + 40), 420)

    # ------------------------------------------------------------------ dados
    def _lista_atual(self):
        """Cópia da lista em exibição (pendentes ou descartados)."""
        with self.fila_p._trava:
            return list(self.fila_p.descartados if self.vendo_descartados else self.fila_p.items)

    def _urls_na_fila(self):
        """URLs que já estão na fila de processamento (aguardando ou em andamento)."""
        try:
            f = self.app.fila
            if f is None:
                return set()
            return {i.get('url') for i in f.items if i.get('estado') in ('pendente', 'processando')}
        except Exception:
            return set()

    def _passa_no_filtro(self, it):
        """O item casa com o motivo escolhido e com todas as palavras da busca?"""
        motivo = self.filtro.get()
        if motivo and motivo != TODOS and not motivo.startswith(rotulo_motivo(it) + ' ('):
            return False
        termo = self.busca.get().strip().lower()
        if termo:
            alvo = ' '.join(str(it.get(k) or '') for k in ('video_title', 'reason', 'url',
                                                           'title_artist', 'title_album')).lower()
            if not all(p in alvo for p in termo.split()):
                return False
        return True

    def _valores(self, it, na_fila):
        """Valores das colunas de uma linha (📋 = playlist, ⏳ = já na fila)."""
        conf = it.get('confidence_pct', 0) or 0
        titulo = it.get('video_title') or it.get('url') or '?'
        if it.get('source_type') == 'playlist':
            titulo = '📋 ' + titulo
        if na_fila:
            titulo = '⏳ ' + titulo
        data = data_curta(it.get('descartado_em') if self.vendo_descartados else it.get('added_at'))
        return (titulo, rotulo_motivo(it), f"{conf}%", data, '▶ abrir')

    def _tags(self, it, na_fila):
        tags = []
        if na_fila:
            tags.append('na_fila')
        elif (it.get('confidence_pct', 0) or 0) == 0 and it.get('kind') == 'nao_encontrado':
            tags.append('zero')
        return tags

    def recarregar(self):
        """Refaz a tabela (abrir, filtrar, buscar, trocar pra descartados)."""
        itens = self._lista_atual()
        self._por_id = {it['id']: it for it in itens}
        selec = set(self.tree.selection())
        self._atualizar_filtro(itens)
        chave, dec = self._ordem
        def _k(it):
            v = it.get(chave)
            return (v is None, v if not isinstance(v, str) else v.lower())
        try:
            itens = sorted(itens, key=_k, reverse=dec)
        except Exception:
            pass
        na_fila = self._urls_na_fila()
        self.tree.delete(*self.tree.get_children())
        for it in itens:
            if not self._passa_no_filtro(it):
                continue
            nf = it.get('url') in na_fila and not self.vendo_descartados
            self.tree.insert('', 'end', iid=it['id'], values=self._valores(it, nf), tags=self._tags(it, nf))
        manter = [i for i in selec if self.tree.exists(i)]
        if manter:
            self.tree.selection_set(manter)
        self._versao_vista = self.fila_p.versao
        self._cabecalho()
        self._seleção_mudou()

    def _atualizar_filtro(self, itens):
        """Refaz as opções do combo de motivos (com contagem), mantendo a escolha."""
        contagem = {}
        for it in itens:
            r = rotulo_motivo(it)
            contagem[r] = contagem.get(r, 0) + 1
        opcoes = [TODOS] + [f"{r} ({n})" for r, n in sorted(contagem.items())]
        atual = self.filtro.get()
        self.combo['values'] = opcoes
        if atual != TODOS:
            base = atual.rsplit(' (', 1)[0]
            novo = next((o for o in opcoes if o.startswith(base + ' (')), None)
            self.filtro.set(novo or TODOS)

    def _cabecalho(self):
        """Título, explicação e botão de alternância conforme a vista atual."""
        n = len(self.fila_p.items)
        d = len(self.fila_p.descartados)
        if self.vendo_descartados:
            self.titulo.config(text=f"🗑  Descartados ({d})")
            self.btn_descartados.config(text=f"← Voltar aos pendentes ({n})")
            self.explica.config(text="Itens que você removeu. Selecione e clique em \"Recuperar\" "
                                     "pra devolvê-los à lista \"Precisam de você\".")
            self.win.title(f"Descartados ({d})")
        else:
            self.titulo.config(text=f"⚠️  {n} álbum(ns) precisam de você")
            self.btn_descartados.config(text=f"🗑 Descartados ({d})")
            self.explica.config(text="Álbuns que o programa não baixou sozinho - nada foi gravado. "
                                     "Selecione (clique, Ctrl+clique, Shift+clique) e use os botões "
                                     "embaixo. Clique em \"▶ abrir\" pra ver o vídeo; ⏳ = já está na fila.")
            self.win.title(f"Precisam de você ({n})")

    def _ordenar(self, chave):
        """Ordena pela coluna; clicar de novo inverte a ordem."""
        atual, dec = self._ordem
        self._ordem = (chave, (not dec) if atual == chave else False)
        self.recarregar()

    def _busca_mudou(self):
        # espera a pessoa parar de digitar (150ms) pra não refazer a cada letra
        if getattr(self, '_busca_after', None):
            try:
                self.win.after_cancel(self._busca_after)
            except Exception:
                pass
        self._busca_after = self.win.after(150, self.recarregar)

    # ------------------------------------------------------------------ seleção
    def selecionados(self):
        return [self._por_id[i] for i in self.tree.selection() if i in self._por_id]

    def _seleção_mudou(self):
        """Ajusta botões (contagem/habilitação) e o detalhe do item em foco."""
        sel = self.selecionados()
        n = len(sel)
        if self.vendo_descartados:
            if self.acoes_pend.winfo_manager():
                self.acoes_pend.pack_forget()
                self.acoes_desc.pack(side='right')
            self.b_recuperar.config(text=f"↩ Recuperar ({n})", state='normal' if n else 'disabled')
        else:
            if self.acoes_desc.winfo_manager():
                self.acoes_desc.pack_forget()
                self.acoes_pend.pack(side='right')
            self.b_enfileirar.config(text=f"➕ Enfileirar ({n})", state='normal' if n else 'disabled')
            self.b_remover.config(text=f"🗑 Remover ({n})", state='normal' if n else 'disabled')
            self.b_buscar.config(state='normal' if n == 1 else 'disabled')
            self.b_corrigir.config(state='normal' if n == 1 else 'disabled')
            self.b_tempos.config(state='normal' if n == 1 else 'disabled')
            self.b_editar.config(state='normal' if n == 1 and sel[0].get('source_type') != 'playlist'
                                 else 'disabled')
        self.b_motivo.config(state='normal' if n else 'disabled')
        foco = self.tree.focus()
        it = self._por_id.get(foco) if foco else (sel[0] if sel else None)
        if it:
            self.detalhe.config(text=f"{rotulo_motivo(it)}: {it.get('reason') or '-'}   ·   {it.get('url', '')}")
        else:
            self.detalhe.config(text='')

    def selecionar_tudo(self):
        self.tree.selection_set(self.tree.get_children())

    def selecionar_mesmo_motivo(self):
        """Seleciona todas as linhas visíveis com o(s) motivo(s) da seleção."""
        sel = self.selecionados()
        if not sel:
            return
        motivos = {it.get('kind') for it in sel}
        ids = [i for i in self.tree.get_children() if self._por_id[i].get('kind') in motivos]
        self.tree.selection_set(ids)

    # ------------------------------------------------------------------ YouTube
    def _clique(self, ev):
        """Clique na coluna "▶ YouTube": abre o vídeo, sem mexer na seleção."""
        if self.tree.identify_region(ev.x, ev.y) != 'cell':
            return None
        if self.tree.identify_column(ev.x) != COL_YT:
            return None
        linha = self.tree.identify_row(ev.y)
        if linha:
            self.abrir_youtube(linha)
        return 'break'

    def _duplo_clique(self, ev):
        linha = self.tree.identify_row(ev.y)
        if linha and self.tree.identify_region(ev.x, ev.y) == 'cell':
            self.abrir_youtube(linha)
            return 'break'
        return None

    def abrir_youtube(self, iid):
        it = self._por_id.get(iid)
        if it and it.get('url'):
            webbrowser.open(it['url'])

    # ------------------------------------------------------------------ ações
    def _avisar(self, texto, cor=None):
        """Mensagem de confirmação no rodapé, apagada após 6s."""
        self.aviso.config(text=texto, fg=cor or self.app.COLOR_SUCCESS)
        if getattr(self, '_aviso_after', None):
            try:
                self.win.after_cancel(self._aviso_after)
            except Exception:
                pass
        self._aviso_after = self.win.after(6000, lambda: self.aviso.config(text=''))

    def enfileirar(self):
        """Manda os selecionados pra fila única (via app._enfileirar_pendencias)."""
        sel = self.selecionados()
        if not sel or self.vendo_descartados:
            return
        n = self.app._enfileirar_pendencias(sel)
        if n is None:
            return
        # só as linhas afetadas mudam: ganham o ⏳
        na_fila = self._urls_na_fila()
        for it in sel:
            if self.tree.exists(it['id']):
                nf = it.get('url') in na_fila
                self.tree.item(it['id'], values=self._valores(it, nf), tags=self._tags(it, nf))
        self._avisar(f"✓ {n} na fila - assumem assim que o álbum atual terminar." if n
                     else "Esses já estavam na fila.")

    def remover(self):
        """Após uma confirmação, move os selecionados para Descartados."""
        sel = self.selecionados()
        if not sel or self.vendo_descartados:
            return
        if len(sel) == 1:
            pergunta = f"Remover \"{(sel[0].get('video_title') or '')[:70]}\"?"
        else:
            pergunta = f"Remover os {len(sel)} álbuns selecionados?"
        pergunta += "\n\nEles vão pra \"Descartados\", de onde dá pra recuperar."
        if not messagebox.askyesno("Remover", pergunta, parent=self.win):
            return
        ids = [it['id'] for it in sel]
        proximo = self._vizinho_depois(ids)
        n = self.fila_p.descartar(ids)
        for i in ids:
            if self.tree.exists(i):
                self.tree.delete(i)
            self._por_id.pop(i, None)
        self._versao_vista = self.fila_p.versao
        if proximo and self.tree.exists(proximo):
            self.tree.selection_set(proximo); self.tree.focus(proximo)
        self._atualizar_filtro(self._lista_atual())
        self._cabecalho(); self._seleção_mudou()
        self.app.log(f"🗑️  {n} item(ns) de \"Precisam de você\" foram pra Descartados (dá pra recuperar).")
        if hasattr(self.app, '_limpar_audios_pendentes'):
            self.app._limpar_audios_pendentes()      # áudio guardado de descartado: espaço livre
        self._avisar(f"✓ {n} removido(s) - estão em Descartados.")
        self._atualizar_botao_principal()

    def _vizinho_depois(self, ids):
        """Linha que deve ganhar a seleção após remover `ids` (seguinte ou anterior)."""
        filhos = list(self.tree.get_children())
        pos = [filhos.index(i) for i in ids if i in filhos]
        if not pos:
            return None
        for j in range(max(pos) + 1, len(filhos)):
            if filhos[j] not in ids:
                return filhos[j]
        for j in range(min(pos) - 1, -1, -1):
            if filhos[j] not in ids:
                return filhos[j]
        return None

    def recuperar(self):
        """Devolve os descartados selecionados à lista de pendentes."""
        sel = self.selecionados()
        if not sel or not self.vendo_descartados:
            return
        ids = [it['id'] for it in sel]
        n = self.fila_p.recuperar(ids)
        for i in ids:
            if self.tree.exists(i):
                self.tree.delete(i)
            self._por_id.pop(i, None)
        self._versao_vista = self.fila_p.versao
        self._atualizar_filtro(self._lista_atual())
        self._cabecalho(); self._seleção_mudou()
        self.app.log(f"↩️  {n} item(ns) recuperado(s) pra \"Precisam de você\".")
        self._avisar(f"✓ {n} recuperado(s).")
        self._atualizar_botao_principal()

    def buscar_outra(self):
        """Abre a busca de playlists já preenchida com artista/álbum do item."""
        sel = self.selecionados()
        if len(sel) != 1:
            return
        art, alb = self.app._dados_para_busca(sel[0])
        self.app._show_playlist_search(artista_inicial=art, album_inicial=alb)

    def corrigir_busca(self, artista=None, album=None):
        """
        Corrige o artista/álbum a buscar de UM item e o põe na fila. Sem
        argumentos, abre a caixinha pra digitar (com os nomes atuais).
        """
        sel = self.selecionados()
        if len(sel) != 1 or self.vendo_descartados:
            return None
        it = sel[0]
        if artista is None or album is None:
            art0, alb0 = self.app._dados_para_busca(it)
            return self._caixa_corrigir(it, it.get('title_artist') or art0 or '', it.get('title_album') or alb0 or '')
        if not artista.strip() or not album.strip():
            self._avisar("Preencha o artista e o álbum.", self.app.COLOR_ERROR)
            return None
        novo = self.fila_p.corrigir_busca(it['id'], artista, album)
        if not novo:
            return None
        self._por_id[novo['id']] = novo
        self.app.log(f"✏️  Busca corrigida: '{artista.strip()}' – '{album.strip()}' "
                     f"({(novo.get('video_title') or '')[:60]})")
        self.app._reg('PENDENTE', f"busca corrigida pelo usuário | {artista.strip()} – {album.strip()} | "
                                  f"{novo.get('url', '')}")
        n = self.app._enfileirar_pendencias([novo])
        self._versao_vista = self.fila_p.versao
        if self.tree.exists(novo['id']):
            nf = novo.get('url') in self._urls_na_fila()
            self.tree.item(novo['id'], values=self._valores(novo, nf), tags=self._tags(novo, nf))
        self._seleção_mudou()
        self._avisar("✓ Busca corrigida - o álbum está na fila e será procurado com os nomes novos."
                     if n else "✓ Busca corrigida.")
        return novo

    def _caixa_corrigir(self, it, artista, album):
        """Caixinha "Corrigir busca": dois campos e Buscar de novo / Cancelar."""
        C = self.app
        cx = tk.Toplevel(self.win)
        cx.title("Corrigir busca")
        cx.configure(bg=C.COLOR_BG)
        cx.transient(self.win)
        cx.resizable(False, False)
        q = tk.Frame(cx, bg=C.COLOR_BG, padx=20, pady=16)
        q.pack(fill='both', expand=True)
        tk.Label(q, text=(it.get('video_title') or it.get('url') or '')[:70], font=('Segoe UI', 10, 'bold'),
                 bg=C.COLOR_BG, fg=C.COLOR_TEXT).grid(row=0, column=0, columnspan=2, sticky='w')
        tk.Label(q, text="Como o álbum se chama no Discogs? A busca é refeita com estes nomes.",
                 font=('Segoe UI', 9), bg=C.COLOR_BG, fg=C.COLOR_TEXT_MUTED).grid(
                     row=1, column=0, columnspan=2, sticky='w', pady=(2, 12))
        campos = {}
        for linha, (rotulo, valor) in enumerate((('Artista:', artista), ('Álbum:', album)), start=2):
            tk.Label(q, text=rotulo, font=('Segoe UI', 9, 'bold'), bg=C.COLOR_BG, fg=C.COLOR_TEXT).grid(
                row=linha, column=0, sticky='w', pady=3)
            e = ttk.Entry(q, width=46)
            e.insert(0, valor)
            e._menu_limpar = True
            e.grid(row=linha, column=1, sticky='ew', padx=(8, 0), pady=3)
            campos[rotulo] = e
        botoes = tk.Frame(q, bg=C.COLOR_BG)
        botoes.grid(row=4, column=0, columnspan=2, sticky='e', pady=(14, 0))

        def ok():
            a, b = campos['Artista:'].get(), campos['Álbum:'].get()
            cx.destroy()
            self.corrigir_busca(a, b)

        tk.Button(botoes, text="Cancelar", command=cx.destroy, bg=C.COLOR_CARD, fg=C.COLOR_TEXT, bd=1,
                  relief='solid', font=('Segoe UI', 9), cursor='hand2', padx=10, pady=5).pack(side='right')
        tk.Button(botoes, text="🔍 Buscar de novo", command=ok, bg=C.COLOR_ACCENT, fg='white', bd=0,
                  font=('Segoe UI', 10, 'bold'), cursor='hand2', padx=14, pady=6,
                  activebackground=C.COLOR_ACCENT_DARK, activeforeground='white').pack(side='right', padx=(0, 8))
        cx.bind('<Return>', lambda e: ok())
        cx.bind('<Escape>', lambda e: cx.destroy())
        campos['Álbum:'].focus_set()
        campos['Álbum:'].select_range(0, tk.END)
        cx._campos, cx._ok = campos, ok           # usados pelos testes
        self._caixa = cx
        return cx

    def editar(self):
        """Abre a tela "Conferir cortes" (ouvir, ver e marcar os cortes) do item selecionado."""
        sel = self.selecionados()
        if len(sel) != 1 or self.vendo_descartados:
            return None
        return self.app.abrir_editor_pendencia(sel[0])

    def informar_tempos(self, texto=None):
        """
        Tempos das faixas de UM item, colados pelo usuário; o item vai pra
        fila e o corte é feito nesses tempos. Sem texto, abre a caixa.
        """
        sel = self.selecionados()
        if len(sel) != 1 or self.vendo_descartados:
            return None
        it = sel[0]
        if texto is None:
            return self._caixa_tempos(it)
        if not inicios_de_texto(texto):
            self._avisar("Não achei os tempos: cole uma linha por música, cada uma com o tempo (ex.: 3:12).",
                         self.app.COLOR_ERROR)
            return None
        novo = self.fila_p.informar_tempos(it['id'], texto)
        if not novo:
            return None
        self._por_id[novo['id']] = novo
        n_linhas = len(inicios_de_texto(texto))
        self.app.log(f"⏱ Tempos informados por você ({n_linhas} faixas): {(novo.get('video_title') or '')[:60]}")
        self.app._reg('PENDENTE', f"tempos informados pelo usuário | {n_linhas} faixas | {novo.get('url', '')}")
        n = self.app._enfileirar_pendencias([novo])
        self._versao_vista = self.fila_p.versao
        if self.tree.exists(novo['id']):
            nf = novo.get('url') in self._urls_na_fila()
            self.tree.item(novo['id'], values=self._valores(novo, nf), tags=self._tags(novo, nf))
        self._seleção_mudou()
        self._avisar("✓ Tempos guardados - o álbum está na fila e será cortado nesses tempos."
                     if n else "✓ Tempos guardados.")
        return novo

    def _caixa_tempos(self, it):
        """Caixa "Informar tempos": um campo de várias linhas e Usar estes tempos / Cancelar."""
        C = self.app
        cx = tk.Toplevel(self.win)
        cx.title("Informar tempos")
        cx.configure(bg=C.COLOR_BG)
        cx.transient(self.win)
        q = tk.Frame(cx, bg=C.COLOR_BG, padx=20, pady=16)
        q.pack(fill='both', expand=True)
        tk.Label(q, text=(it.get('video_title') or it.get('url') or '')[:70], font=('Segoe UI', 10, 'bold'),
                 bg=C.COLOR_BG, fg=C.COLOR_TEXT).pack(anchor='w')
        tk.Label(q, text="Cole a lista das músicas com o tempo de cada uma, uma por linha. Vale o início\n"
                         "(\"0:00 Nome\", \"3:12 Nome\"...) ou a duração (\"Nome 3:12\"). O disco é cortado\n"
                         "nesses tempos, ajustados à pausa mais próxima.",
                 font=('Segoe UI', 9), bg=C.COLOR_BG, fg=C.COLOR_TEXT_MUTED, justify='left').pack(anchor='w',
                                                                                                  pady=(2, 10))
        caixa = tk.Text(q, width=60, height=12, font=('Segoe UI', 10), relief='solid', bd=1, wrap='none')
        caixa.pack(fill='both', expand=True)
        if it.get('tempos_usuario'):
            caixa.insert('1.0', it['tempos_usuario'])
        botoes = tk.Frame(q, bg=C.COLOR_BG)
        botoes.pack(fill='x', pady=(12, 0))

        def ok():
            texto = caixa.get('1.0', 'end').strip()
            cx.destroy()
            self.informar_tempos(texto)

        tk.Button(botoes, text="Cancelar", command=cx.destroy, bg=C.COLOR_CARD, fg=C.COLOR_TEXT, bd=1,
                  relief='solid', font=('Segoe UI', 9), cursor='hand2', padx=10, pady=5).pack(side='right')
        tk.Button(botoes, text="⏱ Usar estes tempos", command=ok, bg=C.COLOR_ACCENT, fg='white', bd=0,
                  font=('Segoe UI', 10, 'bold'), cursor='hand2', padx=14, pady=6,
                  activebackground=C.COLOR_ACCENT_DARK, activeforeground='white').pack(side='right', padx=(0, 8))
        cx.bind('<Escape>', lambda e: cx.destroy())
        caixa.focus_set()
        cx._texto, cx._ok = caixa, ok             # usados pelos testes
        self._caixa = cx
        return cx

    def alternar_descartados(self):
        self.vendo_descartados = not self.vendo_descartados
        self.filtro.set(TODOS)
        self.busca.set('')
        self.tree.selection_set(())
        self.recarregar()

    # ------------------------------------------------------------------ vigia
    def _vigiar(self):
        """A cada 1,5s: se a lista mudou por fora (trabalhador), atualiza."""
        try:
            if not self.win.winfo_exists():
                return
            if self.fila_p.versao != self._versao_vista:
                self.recarregar()
                self._atualizar_botao_principal()
            else:
                # o ⏳ depende da fila de processamento, que muda sozinha
                na_fila = self._urls_na_fila()
                if not self.vendo_descartados:
                    for iid in self.tree.get_children():
                        it = self._por_id.get(iid)
                        nf = it.get('url') in na_fila
                        if ('na_fila' in self.tree.item(iid, 'tags')) != nf:
                            self.tree.item(iid, values=self._valores(it, nf), tags=self._tags(it, nf))
            self._vigia_after = self.win.after(1500, self._vigiar)
        except Exception:
            pass

    def _atualizar_botao_principal(self):
        try:
            self.app._refresh_main_buttons_state()
        except Exception:
            pass

    def fechar(self):
        try:
            if getattr(self, '_vigia_after', None):
                self.win.after_cancel(self._vigia_after)
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        if getattr(self.app, '_janela_pendentes', None) is self:
            self.app._janela_pendentes = None

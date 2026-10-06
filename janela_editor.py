"""
Tela "Conferir cortes": ouvir o disco, ver a forma do som, os silêncios e as
marcas de corte, e ajustar à mão (edicao_cortes.Edicao guarda o estado).

Abre de "Precisam de você" (botão ✂ Editar) ou da tela principal (✂ Editar
disco, pra um disco já cortado). Ao salvar, chama `ao_salvar(edicao)`.

Cores das marcas: azul = corte num silêncio; laranja tracejado = estimado
(sem silêncio perto - conferir); verde-água = marcado por você. Pedaço que
parece ter 2 músicas fica em vermelho na tabela. Guias (não são cortes):
amarelo = onde o Discogs poria o corte, pelas durações; roxo = possível troca
de música sem pausa (o som muda de repente).
"""
import tkinter as tk
from tkinter import ttk, messagebox

from ui_util import Cores

ONDA = "#A5B4FC"
SILENCIO = "#CBD5E1"
USUARIO = "#0D9488"
CURSOR = "#16A34A"
GUIA = "#EAB308"              # onde o Discogs poria o corte (pela soma das durações)
GUIA_TEXTO = "#A16207"
SOM = "#7C3AED"               # possível troca de música sem pausa (mudança no som)
COR_TIPO = {'silencio': Cores.COLOR_ACCENT, 'estimado': Cores.COLOR_WARNING, 'usuario': USUARIO}
NOME_TIPO = {'silencio': 'silêncio', 'estimado': 'estimado - conferir', 'usuario': 'marcado por você'}
VISTA_INICIAL_SEC = 600.0
VISTA_MIN_SEC = 10.0
TIQUE_MS = 60


def mmss(t, decimos=True):
    t = max(0.0, float(t))
    return f"{int(t // 60)}:{t % 60:04.1f}" if decimos else f"{int(t // 60)}:{int(t % 60):02d}"


class JanelaEditor(Cores):
    def __init__(self, pai, edicao, ao_salvar, tocador=None, titulo_janela="Conferir cortes",
                 texto_salvar="💾  Salvar cortes e pôr na fila", explicacao_salvar=None, ao_fechar=None, disco=None):
        from tocador import Tocador
        self.ed = edicao
        self.ao_salvar = ao_salvar
        self.ao_fechar = ao_fechar            # chamado ao fechar sem salvar
        self.tocador = tocador or Tocador()
        self.tocador.ao_terminar = None
        self.cursor = 0.0
        self.sel = None                      # marca selecionada (índice)
        self.arrastando = None
        self.vista = (0.0, min(self.ed.duracao, VISTA_INICIAL_SEC) or 1.0)
        self.salvou = False
        self.disco = disco                   # sem Discogs confirmado: {'artista', 'album', 'ano'} pra conferir

        w = self.win = tk.Toplevel(pai)
        w.title(f"{titulo_janela} - {edicao.titulo}"[:120])
        w.configure(bg=self.COLOR_BG)
        w.geometry("1360x760")
        w.minsize(1320, 680)         # a linha de botões inteira + a tabela
        w.protocol("WM_DELETE_WINDOW", self.fechar)
        self._montar(texto_salvar, explicacao_salvar or (
            "Os cortes salvos valem como \"tempos informados\": o disco vai pra fila e é cortado "
            "exatamente nesses pontos."))
        self._teclas()
        self._ir_ao_primeiro_problema()
        w.after(50, self.redesenhar)
        self._id_tique = w.after(TIQUE_MS, self._tique)

    # ================================================================== montagem
    def _botao(self, pai, texto, cmd, primario=False, cor=None, destaque=None):
        if primario or destaque:
            fundo = destaque or self.COLOR_ACCENT
            return tk.Button(pai, text=texto, command=cmd, font=('Segoe UI', 10, 'bold'), bd=0, bg=fundo,
                             fg='white', activebackground=self.COLOR_ACCENT_DARK, activeforeground='white',
                             padx=12, pady=5, cursor='hand2')
        return tk.Button(pai, text=texto, command=cmd, font=('Segoe UI', 10), bd=1, relief='solid',
                         bg=self.COLOR_CARD, fg=cor or self.COLOR_TEXT, padx=10, pady=4, cursor='hand2')

    def _montar(self, texto_salvar, explicacao):
        w, C = self.win, self
        cab = tk.Frame(w, bg=C.COLOR_ACCENT)
        cab.pack(fill='x')
        tk.Label(cab, text="🎧  Conferir cortes", font=('Segoe UI', 15, 'bold'), bg=C.COLOR_ACCENT,
                 fg='white').pack(side='left', padx=(18, 10), pady=10)
        tk.Label(cab, text=f"{self.ed.titulo}  ·  {mmss(self.ed.duracao, False)}", font=('Segoe UI', 10),
                 bg=C.COLOR_ACCENT, fg='#C7D2FE').pack(side='left', pady=10)
        self.chip = tk.Label(cab, text='', font=('Segoe UI', 10, 'bold'), bg='#FEF3C7', fg='#92400E', padx=8)
        self.chip.pack(side='right', padx=18, pady=10)

        # rodapé primeiro (com a janela baixa, quem encolhe é o resto)
        rod = tk.Frame(w, bg=C.COLOR_BG)
        rod.pack(side='bottom', fill='x', padx=16, pady=(0, 12))
        tk.Label(rod, text=explicacao, font=('Segoe UI', 9), bg=C.COLOR_BG, fg=C.COLOR_TEXT_MUTED,
                 wraplength=760, justify='left').pack(side='left')
        self.b_salvar = self._botao(rod, texto_salvar, self.salvar, primario=True)
        self.b_salvar.pack(side='right')
        self._botao(rod, "Cancelar", self.fechar).pack(side='right', padx=8)

        corpo = tk.Frame(w, bg=C.COLOR_BG)
        corpo.pack(fill='both', expand=True, padx=16, pady=10)
        dir_ = tk.Frame(corpo, bg=C.COLOR_BG, width=420)
        dir_.pack(side='right', fill='y', padx=(14, 0))
        dir_.pack_propagate(False)
        esq = tk.Frame(corpo, bg=C.COLOR_BG)
        esq.pack(side='left', fill='both', expand=True)

        tk.Label(esq, text="Disco inteiro  (clique pra ir a um ponto; o retângulo é o trecho ampliado embaixo)",
                 font=('Segoe UI', 9), bg=C.COLOR_BG, fg=C.COLOR_TEXT_MUTED).pack(anchor='w')
        self.c_geral = tk.Canvas(esq, height=64, bg=C.COLOR_CARD, highlightthickness=1,
                                 highlightbackground=C.COLOR_BORDER, cursor='hand2')
        self.c_geral.pack(fill='x', pady=(2, 8))
        self.c_geral.bind('<Button-1>', self._clique_geral)
        self.c_geral.bind('<B1-Motion>', self._clique_geral)
        self.c_zoom = tk.Canvas(esq, height=300, bg=C.COLOR_CARD, highlightthickness=1,
                                highlightbackground=C.COLOR_BORDER, cursor='crosshair')
        self.c_zoom.pack(fill='both', expand=True)
        self.c_zoom.bind('<Button-1>', self._clique_zoom)
        self.c_zoom.bind('<B1-Motion>', self._arrasta_zoom)
        self.c_zoom.bind('<ButtonRelease-1>', self._solta_zoom)
        self.c_zoom.bind('<MouseWheel>', self._roda)
        self.c_zoom.bind('<Button-4>', lambda e: self._rolar(-0.15))
        self.c_zoom.bind('<Button-5>', lambda e: self._rolar(0.15))
        for c in (self.c_geral, self.c_zoom):
            c.bind('<Configure>', lambda e: self.redesenhar())

        nav = tk.Frame(esq, bg=C.COLOR_BG)
        nav.pack(anchor='w', fill='x', pady=(10, 4))
        b = self._botao
        b(nav, "⏮", lambda: self.ir(0.0)).pack(side='left', padx=(0, 4))
        b(nav, "◀ marca", lambda: self.ir_marca(-1)).pack(side='left', padx=(0, 4))
        b(nav, "◀◀ 10s", lambda: self.andar(-10)).pack(side='left', padx=(0, 4))
        self.b_tocar = b(nav, "▶  Tocar", self.tocar_pausar, primario=True)
        self.b_tocar.config(width=9)
        self.b_tocar.pack(side='left', padx=(0, 4))
        b(nav, "10s ▶▶", lambda: self.andar(10)).pack(side='left', padx=(0, 4))
        b(nav, "marca ▶", lambda: self.ir_marca(1)).pack(side='left', padx=(0, 4))
        b(nav, "⏭", lambda: self.ir(self.ed.duracao - 5)).pack(side='left', padx=(0, 4))
        self.l_tempo = tk.Label(nav, text='', font=('Segoe UI', 12, 'bold'), bg=C.COLOR_BG, fg=C.COLOR_TEXT)
        self.l_tempo.pack(side='left', padx=(8, 0))
        # zoom à direita da linha (cabe mesmo na largura mínima)
        b(nav, "Disco inteiro", self.ver_tudo).pack(side='right')
        b(nav, "🔍+", lambda: self.zoom(0.5)).pack(side='right', padx=(2, 4))
        b(nav, "🔍−", lambda: self.zoom(2.0)).pack(side='right')

        ed = tk.Frame(esq, bg=C.COLOR_BG)
        ed.pack(anchor='w', fill='x', pady=(6, 0))
        # "Marcar corte" longe do Tocar (o mais usado), e em destaque
        self.b_marcar = b(ed, "✂  Marcar corte", self.marcar, destaque=USUARIO)
        self.b_marcar.pack(side='left', padx=(0, 6))
        b(ed, "🎧 Ouvir a emenda (±5s)", self.ouvir_emenda, cor=C.COLOR_ACCENT).pack(side='left', padx=(0, 6))
        b(ed, "⇤ 0,5s", lambda: self.empurrar(-0.5)).pack(side='left')
        b(ed, "0,5s ⇥", lambda: self.empurrar(0.5)).pack(side='left', padx=(2, 6))
        b(ed, "🧲 Ao silêncio mais perto", self.ao_silencio).pack(side='left', padx=(0, 6))
        b(ed, "🗑 Apagar marca", self.apagar, cor=C.COLOR_ERROR).pack(side='left')

        leg = tk.Frame(esq, bg=C.COLOR_BG)
        leg.pack(anchor='w', pady=(10, 0))
        leg2 = tk.Frame(esq, bg=C.COLOR_BG)
        leg2.pack(anchor='w', pady=(4, 0))
        tk.Label(leg2, text="Guias (não cortam nada):", font=('Segoe UI', 9), bg=C.COLOR_BG,
                 fg=C.COLOR_TEXT_MUTED).pack(side='left', padx=(0, 8))
        for cor, txt, tr, larg, onde in ((C.COLOR_ACCENT, "corte num silêncio", False, 3, leg),
                                         (C.COLOR_WARNING, "estimado (conferir)", True, 3, leg),
                                         (USUARIO, "marcado por você", False, 3, leg),
                                         (SILENCIO, "silêncio", False, 7, leg), (CURSOR, "cursor", False, 3, leg),
                                         (GUIA, "onde o Discogs poria o corte (pelas durações)", True, 3, leg2),
                                         (SOM, "o som muda de repente (troca sem pausa?)", False, 3, leg2)):
            cv = tk.Canvas(onde, width=22, height=14, bg=C.COLOR_BG, highlightthickness=0)
            cv.create_line(2, 7, 20, 7, fill=cor, width=larg, dash=(4, 2) if tr else None)
            cv.pack(side='left')
            tk.Label(onde, text=txt, font=('Segoe UI', 9), bg=C.COLOR_BG, fg=C.COLOR_TEXT).pack(side='left',
                                                                                              padx=(2, 14))
        tk.Label(esq, text="Teclado: espaço = tocar/pausar · ← → = 1s · Ctrl+← → = marca anterior/próxima · "
                           "M = marcar corte · Del = apagar marca · E = ouvir a emenda · clique na onda = levar "
                           "o cursor · arrastar uma marca = ajustar", font=('Segoe UI', 9), bg=C.COLOR_BG,
                 fg=C.COLOR_TEXT_MUTED, wraplength=880, justify='left').pack(anchor='w', pady=(6, 0))
        if not self.tocador.disponivel:
            tk.Label(esq, text=f"🔇 Sem som neste computador: {self.tocador.motivo}. Dá pra marcar os cortes "
                               f"pelo desenho e pelos silêncios.", font=('Segoe UI', 9, 'bold'), bg=C.COLOR_BG,
                     fg=C.COLOR_ERROR, wraplength=880, justify='left').pack(anchor='w', pady=(6, 0))

        if self.disco is not None:
            self._campos_do_disco(dir_)
        topo_tab = tk.Frame(dir_, bg=C.COLOR_BG)
        topo_tab.pack(fill='x')
        tk.Label(topo_tab, text="Músicas", font=('Segoe UI', 12, 'bold'), bg=C.COLOR_BG,
                 fg=C.COLOR_TEXT).pack(side='left')
        self.b_colar = self._botao(topo_tab, "📋 Colar nomes", self.colar_nomes)
        self.b_colar.pack(side='right')
        tk.Label(dir_, text="Clique numa linha pra levar o cursor ao começo dela. Duplo clique no nome pra "
                            "escrever outro ou escolher entre os nomes achados (Discogs, descrição, capítulos, "
                            "comentários).", font=('Segoe UI', 9), bg=C.COLOR_BG, fg=C.COLOR_TEXT_MUTED,
                 wraplength=410, justify='left').pack(anchor='w', pady=(2, 0))
        est = ttk.Style()
        est.configure('Ed.Treeview', font=('Segoe UI', 9), rowheight=24)
        est.configure('Ed.Treeview.Heading', font=('Segoe UI', 9, 'bold'))
        quadro = tk.Frame(dir_, bg=C.COLOR_BG)
        quadro.pack(fill='both', expand=True, pady=(6, 8))
        self.tabela = ttk.Treeview(quadro, style='Ed.Treeview', columns=('n', 'm', 'i', 'd', 'dc', 's'),
                                   show='headings', selectmode='browse')
        for col, tit, larg, an in (('n', 'Nº', 32, 'center'), ('m', 'Música', 170, 'w'), ('i', 'Início', 54, 'e'),
                                   ('d', 'Duração', 66, 'e'), ('dc', 'Discogs', 62, 'e'), ('s', '', 26, 'center')):
            self.tabela.heading(col, text=tit)
            self.tabela.column(col, width=larg, anchor=an, stretch=(col == 'm'))
        barra = ttk.Scrollbar(quadro, orient='vertical', command=self.tabela.yview)
        self.tabela.configure(yscrollcommand=barra.set)
        self.tabela.pack(side='left', fill='both', expand=True)
        barra.pack(side='right', fill='y')
        self.tabela.tag_configure('longo', foreground=C.COLOR_ERROR)
        self.tabela.tag_configure('estimado', foreground=C.COLOR_WARNING)
        self.tabela.bind('<<TreeviewSelect>>', self._linha_escolhida)
        self.tabela.bind('<Double-1>', self._editar_nome)
        self.avisos = tk.Frame(dir_, bg=C.COLOR_BG)
        self.avisos.pack(fill='x')

    def _campos_do_disco(self, pai):
        """Disco sem Discogs confirmado: artista, álbum e ano vêm do título do vídeo - confira aqui."""
        C = self
        f = tk.Frame(pai, bg='#FFFBEB', highlightthickness=1, highlightbackground='#FDE68A')
        f.pack(fill='x', pady=(0, 10))
        tk.Label(f, text="Disco - o Discogs não confirmou: confira o nome", font=('Segoe UI', 10, 'bold'),
                 bg='#FFFBEB', fg=C.COLOR_WARNING).grid(row=0, column=0, columnspan=4, sticky='w', padx=10,
                                                        pady=(8, 4))
        fonte = getattr(self.ed, 'fonte_dos_cortes', None)
        if fonte:
            tk.Label(f, text=f"Cortes e nomes sugeridos pelos tempos de: {fonte}", font=('Segoe UI', 9),
                     bg='#FFFBEB', fg=C.COLOR_TEXT).grid(row=1, column=0, columnspan=4, sticky='w', padx=10)
        self.v_artista = tk.StringVar(value=self.disco.get('artista', ''))
        self.v_album = tk.StringVar(value=self.disco.get('album', ''))
        self.v_ano = tk.StringVar(value=self.disco.get('ano', ''))
        for col, (rot, var, larg) in enumerate((("Artista", self.v_artista, 0), ("Álbum", self.v_album, 0))):
            tk.Label(f, text=rot, font=('Segoe UI', 9), bg='#FFFBEB', fg=C.COLOR_TEXT).grid(
                row=2 + col, column=0, sticky='w', padx=(10, 4), pady=2)
            ttk.Entry(f, textvariable=var, font=('Segoe UI', 9)).grid(row=2 + col, column=1, sticky='we', pady=2,
                                                                     padx=(0, 6))
        tk.Label(f, text="Ano", font=('Segoe UI', 9), bg='#FFFBEB', fg=C.COLOR_TEXT).grid(row=3, column=2, padx=(0, 4))
        ttk.Entry(f, textvariable=self.v_ano, font=('Segoe UI', 9), width=6).grid(row=3, column=3, padx=(0, 10))
        f.grid_columnconfigure(1, weight=1)
        tk.Label(f, text="", bg='#FFFBEB').grid(row=4, column=0, pady=1)

    def dados_do_disco(self):
        if self.disco is None:
            return None
        return {'artista': self.v_artista.get().strip(), 'album': self.v_album.get().strip(),
                'ano': self.v_ano.get().strip()}

    def _teclas(self):
        w = self.win
        w.bind('<space>', lambda e: self._se_nao_digitando(e, self.tocar_pausar))
        w.bind('<Left>', lambda e: self._se_nao_digitando(e, lambda: self.andar(-1)))
        w.bind('<Right>', lambda e: self._se_nao_digitando(e, lambda: self.andar(1)))
        w.bind('<Control-Left>', lambda e: self._se_nao_digitando(e, lambda: self.ir_marca(-1)))
        w.bind('<Control-Right>', lambda e: self._se_nao_digitando(e, lambda: self.ir_marca(1)))
        for k in ('m', 'M'):
            w.bind(f'<KeyPress-{k}>', lambda e: self._se_nao_digitando(e, self.marcar))
        for k in ('e', 'E'):
            w.bind(f'<KeyPress-{k}>', lambda e: self._se_nao_digitando(e, self.ouvir_emenda))
        w.bind('<Delete>', lambda e: self._se_nao_digitando(e, self.apagar))
        w.bind('<Escape>', lambda e: self._se_nao_digitando(e, self.fechar))   # na caixa do nome, Esc só cancela

    def _se_nao_digitando(self, evento, acao):
        if isinstance(evento.widget, (tk.Entry, ttk.Entry)):
            return None
        acao()
        return 'break'

    # ================================================================== desenho
    def _x(self, t, largura, t0, t1, margem=8):
        return margem + (largura - 2 * margem) * (t - t0) / max(1e-6, (t1 - t0))

    def _t(self, x, largura, t0, t1, margem=8):
        return t0 + (x - margem) / max(1, (largura - 2 * margem)) * (t1 - t0)

    def _onda(self, c, largura, altura, t0, t1, topo, base):
        env = self.ed.envelope
        if env is None or not len(env):
            return
        import numpy as np
        passo = 0.05
        meio = (topo + base) / 2
        meia = (base - topo) / 2 * 0.95
        cols = max(1, int(largura) - 16)
        idx = np.linspace(t0 / passo, t1 / passo, cols + 1).astype(int).clip(0, len(env) - 1)
        for k in range(cols):
            a, b = idx[k], max(idx[k] + 1, idx[k + 1])
            v = float(env[a:b].max()) if b > a else float(env[a])
            h = max(0.5, v * meia)
            x = 8 + k
            c.create_line(x, meio - h, x, meio + h, fill=ONDA)

    def redesenhar(self):
        if not self.win.winfo_exists():
            return
        self._desenhar_geral()
        self._desenhar_zoom()
        self._preencher_tabela()
        self._avisos()
        self.l_tempo.config(text=f"{mmss(self.cursor)} / {mmss(self.ed.duracao, False)}")

    def _desenhar_geral(self):
        c = self.c_geral
        c.delete('all')
        L, H = c.winfo_width(), c.winfo_height()
        if L < 50:
            return
        dur = self.ed.duracao or 1.0
        self._onda(c, L, H, 0, dur, 4, H - 4)
        for a, b, _ in self.ed.silencios:
            c.create_rectangle(self._x(a, L, 0, dur) - 1, 2, self._x(b, L, 0, dur) + 1, H - 2, fill=SILENCIO,
                               outline='')
        for i, m in enumerate(self.ed.marcas):
            x = self._x(m['pos'], L, 0, dur)
            c.create_line(x, 2, x, H - 2, fill=COR_TIPO[m['tipo']], width=3 if i == self.sel else 2,
                          dash=(4, 2) if m['tipo'] == 'estimado' else None)
        for p in self.ed.guias_discogs():
            x = self._x(p, L, 0, dur)
            c.create_line(x, H - 16, x, H - 2, fill=GUIA, width=3)
        for p in self.ed.sugestoes_som:
            x = self._x(p, L, 0, dur)
            c.create_line(x, 2, x, 16, fill=SOM, width=3)
        v0, v1 = self.vista
        c.create_rectangle(self._x(v0, L, 0, dur), 1, self._x(v1, L, 0, dur), H - 1, outline=self.COLOR_TEXT, width=2)
        x = self._x(self.cursor, L, 0, dur)
        c.create_line(x, 0, x, H, fill=CURSOR, width=2)

    def _desenhar_zoom(self):
        c = self.c_zoom
        c.delete('all')
        L, H = c.winfo_width(), c.winfo_height()
        if L < 50:
            return
        t0, t1 = self.vista
        topo, base = 38, H - 34
        for a, b, _ in self.ed.silencios:
            if b > t0 and a < t1:
                c.create_rectangle(self._x(max(a, t0), L, t0, t1), topo, self._x(min(b, t1), L, t0, t1), base,
                                   fill=SILENCIO, outline='')
        self._onda(c, L, H, t0, t1, topo, base)
        # nomes no meio de cada pedaço
        for i, ((a, b), nome) in enumerate(zip(self.ed.pecas(), self.ed.nomes())):
            ini, fim = max(a, t0), min(b, t1)
            if fim - ini < (t1 - t0) * 0.06:
                continue
            c.create_text(self._x((ini + fim) / 2, L, t0, t1), 18, text=f"{i + 1}. {nome}"[:48],
                          font=('Segoe UI', 9, 'bold'), fill=self.COLOR_TEXT)
        # guias (não são cortes): amarelo = pela duração do Discogs; roxo = o som muda de repente
        guias = self.ed.guias_discogs()
        lim = [0.0] + guias + [self.ed.duracao]
        for k, (a, b) in enumerate(zip(lim, lim[1:])):
            if b > t0 and a < t1 and k < len(self.ed.oficiais) and (min(b, t1) - max(a, t0)) > (t1 - t0) * 0.08:
                c.create_text(self._x((max(a, t0) + min(b, t1)) / 2, L, t0, t1), 34,
                              text=f"Discogs {k + 1}: {mmss(self.ed.oficiais[k]['duracao'], False)}",
                              font=('Segoe UI', 8), fill=GUIA_TEXTO)
        for p in guias:
            if t0 <= p <= t1:
                x = self._x(p, L, t0, t1)
                c.create_line(x, base - 60, x, base + 6, fill=GUIA, width=3, dash=(3, 2))
                c.create_polygon(x - 6, base + 14, x + 6, base + 14, x, base + 4, fill=GUIA, outline='')
        for p in self.ed.sugestoes_som:
            if t0 <= p <= t1:
                x = self._x(p, L, t0, t1)
                c.create_line(x, topo, x, topo + 60, fill=SOM, width=3)
                c.create_polygon(x - 6, topo, x + 6, topo, x, topo + 10, fill=SOM, outline='')
        for i, m in enumerate(self.ed.marcas):
            if not (t0 <= m['pos'] <= t1):
                continue
            x, cor = self._x(m['pos'], L, t0, t1), COR_TIPO[m['tipo']]
            larg = 5 if i == self.sel else 3
            c.create_line(x, topo - 6, x, base + 4, fill=cor, width=larg,
                          dash=(6, 3) if m['tipo'] == 'estimado' else None)
            c.create_polygon(x - 8, topo - 13, x + 8, topo - 13, x, topo - 2, fill=cor, outline='')
            c.create_text(x + 5, base - 10, text=f"{mmss(m['pos'])}  {NOME_TIPO[m['tipo']]}", anchor='w',
                          font=('Segoe UI', 8, 'bold' if i == self.sel else 'normal'), fill=cor)
        # régua: um traço a cada 1/2/5/10/30/60 s, conforme o zoom
        passo = next((p for p in (1, 2, 5, 10, 15, 30, 60, 120, 300) if (t1 - t0) / p <= 16), 600)
        t = (int(t0 // passo) + 1) * passo
        while t < t1:
            x = self._x(t, L, t0, t1)
            c.create_line(x, base + 2, x, base + 8, fill=self.COLOR_TEXT_MUTED)
            c.create_text(x, base + 18, text=mmss(t, False), font=('Segoe UI', 8), fill=self.COLOR_TEXT_MUTED)
            t += passo
        if t0 <= self.cursor <= t1:
            x = self._x(self.cursor, L, t0, t1)
            c.create_line(x, topo - 14, x, base + 8, fill=CURSOR, width=2)
            c.create_rectangle(x - 40, topo - 2, x - 2, topo + 14, fill=CURSOR, outline='')
            c.create_text(x - 21, topo + 6, text=mmss(self.cursor), font=('Segoe UI', 8, 'bold'), fill='white')

    def _preencher_tabela(self):
        tv = self.tabela
        escolhida = tv.selection()
        tv.delete(*tv.get_children())
        sit = self.ed.situacao_pecas()
        durs_of = self.ed.duracoes_oficiais()
        for i, ((a, b), nome) in enumerate(zip(self.ed.pecas(), self.ed.nomes())):
            marca = {'longo': '✗', 'estimado': '⚠', 'ok': '✓'}[sit[i]]
            tv.insert('', 'end', iid=str(i), values=(i + 1, nome, mmss(a, False), mmss(b - a, False),
                                                     mmss(durs_of[i], False) if durs_of[i] else '-', marca),
                      tags=(sit[i],))
        if escolhida and tv.exists(escolhida[0]):
            # os <<TreeviewSelect>> do delete/selection_set chegam depois (fila de eventos) e acham a
            # mesma linha: _linha_escolhida só age quando a linha muda (senão seria um laço sem fim)
            self._linha_atual = escolhida[0]
            tv.selection_set(escolhida[0])

    def _avisos(self):
        for f in self.avisos.winfo_children():
            f.destroy()
        faltam, sobram, est = self.ed.faltam(), self.ed.sobram(), self.ed.estimadas()
        sit = self.ed.situacao_pecas()
        longos = [i + 1 for i, s in enumerate(sit) if s == 'longo']
        partes = []
        dicas = self._dicas_de_troca(longos)
        if faltam:
            onde = f" - ouça a faixa {', '.join(map(str, longos[:3]))}" if longos else ""
            self._caixa("#FEF2F2", "#FECACA", self.COLOR_ERROR,
                        f"✗  Falta{'m' if faltam > 1 else ''} {faltam} corte{'s' if faltam > 1 else ''}",
                        f"O Discogs tem {len(self.ed.oficiais)} músicas e há {len(self.ed.marcas) + 1} pedaços"
                        f"{onde}. Ache a troca de música ouvindo e use \"✂ Marcar corte\".{dicas}")
            partes.append(f"faltam {faltam} corte{'s' if faltam > 1 else ''}")
        elif longos:
            self._caixa("#FEF2F2", "#FECACA", self.COLOR_ERROR, f"✗  Faixa {', '.join(map(str, longos[:3]))} "
                        f"longa demais", f"Pode ter duas músicas juntas: ouça e marque o corte, se for o caso.{dicas}")
            partes.append("faixa longa demais")
        if sobram:
            self._caixa("#FEF2F2", "#FECACA", self.COLOR_ERROR,
                        f"✗  Sobra{'m' if sobram > 1 else ''} {sobram} corte{'s' if sobram > 1 else ''}",
                        f"O Discogs tem {len(self.ed.oficiais)} músicas e há {len(self.ed.marcas) + 1} pedaços: "
                        f"algum corte caiu dentro de uma música. Selecione e use \"🗑 Apagar marca\".")
            partes.append(f"sobra{'m' if sobram > 1 else ''} {sobram}")
        if est:
            nums = ', '.join(f"{i + 1}→{i + 2}" for i in est[:4])
            self._caixa("#FFFBEB", "#FDE68A", self.COLOR_WARNING,
                        f"⚠  {len(est)} corte{'s' if len(est) > 1 else ''} estimado{'s' if len(est) > 1 else ''}",
                        f"Faixas {nums}{' ...' if len(est) > 4 else ''}: sem silêncio perto. Use \"◀ marca / "
                        f"marca ▶\" e \"🎧 Ouvir a emenda\"; se estiver certo, não precisa fazer nada.")
            partes.append(f"{len(est)} estimado{'s' if len(est) > 1 else ''} pra conferir")
        if not partes:
            self._caixa("#F0FDF4", "#BBF7D0", self.COLOR_SUCCESS, "✓  Tudo confirmado",
                        "Todos os cortes estão em silêncios ou foram marcados por você.")
        self.chip.config(text=('⚠ ' + '  ·  '.join(partes)) if partes else '✓ tudo confirmado',
                         bg='#FEF3C7' if partes else '#DCFCE7', fg='#92400E' if partes else '#166534')

    def _dicas_de_troca(self, longos):
        """ "O som muda em 12:40 e 15:02" dentro das faixas longas (as marcas roxas)."""
        pontos = [p for i in longos for p in self.ed.sugestoes_dentro(i - 1)]
        if not pontos:
            return ""
        return (f" O som muda de repente em {', '.join(mmss(p, False) for p in pontos[:4])} (marca roxa): "
                f"pode ser a troca - ouça ali.")

    def _caixa(self, fundo, borda, cor, titulo, texto):
        f = tk.Frame(self.avisos, bg=fundo, highlightthickness=1, highlightbackground=borda)
        f.pack(fill='x', pady=(0, 8))
        tk.Label(f, text=titulo, font=('Segoe UI', 10, 'bold'), bg=fundo, fg=cor).pack(anchor='w', padx=10,
                                                                                   pady=(8, 2))
        tk.Label(f, text=texto, font=('Segoe UI', 9), bg=fundo, fg=self.COLOR_TEXT, wraplength=390,
                 justify='left').pack(anchor='w', padx=10, pady=(0, 8))

    # ================================================================== navegação
    def _mostrar(self, t):
        """Garante que `t` está no trecho ampliado (sem mudar o zoom)."""
        v0, v1 = self.vista
        larg = v1 - v0
        if not (v0 + larg * 0.05 <= t <= v1 - larg * 0.05):
            v0 = min(max(0.0, t - larg / 2), max(0.0, self.ed.duracao - larg))
            self.vista = (v0, v0 + larg)

    def ir(self, t, tocar_junto=True):
        t = min(max(0.0, float(t)), max(0.0, self.ed.duracao - 0.05))
        tocava = self.tocador.tocando
        self.cursor = t
        self._mostrar(t)
        if tocava and tocar_junto:
            self.tocador.tocar(self.ed.arquivo, t)
        self.redesenhar()

    def andar(self, seg):
        self.ir((self.tocador.posicao() if self.tocador.tocando else self.cursor) + seg)

    def ir_marca(self, direcao):
        marcas = [m['pos'] for m in self.ed.marcas]
        if not marcas:
            return
        agora = self.tocador.posicao() if self.tocador.tocando else self.cursor
        if direcao > 0:
            alvo = next((i for i, p in enumerate(marcas) if p > agora + 0.05), None)
        else:
            alvo = next((i for i in range(len(marcas) - 1, -1, -1) if marcas[i] < agora - 0.05), None)
        if alvo is None:
            return
        self.sel = alvo
        self.ir(marcas[alvo])

    def zoom(self, fator):
        v0, v1 = self.vista
        larg = min(self.ed.duracao, max(VISTA_MIN_SEC, (v1 - v0) * fator))
        centro = self.cursor if v0 <= self.cursor <= v1 else (v0 + v1) / 2
        v0 = min(max(0.0, centro - larg / 2), max(0.0, self.ed.duracao - larg))
        self.vista = (v0, v0 + larg)
        self.redesenhar()

    def ver_tudo(self):
        self.vista = (0.0, self.ed.duracao or 1.0)
        self.redesenhar()

    def _rolar(self, fracao):
        v0, v1 = self.vista
        larg = v1 - v0
        v0 = min(max(0.0, v0 + larg * fracao), max(0.0, self.ed.duracao - larg))
        self.vista = (v0, v0 + larg)
        self.redesenhar()

    def _roda(self, evento):
        self._rolar(-0.15 if evento.delta > 0 else 0.15)

    def _ir_ao_primeiro_problema(self):
        """Abre mostrando o primeiro corte a conferir (ou o pedaço longo demais)."""
        sit = self.ed.situacao_pecas()
        est = self.ed.estimadas()
        if 'longo' in sit:
            a, b = self.ed.pecas()[sit.index('longo')]
            alvo = (a + b) / 2
        elif est:
            self.sel = est[0]
            alvo = self.ed.marcas[est[0]]['pos']
        else:
            alvo = 0.0
        larg = min(self.ed.duracao, VISTA_INICIAL_SEC) or 1.0
        v0 = min(max(0.0, alvo - larg / 2), max(0.0, self.ed.duracao - larg))
        self.vista = (v0, v0 + larg)
        self.cursor = alvo

    # ================================================================== mouse
    def _clique_geral(self, evento):
        L = self.c_geral.winfo_width()
        t = self._t(evento.x, L, 0, self.ed.duracao or 1.0)
        larg = self.vista[1] - self.vista[0]
        v0 = min(max(0.0, t - larg / 2), max(0.0, self.ed.duracao - larg))
        self.vista = (v0, v0 + larg)
        self.ir(t)

    def _marca_no_x(self, x):
        L = self.c_zoom.winfo_width()
        t0, t1 = self.vista
        perto = [(abs(self._x(m['pos'], L, t0, t1) - x), i) for i, m in enumerate(self.ed.marcas)
                 if t0 <= m['pos'] <= t1]
        perto = [p for p in perto if p[0] <= 7]
        return min(perto)[1] if perto else None

    def _clique_zoom(self, evento):
        i = self._marca_no_x(evento.x)
        if i is not None:
            self._fechar_caixa_nome()
            self.sel, self.arrastando = i, i
            self.redesenhar()
            return
        L = self.c_zoom.winfo_width()
        self.arrastando = None
        t = self._t(evento.x, L, *self.vista)
        guias = [p for p in self.ed.guias_discogs() + list(self.ed.sugestoes_som)
                 if abs(self._x(p, L, *self.vista) - evento.x) <= 6]
        if guias:
            t = min(guias, key=lambda p: abs(p - t))      # clicou numa guia: o cursor vai exatamente pra ela
        self.ir(t)

    def _arrasta_zoom(self, evento):
        if self.arrastando is None:
            return
        L = self.c_zoom.winfo_width()
        self.ed.mover(self.arrastando, self._t(evento.x, L, *self.vista))
        self.redesenhar()

    def _solta_zoom(self, evento):
        self.arrastando = None

    # ================================================================== som
    def tocar_pausar(self):
        if not self.tocador.disponivel:
            self._aviso_sem_som()
            return
        if self.tocador.tocando:
            self.tocador.pausar()
            self.cursor = self.tocador.posicao()
        elif not self.tocador.tocar(self.ed.arquivo, self.cursor):
            self._aviso_sem_som()
        self._botao_tocar()
        self.redesenhar()

    def ouvir_emenda(self):
        if not self.tocador.disponivel:
            self._aviso_sem_som()
            return
        i = self._marca_da_vez()
        if i is None:
            return
        p = self.ed.marcas[i]['pos']
        self.sel = i
        self.cursor = max(0.0, p - 5)
        self._mostrar(p)
        if not self.tocador.tocar(self.ed.arquivo, self.cursor, min(self.ed.duracao, p + 5)):
            self._aviso_sem_som()
        self._botao_tocar()
        self.redesenhar()

    def _aviso_sem_som(self):
        messagebox.showinfo("Sem som", f"Não dá pra tocar neste computador: {self.tocador.motivo}.",
                            parent=self.win)

    def _botao_tocar(self):
        self.b_tocar.config(text="⏸  Pausar" if self.tocador.tocando else "▶  Tocar")

    def _tique(self):
        if not self.win.winfo_exists():
            return
        if self.tocador.tocando or getattr(self, '_tocava', False):
            if self.tocador.tocando:
                self.cursor = self.tocador.posicao()
                self._mostrar(self.cursor)
            else:
                self.cursor = self.tocador.posicao()
            self._botao_tocar()
            self._desenhar_geral()
            self._desenhar_zoom()
            self.l_tempo.config(text=f"{mmss(self.cursor)} / {mmss(self.ed.duracao, False)}")
        self._tocava = self.tocador.tocando
        self._id_tique = self.win.after(TIQUE_MS, self._tique)

    # ================================================================== edição
    def _marca_da_vez(self):
        """A marca selecionada; sem seleção, a mais perto do cursor."""
        if self.sel is not None and self.sel < len(self.ed.marcas):
            return self.sel
        return self.ed.marca_mais_perto(self.cursor)

    def marcar(self):
        self._fechar_caixa_nome()
        pos = self.tocador.posicao() if self.tocador.tocando else self.cursor
        self.sel = self.ed.marcar(pos)
        self.redesenhar()

    def empurrar(self, seg):
        self._fechar_caixa_nome()
        i = self._marca_da_vez()
        if i is None:
            return
        self.sel = i
        p = self.ed.mover(i, self.ed.marcas[i]['pos'] + seg)
        self.cursor = p
        self._mostrar(p)
        self.redesenhar()

    def ao_silencio(self):
        self._fechar_caixa_nome()
        i = self._marca_da_vez()
        if i is None:
            return
        alvo = self.ed.silencio_mais_perto(self.ed.marcas[i]['pos'])
        if alvo is None:
            messagebox.showinfo("Sem silêncio perto", "Não há silêncio a até 15s desta marca.", parent=self.win)
            return
        self.sel = i
        p = self.ed.mover(i, alvo)
        self.ed.marcas[i]['tipo'] = 'silencio'
        self.cursor = p
        self._mostrar(p)
        self.redesenhar()

    def apagar(self):
        self._fechar_caixa_nome()
        i = self._marca_da_vez()
        if i is None:
            return
        self.ed.apagar(i)
        self.sel = None
        self.redesenhar()

    def _linha_escolhida(self, evento=None):
        sel = self.tabela.selection()
        if not sel:
            return
        if sel[0] == getattr(self, '_linha_atual', None):        # é a mesma (o programa re-selecionou)
            return
        self._linha_atual = sel[0]
        a, _ = self.ed.pecas()[int(sel[0])]
        self.ir(a + (0.0 if a == 0 else 0.5))

    def _editar_nome(self, evento):
        linha = self.tabela.identify_row(evento.y)
        col = self.tabela.identify_column(evento.x)
        if not linha or col != '#2':
            return
        x, y, larg, alt = self.tabela.bbox(linha, col)
        opcoes = [nome for _, nome in self.ed.candidatos_da_faixa(int(linha))]
        caixa = ttk.Combobox(self.tabela, font=('Segoe UI', 9), values=opcoes, height=12)
        caixa.insert(0, self.ed.nomes()[int(linha)])
        caixa.select_range(0, 'end')
        caixa.place(x=x, y=y, width=larg, height=alt)
        caixa.focus_set()

        feito = []

        def ok(e=None):
            if feito:
                return
            feito.append(1)
            self.ed.renomear(int(linha), caixa.get())
            caixa.destroy()
            self.redesenhar()

        def cancelar(e=None):
            feito.append(1)
            caixa.destroy()
            return 'break'
        caixa.bind('<Return>', ok)
        caixa.bind('<<ComboboxSelected>>', ok)
        def saiu(e=None):
            # a lista de nomes abre por cima e tira o foco da caixa: só vale o foco que foi pra outro lugar
            if feito or not caixa.winfo_exists():
                return
            try:
                foco = str(self.win.focus_get() or '')
            except (KeyError, tk.TclError):
                return                                    # foco na lista aberta (não é um widget do tkinter)
            if not (foco == str(caixa) or foco.startswith(str(caixa) + '.')):
                ok()
        caixa.bind('<FocusOut>', lambda e: self.win.after(150, saiu))
        caixa.bind('<Escape>', cancelar)
        self._caixa_nome = caixa
        self._caixa_ok = ok

    def _fechar_caixa_nome(self):
        """Antes de mudar os cortes, o nome que está sendo escrito vale pra linha em que foi aberto
        (depois os números das linhas mudam)."""
        caixa, ok = getattr(self, '_caixa_nome', None), getattr(self, '_caixa_ok', None)
        if caixa is not None and ok is not None:
            try:
                if caixa.winfo_exists():
                    ok()
            except tk.TclError:
                pass
        self._caixa_nome = self._caixa_ok = None

    def colar_nomes(self):
        """Uma caixa pra colar a lista de nomes (do Discogs, de um site, de um comentário)."""
        self._fechar_caixa_nome()
        jan = tk.Toplevel(self.win)
        jan.title("Colar nomes das músicas")
        jan.configure(bg=self.COLOR_BG)
        jan.transient(self.win)
        q = tk.Frame(jan, bg=self.COLOR_BG, padx=16, pady=14)
        q.pack(fill='both', expand=True)
        tk.Label(q, text=f"Cole os nomes, um por linha, na ordem do disco ({len(self.ed.marcas) + 1} pedaços). "
                         f"Número e tempo na frente (\"01 -\", \"3:12\") saem sozinhos.", font=('Segoe UI', 9),
                 bg=self.COLOR_BG, fg=self.COLOR_TEXT, wraplength=440, justify='left').pack(anchor='w')
        texto = tk.Text(q, width=60, height=14, font=('Segoe UI', 9))
        texto.pack(fill='both', expand=True, pady=8)
        texto.focus_set()
        rod = tk.Frame(q, bg=self.COLOR_BG)
        rod.pack(fill='x')

        def usar():
            self.ed.colar_nomes(texto.get('1.0', 'end'))
            jan.destroy()
            self.redesenhar()
        self._botao(rod, "Usar estes nomes", usar, primario=True).pack(side='right')
        self._botao(rod, "Cancelar", jan.destroy).pack(side='right', padx=8)
        self._janela_colar = (jan, texto, usar)
        return jan

    # ================================================================== fim
    def salvar(self):
        self._fechar_caixa_nome()
        faltam, sobram = self.ed.faltam(), self.ed.sobram()
        if faltam or sobram:
            q = (f"O Discogs tem {len(self.ed.oficiais)} músicas e há {len(self.ed.marcas) + 1} pedaços "
                 f"({'faltam' if faltam else 'sobram'} {faltam or sobram} corte(s)). Os nomes das faixas vão "
                 f"ficar como estão na tabela. Salvar assim mesmo?")
            if not messagebox.askyesno("Salvar cortes", q, parent=self.win):
                return
        self.tocador.pausar()
        try:
            r = self.ao_salvar(self.ed)
        except Exception as e:
            messagebox.showerror("Salvar cortes", f"Não deu pra salvar: {e}", parent=self.win)
            return
        if r is False:
            return          # o trabalho segue em segundo plano: quem chamou fecha com salvo() se der certo
        self.salvo()

    def salvo(self):
        """Salvou de vez: fecha sem perguntar (e sem o ao_fechar de quem desistiu)."""
        self.salvou = True
        self.fechar(perguntar=False)

    def fechar(self, perguntar=True):
        if perguntar and self.ed.mudou and not self.salvou:
            if not messagebox.askyesno("Conferir cortes", "Sair sem salvar as mudanças?", parent=self.win):
                return
        self.tocador.fechar()
        try:
            self.win.after_cancel(self._id_tique)
        except Exception:
            pass
        try:
            self.win.destroy()
        except Exception:
            pass
        if not self.salvou and self.ao_fechar:
            try:
                self.ao_fechar()
            except Exception:
                pass

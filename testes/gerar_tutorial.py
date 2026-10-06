"""
Gera o tutorial em PDF com fotos da janela de verdade (abre o programa no Xvfb).

    python testes/gerar_tutorial.py [saida.pdf]

Padrão: Tutorial_DiscoFacil_<versão>.pdf na pasta do programa.
Precisa de: tkinter, Xvfb (xvfb-run), ImageMagick (import), Pillow e reportlab.
"""
import os, sys, subprocess, time
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1400x1000x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import janela
from PIL import Image

FOTOS = tmp('tutorial', 'x')[:-2]


def esperar(root, seg=0.4):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


def recorte(root, w, nome, margem=0, extra=None):
    """Foto só da janela w (e opcionalmente unida com a área de extra, ex.: um menu)."""
    esperar(root, 0.5)
    tela = os.path.join(FOTOS, '_tela.png')
    subprocess.run(['import', '-window', 'root', tela], check=True)
    x, y = w.winfo_rootx(), w.winfo_rooty()
    x2, y2 = x + w.winfo_width(), y + w.winfo_height()
    if extra is not None:
        ex, ey = extra.winfo_rootx(), extra.winfo_rooty()
        x2 = max(x2, ex + extra.winfo_reqwidth()); y2 = max(y2, ey + extra.winfo_reqheight())
    img = Image.open(tela).crop((max(0, x - margem), max(0, y - margem), x2 + margem, y2 + margem))
    p = os.path.join(FOTOS, nome + '.png')
    img.save(p)
    return p


def janelas(w):
    """Todas as Toplevel abaixo de w (os popups do "?" nascem dentro do botão)."""
    saida = []
    for f in w.winfo_children():
        if f.winfo_class() == 'Toplevel':
            saida.append(f)
        saida += janelas(f)
    return saida


def botoes_ajuda(w):
    """Botões "?" dentro de w."""
    saida = []
    for f in w.winfo_children():
        try:
            if f.winfo_class() == 'Button' and f.cget('text') == '?':
                saida.append(f)
        except Exception:
            pass
        saida += botoes_ajuda(f)
    return saida


def foto_ajuda(root, botao, nome, onde='+640+20'):
    """Abre o popup do "?", tira a foto e fecha. Devolve (titulo, caminho)."""
    antes = set(map(str, janelas(root)))
    botao.invoke(); esperar(root, 0.3)
    novas = [j for j in janelas(root) if str(j) not in antes]
    if not novas:
        return None, None
    pop = novas[-1]
    pop.geometry(onde); esperar(root, 0.5)
    titulo = pop.title()
    p = recorte(root, pop, nome)
    pop.destroy(); esperar(root, 0.2)
    return titulo, p


def capturar():
    os.makedirs(FOTOS, exist_ok=True)
    fotos = {}
    root, app, main = janela.abrir()
    root.geometry('1000x820+0+0'); esperar(root, 1.0)
    # log de exemplo com caminho de Windows (as fotos não mostram a pasta de teste daqui)
    app._descarregar_log()
    esperar(root)
    app.progress_text.config(state='normal'); app.progress_text.delete('1.0', 'end')
    for linha in ('⚙ Configurações (início):', f'   Versão: DiscoFácil {__import__("versao").APP_VERSION}',
                  '   Pasta de saída: C:\\SOM', '   Bitrate mínimo: 80 kbps',
                  '   Confiança mínima pra baixar sem perguntar: 80%', '   Navegador dos cookies: automático',
                  '   Correções do ✂ Editar: guardadas em logs/correcoes_do_editor.txt',
                  '   Chaves: Discogs configurada · Groq não configurada · YouTube Data API não configurada',
                  '📝 Log desta rodada: C:\\SOM\\logs\\DiscoFacil_2026-10-03_20-00-00.log'):
        app.progress_text.insert('end', linha + '\n')
    app.log('➕ Na fila como próximo: https://www.youtube.com/watch?v=exemplo')
    app.status_line.config(text='▶ Baixando: Gloria Lynne - Gloria, Marty & Strings (Full Album)   ·   1 de 3  ·  2 na fila')
    esperar(root)
    fotos['principal'] = recorte(root, root, 'principal')
    # "?" do cabeçalho: como funciona
    _, fotos['ajuda_geral'] = foto_ajuda(root, botoes_ajuda(root)[0], 'ajuda_geral', '+520+20')
    # aviso de link
    app.video_entry.insert(0, 'https://www.youtube.com/@umcanal')
    app._on_url_change(); esperar(root)
    fotos['aviso'] = recorte(root, app.url_frame, 'aviso', margem=6)
    app.video_entry.delete(0, 'end'); app._on_url_change()
    # playlist
    app._select_mode('playlist', salvar=False); esperar(root)
    app.playlist_text.insert('1.0', 'https://www.youtube.com/playlist?list=PLexemplo1\nhttps://www.youtube.com/playlist?list=PLexemplo2')
    esperar(root)
    fotos['playlist'] = recorte(root, app.playlist_frame, 'playlist', margem=6)
    app.playlist_text.delete('1.0', 'end')
    app._select_mode('video', salvar=False); esperar(root)
    # menu do botão direito (de verdade)
    app.video_entry.insert(0, 'https://www.youtube.com/watch?v=exemplo')

    class Ev:
        widget = app.video_entry
        x_root = app.video_entry.winfo_rootx() + 220
        y_root = app.video_entry.winfo_rooty() + 20
    app.video_entry.selection_range(0, 'end')
    root.after(300, lambda: None)
    main._menu_de_contexto(Ev())
    menu = app.video_entry._menu_aberto
    esperar(root, 0.5)
    fotos['menu'] = recorte(root, app.url_frame, 'menu', margem=6, extra=menu)
    try:
        menu.unpost()
    except Exception:
        pass
    app.video_entry.delete(0, 'end')
    # log com linhas novas
    for i in range(40):
        app.log(f'   Faixa {i + 1}: corte em {i * 3}:{(i * 7) % 60:02d}.0')
    esperar(root)
    app.progress_text.yview_moveto(0.2); app.progress_text.event_generate('<Button-4>', x=5, y=5); esperar(root)
    for i in range(12):
        app.log(f'✓ Faixa {i + 1} salva')
    esperar(root, 0.5)
    fotos['log'] = recorte(root, app.progress_text.master, 'log', margem=4)
    app._log_ir_para_o_fim()
    # configurações
    cfg = main.SettingsWindow(root, app.config, app)
    cfg.window.geometry('640x700+20+20'); esperar(root, 0.8)
    cfg.output_path_var.set('C:\\SOM')        # só na foto: não salva
    esperar(root)
    fotos['config'] = recorte(root, cfg.window, 'config')
    for b in botoes_ajuda(cfg.window):
        try:
            if not b.winfo_ismapped():
                continue
        except Exception:
            continue
        tit, foto_ = foto_ajuda(root, b, '_ajuda_tmp')
        if tit == 'Confiança mínima':
            os.replace(foto_, os.path.join(FOTOS, 'ajuda_confianca.png'))
            fotos['ajuda_confianca'] = os.path.join(FOTOS, 'ajuda_confianca.png')
    def acha_nb(w):
        for f in w.winfo_children():
            if f.winfo_class() == 'TNotebook':
                return f
            r = acha_nb(f)
            if r is not None:
                return r
    nb = acha_nb(cfg.window)
    if nb is not None:
        nb.select(1); esperar(root, 0.6)
        fotos['config_chaves'] = recorte(root, cfg.window, 'config_chaves')
        for b in botoes_ajuda(cfg.window):
            if not b.winfo_ismapped():
                continue
            tit, foto_ = foto_ajuda(root, b, '_ajuda_tmp')
            if tit and tit.startswith('Discogs'):
                os.replace(foto_, os.path.join(FOTOS, 'ajuda_discogs.png'))
                fotos['ajuda_discogs'] = os.path.join(FOTOS, 'ajuda_discogs.png')
    cfg.window.destroy()
    # Buscar Playlists
    app._show_playlist_search(); esperar(root, 0.6)
    busca = [j for j in janelas(root) if 'playlists' in (j.title() or '').lower()]
    if busca:
        busca[-1].geometry('760x400+10+10'); esperar(root, 0.6)
        fotos['busca'] = recorte(root, busca[-1], 'busca')
        busca[-1].destroy()
    root.destroy()

    # fila guardada + pendências
    import fila_unica, pending_queue
    f = fila_unica.FilaUnica(janela.SAIDA_MUSICAS)
    for i, n in enumerate(['Wes Montgomery - Full House', 'Simone - Pedaço de Mim', 'Nico Assumpção - 1981']):
        f.adicionar('disco_unico', f'https://youtu.be/ex{i}', n)
    del f
    pq = pending_queue.PendingQueue(janela.SAIDA_MUSICAS)
    exemplos = [('nao_encontrado', 'Wes Montgomery (Jazz)', 0, 'Álbum não encontrado no Discogs'),
                ('baixa_confianca', 'Simone 1980 Pedaço de Mim (álbum completo)', 62,
                 'Confiança 62% abaixo do mínimo automático (80%)'),
                ('falha_corte', 'Nico Assumpção - Nico Assumpção (1981) Full Album', 91,
                 'Corte pelos silêncios achou 9 faixas, o Discogs tem 10')]
    for i, (k, tit, c, mot) in enumerate(exemplos):
        pq.add(kind=k, url=f'https://youtu.be/pend{i}', video_title=tit, confidence_pct=c, reason=mot)
    del pq
    root, app, main = janela.abrir(limpar=False)
    root.geometry('1000x820+0+0'); app._iniciar_trabalhador = lambda: None
    esperar(root, 1.4)
    w = getattr(app, '_janela_pergunta_fila', None)
    if w is not None:
        fotos['pergunta'] = recorte(root, w, 'pergunta')
        w._depois()
    esperar(root)
    fotos['botoes'] = recorte(root, app.action_frame, 'botoes', margem=6)
    # painel da fila
    app._mostrar_painel_fila(); esperar(root, 0.6)
    jf = getattr(app, '_janela_fila', None)
    if jf is not None:
        jf.geometry('620x330+10+10'); esperar(root, 0.6)
        fotos['fila'] = recorte(root, jf, 'fila')
        jf.destroy()
    app._ensure_acervo_and_queue()
    app._show_pending_queue(); esperar(root, 0.8)
    pend = None
    for x in root.winfo_children():
        if isinstance(x, main.tk.Toplevel) and x.winfo_exists() and 'ocê' in (x.title() or ''):
            pend = x
    if pend is None:
        tops = [x for x in root.winfo_children() if isinstance(x, main.tk.Toplevel) and x.winfo_exists()]
        pend = tops[-1] if tops else None
    if pend is not None:
        pend.geometry('+10+10'); esperar(root, 0.6)
        J = app._janela_pendentes
        filhos = J.tree.get_children()
        J.tree.selection_set(filhos[:1]); J.enfileirar()
        J.tree.selection_set(filhos[1:3]); J.tree.focus(filhos[2]); J._seleção_mudou()
        esperar(root, 0.4)
        fotos['pendentes'] = recorte(root, pend, 'pendentes')
        # caixinha "Corrigir busca"
        J.tree.selection_set(filhos[:1]); J.tree.focus(filhos[0]); J._seleção_mudou(); esperar(root)
        cx = J.corrigir_busca()
        cx._campos['Artista:'].delete(0, 'end'); cx._campos['Artista:'].insert(0, 'Wes Montgomery')
        cx._campos['Álbum:'].insert(0, 'Full House')
        cx.geometry('+60+120'); esperar(root, 0.6)
        fotos['corrigir'] = recorte(root, cx, 'corrigir')
        cx.destroy()
        # caixa "Informar tempos"
        J.tree.selection_set(filhos[2:3]); J.tree.focus(filhos[2]); J._seleção_mudou(); esperar(root)
        cx = J.informar_tempos()
        cx._texto.insert('1.0', '0:00 Luanne\n4:12 Kamba\n8:05 Coisa Nº 5\n12:40 Amphibious\n17:02 Orfeu')
        cx.geometry('+60+120'); esperar(root, 0.6)
        fotos['tempos'] = recorte(root, cx, 'tempos')
        cx.destroy()
        # tela "Conferir cortes" (✂ Editar), com um disco sintético de 10 músicas, 3 emendadas
        fotos.update(_foto_editor(root, app, main, J))
    log_arq = app.registro.caminho
    root.destroy()
    return fotos, log_arq


def _disco_ray():
    """O disco sintético do teste_editor: 10 músicas, 3 trocas sem pausa."""
    import numpy as np
    from sint import musica, silencio, fade, salvar, rng, SR

    def plana(seg):
        x = np.convolve(rng.standard_normal(int(seg * SR)), np.ones(8) / 8, 'same')
        return 0.3 * x / np.std(x)
    dur = [124, 205, 180, 256, 330, 290, 150, 160, 200, 190]
    emend = (2, 3, 6)
    nomes = ['Busted', 'Where Can I Go?', 'Born To Be Blue', 'That Lucky Old Sun', "Ol' Man River",
             'In The Evening', 'A Stranger In Town', "Ol' Man Time", 'Over The Rainbow', "You'll Never Walk Alone"]
    partes = []
    for i, d in enumerate(dur):
        if i in emend or (i - 1) in emend:
            partes.append(plana(d) if (i in emend or i == len(dur) - 1)
                          else np.concatenate([plana(d - 1), fade(musica(1))]))
            if i not in emend and i < len(dur) - 1:
                partes.append(silencio(2.0))
        elif i == len(dur) - 1:
            partes.append(musica(d))
        else:
            partes += [musica(d - 1), fade(musica(1)), silencio(2.0)]
    arq = salvar(np.concatenate(partes), 'tutorial_ray.wav')
    cad = [d + (2 if i not in emend and i < len(dur) - 1 else 0) for i, d in enumerate(dur)]
    return arq, [{'title': n, 'duration': c} for n, c in zip(nomes, cad)]


def _foto_editor(root, app, main, J):
    import edicao_cortes as EC
    from tocador import TocadorFalso
    fotos = {}
    arq, faixas = _disco_ray()
    url = 'https://www.youtube.com/watch?v=RayCharles63'
    app.pending_queue.add(kind='falha_corte', url=url,
                          video_title='Ray Charles - Ingredients In A Recipe For Soul -1963 (FULL ALBUM)',
                          title_artist='Ray Charles', title_album='Ingredients In A Recipe For Soul',
                          confidence_pct=100, reason='Corte pelos silêncios achou 7 faixas, o Discogs tem 10',
                          discogs_data={'title': 'Ingredients In A Recipe For Soul', 'artists': ['Ray Charles'],
                                        'tracks': faixas})
    EC.guardar_audio(app.config.get_output_directory(), url, arq)
    # sem rede: o "vídeo" dos exemplos (o segundo tem capítulos, como muitos vídeos de disco)
    inicios = [0.0]
    for f_ in faixas[:-1]:
        inicios.append(inicios[-1] + f_['duration'])
    dur = inicios[-1] + faixas[-1]['duration']
    url2 = 'https://www.youtube.com/watch?v=RuthBrown57'
    infos = {url2: {'title': 'Ruth Brown - Sotfly (FULL ALBUM)', 'duration': dur, 'description': '',
                    'chapters': [{'title': n, 'start_time': a, 'end_time': b} for n, a, b in
                                 zip(['Softly', 'Love Has Joined Us Together', 'Mean Mean Man', 'Mambo Baby',
                                      'Oh What A Dream', 'Lucky Lips', 'Teardrops From My Eyes', '5-10-15 Hours',
                                      'Wild Wild Young Men', 'Mama He Treats Your Daughter Mean'],
                                     inicios, inicios[1:] + [dur])]}}
    app.downloader.get_video_info = lambda u, *a, **k: infos.get(u, {})
    app.downloader.comentarios = lambda u, *a, **k: []
    app._tocador_teste = TocadorFalso()

    def abrir(item):
        app._janela_editor = None
        app.abrir_editor_pendencia(item)
        for _ in range(600):
            esperar(root, 0.1)
            if getattr(app, '_janela_editor', None) is not None:
                break
        je = app._janela_editor
        if je is not None:
            je.win.geometry('1360x800+0+0'); esperar(root, 1.0)
        return je

    novo = [i for i in app.pending_queue.items if i.get('url') == url]
    je = abrir(novo[0]) if novo else None
    if je is not None:
        # exemplo do roxo: onde o som muda dentro da faixa 3 (ilustração)
        a3, b3 = je.ed.pecas()[2]
        je.ed.sugestoes_som = [a3 + (b3 - a3) * 0.55]
        je.redesenhar(); esperar(root, 0.4)
        fotos['editor'] = recorte(root, je.win, 'editor')
        je.ed.mudou = False
        je.fechar(perguntar=False)
        esperar(root, 0.3)
    # disco sem Discogs confirmado: título do vídeo e capítulos
    app.pending_queue.add(kind='baixa_confianca', url=url2, video_title='Ruth Brown - Sotfly (FULL ALBUM)',
                          title_artist='Ruth Brown', title_album='Sotfly', confidence_pct=0,
                          reason='Confiança 0% abaixo do mínimo automático (60%)',
                          discogs_data={'title': 'Zen Garden', 'artists': ['Peaks Iration'],
                                        'tracks': [{'title': f'Zen {k}', 'duration': 0} for k in range(6)]})
    EC.guardar_audio(app.config.get_output_directory(), url2, arq)
    novo = [i for i in app.pending_queue.items if i.get('url') == url2]
    je = abrir(novo[0]) if novo else None
    if je is not None:
        je.v_album.set('Softly'); je.v_ano.set('1957')
        bb = je.tabela.bbox('1', '#2')
        je.redesenhar(); esperar(root, 0.4)
        fotos['editor_sem_discogs'] = recorte(root, je.win, 'editor_sem_discogs')
        je.ed.mudou = False
        je.fechar(perguntar=False)
        esperar(root, 0.3)
    return fotos


def montar_pdf(fotos, destino, versao):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
                                    PageBreak, KeepTogether)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont('DV', '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))
    pdfmetrics.registerFont(TTFont('DVB', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    ROXO = HexColor('#4F46E5'); CINZA = HexColor('#64748B'); TXT = HexColor('#1E293B')
    st_t = ParagraphStyle('t', fontName='DVB', fontSize=15, textColor=ROXO, spaceBefore=6, spaceAfter=8)
    st_p = ParagraphStyle('p', fontName='DV', fontSize=10, leading=14.5, textColor=TXT, spaceAfter=6)
    st_l = ParagraphStyle('l', parent=st_p, leftIndent=12, bulletIndent=2)
    st_n = ParagraphStyle('n', parent=st_p, fontSize=8.5, textColor=CINZA)
    larg = A4[0] - 4 * cm

    def img(nome, maxw=larg, maxh=12 * cm):
        p = fotos.get(nome)
        if not p:
            return Spacer(1, 2)
        w, h = Image.open(p).size
        esc = min(maxw / w, maxh / h)
        return RLImage(p, w * esc, h * esc)

    def P(t): return Paragraph(t, st_p)
    def L(t): return Paragraph(t, st_l, bulletText='•')

    def rodape(c, d):
        c.saveState(); c.setFont('DV', 8); c.setFillColor(CINZA)
        c.drawString(2 * cm, 1.2 * cm, f'DiscoFácil {versao} · Tutorial')
        c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f'página {d.page}')
        c.restoreState()

    def capa(c, d):
        c.saveState(); c.setFillColor(ROXO); c.rect(0, A4[1] - 9 * cm, A4[0], 9 * cm, fill=1, stroke=0)
        c.setFillColor(HexColor('#FFFFFF')); c.setFont('DVB', 34); c.drawString(2 * cm, A4[1] - 5 * cm, 'DiscoFácil')
        c.setFont('DV', 14); c.drawString(2 * cm, A4[1] - 6.2 * cm, f'Tutorial · versão {versao}')
        c.setFont('DV', 10); c.drawString(2 * cm, A4[1] - 7.2 * cm,
                                          'Álbuns do YouTube separados em faixas')
        c.restoreState(); rodape(c, d)

    from reportlab.platypus import Table, TableStyle
    pdfmetrics.registerFont(TTFont('DVM', '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf'))
    st_s = ParagraphStyle('s', fontName='DVB', fontSize=11.5, textColor=TXT, spaceBefore=8, spaceAfter=4)
    st_c = ParagraphStyle('c', parent=st_p, fontSize=9, leading=12.5, spaceAfter=0)
    st_m = ParagraphStyle('m', parent=st_p, fontName='DVM', fontSize=8.5, leading=12, spaceAfter=0)
    st_d = ParagraphStyle('d', parent=st_p, backColor=HexColor('#EEF2FF'), borderPadding=(6, 8, 6, 8),
                          leftIndent=8, rightIndent=8, spaceBefore=6, spaceAfter=10)
    def T(t): return Paragraph(t, st_t)
    def S(t): return Paragraph(t, st_s)
    def D(t): return Paragraph('<b>Dica:</b> ' + t, st_d)

    def tabela(linhas, larguras, cabecalho=True):
        dados = [[Paragraph(c, st_c) for c in l] for l in linhas]
        t = Table(dados, colWidths=larguras, repeatRows=1 if cabecalho else 0)
        estilo = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), 0.4, HexColor('#CBD5E1')),
                  ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]
        if cabecalho:
            estilo.append(('BACKGROUND', (0, 0), (-1, 0), HexColor('#E0E7FF')))
        t.setStyle(TableStyle(estilo))
        return t

    h = []
    # ------------------------------------------------------------ capa
    h.append(Spacer(1, 8.5 * cm))
    h.append(S('O que o programa faz'))
    h.append(P('Você cola o link de um disco inteiro que está no YouTube. O DiscoFácil descobre qual disco é '
               'no <b>Discogs</b> (um catálogo gratuito de discos na internet), baixa o áudio, separa as '
               'músicas e grava cada uma num arquivo MP3 com o nome da música, o número da faixa, o artista, '
               'o ano e a capa.'))
    h.append(S('O caminho, em 4 passos'))
    h.append(L('<b>Uma vez só:</b> em Configurações, escolha a pasta dos discos e cole a chave do Discogs '
               '(seção 1).'))
    h.append(L('Escolha o modo (Vídeo Único, Canal Inteiro ou Playlist Completa) e cole o link (seção 4).'))
    h.append(L('Clique em <b>Enfileirar</b>. O resto é sozinho: baixar, identificar, cortar, gravar.'))
    h.append(L('O que o programa não tiver certeza vai pra <b>Precisam de você</b>, pra você decidir '
               '(seção 7). Ele prefere perguntar a gravar errado.'))
    h.append(D('cada item da janela tem um botão <b>?</b> ao lado. Clique nele pra ver a explicação '
               'daquele item, sem sair do programa (seção 2).'))
    h.append(PageBreak())

    # ------------------------------------------------------------ 1. configurações
    h.append(T('1. Primeira vez: Configurações'))
    h.append(P('Clique em <b>Configurações</b>, no alto à direita. São duas abas.'))
    h.append(S('Aba "Pasta de Saída"'))
    h.append(img('config', maxh=11 * cm))
    h.append(tabela([
        ['Campo', 'O que é', 'O que colocar'],
        ['Onde as músicas serão salvas', 'A pasta dos discos. Cada disco vira uma subpasta '
         '"Artista - Álbum (Ano)". Os registros de cada uso ficam na subpasta <b>logs</b>.',
         'Qualquer pasta com espaço, ex.: C:\\SOM'],
        ['Bitrate mínimo (kbps)', 'A qualidade mínima do áudio. Abaixo disso o disco é pulado, em vez de '
         'gravado com som ruim.', '<b>80</b> (padrão). O YouTube costuma ter cerca de 130. Valor alto '
         'demais faz muito disco ser pulado.'],
        ['Confiança mínima (%)', 'A nota (0 a 100) de "é este mesmo o disco?". Abaixo dela o programa não '
         'baixa sozinho: pergunta em Precisam de você.', '<b>80</b> (padrão). Com 60 ele baixa mais sozinho, '
         'com mais risco de pegar o disco errado.'],
        ['Usar cookies do navegador', 'Usa o seu login do YouTube no navegador. Sem isso o YouTube às vezes '
         'só entrega áudio de qualidade baixa.', '<b>automático</b>, e deixe um navegador com login no '
         'YouTube.'],
        ['Guardar as correções feitas no ✂ Editar', 'Anota o que o programa sugeriu e o que você acertou no '
         'editor (seção 8), pra ajustar os cortes automáticos.', '<b>Marcado</b> (padrão). Desmarque quando o '
         'ajuste estiver pronto.'],
    ], [3.6 * cm, 7.3 * cm, 6.1 * cm]))
    h.append(PageBreak())
    h.append(S('Aba "Chaves de API"'))
    h.append(P('Uma "chave" é uma senha que o site dá de graça pra programas como este consultarem o catálogo. '
               'Só a do Discogs é obrigatória.'))
    h.append(img('config_chaves', maxh=8.5 * cm))
    h.append(tabela([
        ['Chave', 'Pra que serve', 'Precisa?'],
        ['<b>Discogs</b>', 'Identificar o disco: nomes das músicas, artista, ano e capa vêm de lá.',
         '<b>Sim.</b> Sem ela nenhum disco é identificado.'],
        ['Groq', 'Inteligência artificial que dá palpites quando o título do vídeo é confuso (ex.: não diz o '
         'nome do disco). O Discogs sempre confere o palpite.', 'Não. Ajuda em casos difíceis.'],
        ['YouTube Data API', 'Buscar Playlists (seção 6) e listar os vídeos de um canal mais rápido.',
         'Só pra usar Buscar Playlists.'],
    ], [3.2 * cm, 9 * cm, 4.8 * cm]))
    h.append(S('Como conseguir a chave do Discogs'))
    h.append(P('O <b>?</b> ao lado do campo explica, e o link embaixo do campo já abre a página certa:'))
    h.append(img('ajuda_discogs', maxh=7 * cm))
    h.append(P('Clique em <b>Salvar</b>. As configurações aparecem no log; as chaves aparecem só como '
               '"configurada", nunca o valor.'))
    h.append(PageBreak())

    # ------------------------------------------------------------ 2. ajuda
    h.append(T('2. Os botões de ajuda (?)'))
    h.append(P('Todo <b>?</b> abre uma explicação curta do item ao lado. Feche com <b>Fechar</b> ou Esc. O '
               '<b>?</b> do alto da janela explica o programa todo:'))
    h.append(img('ajuda_geral', maxh=12 * cm))
    h.append(P('Nas Configurações, o <b>?</b> de cada campo diz o que ele faz e o valor recomendado. Exemplo, '
               'o da confiança mínima:'))
    h.append(img('ajuda_confianca', maxh=7.5 * cm))
    h.append(PageBreak())

    # ------------------------------------------------------------ 3. janela principal
    h.append(T('3. A janela principal'))
    h.append(img('principal', maxh=12.5 * cm))
    h.append(tabela([
        ['Parte', 'Pra que serve'],
        ['<b>?</b> · Fila · Buscar Playlists · Configurações', 'Ajuda geral; o que está esperando a '
         'vez (seção 5); achar playlists de um artista (seção 6); configurações (seção 1).'],
        ['Modo de processamento', 'Que tipo de link você vai colar (seção 4).'],
        ['Campo do link', 'Onde se cola o endereço do YouTube. Enter = Enfileirar.'],
        ['Copiar Log', 'Copia todo o registro da tela, pra colar numa mensagem.'],
        ['Abrir Pasta', 'Abre a pasta dos discos.'],
        ['Pausar fila / Retomar fila', 'Pausar termina o disco atual e para. Retomar continua de onde parou.'],
        ['Precisam de você (N)', 'Os discos que esperam a sua decisão (seção 7).'],
        ['✂ Editar disco', 'Ouvir e acertar os cortes de um disco que já está na pasta (seção 8).'],
        ['Enfileirar', 'Põe o link na fila. Os discos são feitos um de cada vez, na ordem.'],
        ['Progresso', 'A linha de cima diz o que está sendo feito e quanto falta. Embaixo, o registro de cada '
         'passo: <font color="#16A34A">verde</font> = deu certo, <font color="#D97706">laranja</font> = '
         'aviso, <font color="#DC2626">vermelho</font> = erro.'],
    ], [5.2 * cm, 11.8 * cm]))
    h.append(PageBreak())

    # ------------------------------------------------------------ 4. modos e links
    h.append(T('4. Escolher o modo e colar o link'))
    h.append(tabela([
        ['Modo', 'Quando usar', 'Link parecido com'],
        ['Vídeo Único', 'Um vídeo com o disco inteiro (o título costuma ter "Full Album").',
         'youtube.com/watch?v=...'],
        ['Canal Inteiro', 'Todos os discos inteiros de um canal. Pode levar horas.', 'youtube.com/@nomedocanal'],
        ['Playlist Completa', 'Um disco em que cada vídeo é uma música. Pode colar várias playlists, uma por '
         'linha.', 'youtube.com/playlist?list=...'],
    ], [3.3 * cm, 7.9 * cm, 5.8 * cm]))
    h.append(Spacer(1, 6))
    h.append(P('Cole o link e clique em <b>Enfileirar</b> (ou Enter). O link sai do campo assim que entra na '
               'fila. Se o link não combinar com o modo, o programa avisa e oferece trocar de modo:'))
    h.append(img('aviso', maxh=3.5 * cm))
    h.append(P('No modo Playlist, só saem do campo as playlists que entraram na fila; as que deram erro ficam, '
               'com o motivo.'))
    h.append(img('playlist', maxh=4.2 * cm))
    h.append(S('Botão direito do mouse'))
    h.append(P('Nos campos de texto: <b>Colar</b>, <b>Copiar</b>, <b>Selecionar tudo</b> e <b>Limpar</b>. No log: '
               'Copiar e Selecionar tudo.'))
    h.append(img('menu', maxh=4.5 * cm))
    h.append(PageBreak())

    # ------------------------------------------------------------ 5. fila
    h.append(T('5. Acompanhar e controlar a fila'))
    h.append(P('Pra ler algo lá atrás no log, role pra cima: ele fica parado e aparece <b>↓ N linhas novas</b>. '
               'Clique nele (ou role até o fim) pra voltar a acompanhar.'))
    h.append(img('log', maxh=6 * cm))
    h.append(S('Fila'))
    h.append(P('Mostra o que ainda vai ser feito, na ordem. Pra desistir de algum: marque e clique em '
               '<b>Tirar da lista</b>.'))
    h.append(img('fila', maxh=7 * cm))
    h.append(S('A fila fica guardada'))
    h.append(P('Pode fechar o programa no meio. Na próxima vez ele pergunta se continua. <b>Depois</b> não perde '
               'nada: o botão <b>Retomar (N)</b> fica na linha de botões.'))
    h.append(img('pergunta', maxh=3.6 * cm))
    h.append(img('botoes', maxh=2 * cm))
    h.append(D('enquanto um disco é cortado, o próximo da fila já vai sendo baixado. Cada disco leva poucos '
               'minutos.'))
    h.append(PageBreak())

    # ------------------------------------------------------------ 6. buscar playlists + resultado
    h.append(T('6. Buscar Playlists'))
    h.append(P('Pra quando o disco não está num vídeo só, mas numa playlist (uma música por vídeo). Digite o '
               'artista (e o álbum, se quiser) e clique em <b>Buscar</b>. Marque as playlists certas e clique em '
               '<b>Adicionar à lista</b>: elas vão pro campo do modo Playlist Completa. Daí é só Enfileirar. '
               'Precisa da chave do YouTube (seção 1).'))
    h.append(img('busca', maxh=7 * cm))
    h.append(T('O que fica na pasta'))
    h.append(Paragraph('C:\\SOM\\Neco - Coquetel Bossa Nova (1963)\\<br/>'
                       '&nbsp;&nbsp;&nbsp;01 - Jogado Fora.mp3<br/>'
                       '&nbsp;&nbsp;&nbsp;02 - Você.mp3<br/>'
                       '&nbsp;&nbsp;&nbsp;...<br/>'
                       '&nbsp;&nbsp;&nbsp;cover.jpg', st_m))
    h.append(Spacer(1, 6))
    h.append(L('Cada MP3 leva nome, número, artista, álbum, ano, gênero e capa. Aparecem no Windows Explorer '
               'e em qualquer tocador.'))
    h.append(L('<b>Disco que você já tem</b> (baixado antes pelo programa) é pulado: o log diz "já está no '
               'acervo".'))
    h.append(L('<b>"Track 1, Track 2..."</b> no lugar dos nomes: o programa não conseguiu confirmar qual música '
               'é cada pedaço. Ele prefere número a nome errado.'))
    h.append(L('<b>Faixas "a conferir"</b>: quando o nome saiu pela ordem do disco, ou músicas emendadas '
               'foram separadas pela duração, o log diz quais faixas ouvir.'))
    h.append(L('<b>Disco sem as durações no Discogs</b>: o programa procura as durações no Deezer e no iTunes '
               '(sem precisar de chave). Os nomes continuam os do Discogs.'))
    h.append(L('<b>Músicas sem pausa entre elas</b>, ou sem durações em lugar nenhum: o programa procura nos '
               'comentários do vídeo uma lista com os tempos (muita gente posta). Só usa se for a lista deste '
               'disco, conferida com o Discogs e com as pausas do áudio.'))
    h.append(L('<b>Corte no lugar errado?</b> Use <b>✂ Editar disco</b> (seção 8). <b>Disco errado?</b> Apague '
               'a pasta e mande o arquivo de log (seção 9).'))
    h.append(PageBreak())

    # ------------------------------------------------------------ 7. precisam de você
    h.append(T('7. Precisam de você'))
    h.append(P('Discos que o programa não quis decidir sozinho. Nada foi gravado errado: ele espera você.'))
    h.append(img('pendentes', maxh=8.5 * cm))
    h.append(tabela([
        ['Motivo', 'O que quer dizer', 'O que fazer'],
        ['Não achado no Discogs', 'A busca não achou o disco, quase sempre porque o título do vídeo não diz '
         'o nome dele direito.', '<b>Corrigir busca</b> com o artista e o álbum certos. Ou <b>Enfileirar</b>: '
         'baixa assim mesmo, com os nomes do vídeo ou "Track N".'],
        ['Confiança baixa', 'Achou um disco, mas não tem certeza de que é este.', 'Abra o vídeo (▶) e confira. '
         'Se for o certo, <b>Enfileirar</b>.'],
        ['Corte não bateu', 'O disco é este, mas as músicas não se separaram como o Discogs diz.',
         '<b>Enfileirar</b> = processar assim mesmo: as músicas emendadas, sem pausa, são separadas pela '
         'duração e saem marcadas "a conferir". Ou <b>✂ Editar</b>: você ouve e acerta os cortes (seção 8). '
         'Se faltar pausa demais, continua aqui: use <b>✂ Editar</b>, <b>Informar tempos</b> ou <b>Buscar '
         'outra versão</b> do vídeo.'],
        ['Talvez outro disco', 'O áudio não combina com o disco achado: pode ser outra edição.',
         '<b>Corrigir busca</b> ou <b>Buscar outra versão</b>.'],
        ['Download falhou', 'O vídeo saiu do ar, ficou privado ou bloqueado.', '<b>Buscar outra versão</b>.'],
        ['Discogs não respondeu', 'O Discogs limitou os pedidos por um tempo.', 'Nada: volta sozinho pra fila '
         'em 10 minutos (até 3 vezes).'],
    ], [3.3 * cm, 6.4 * cm, 7.3 * cm]))
    h.append(PageBreak())
    h.append(S('Como usar a lista'))
    h.append(L('<b>Selecionar</b>: clique; Ctrl+clique (um a um); Shift+clique (um trecho); <b>Selecionar '
               'tudo</b> ou <b>Todos com este motivo</b>.'))
    h.append(L('<b>Filtrar</b> pelo motivo e <b>buscar</b> por qualquer parte do título.'))
    h.append(L('<b>▶ abrir</b> (ou duplo clique) abre o vídeo no navegador. Embaixo da tabela aparece o motivo '
               'completo da linha.'))
    h.append(L('<b>Remover</b>: vai pra <b>Descartados</b>, de onde dá pra recuperar.'))
    h.append(L('<b>✂ Editar</b> (seção 8), <b>Informar tempos</b> e <b>Corrigir busca</b> (abaixo) valem pra um '
               'disco selecionado.'))
    h.append(L('Uma ampulheta na frente do título = já está na fila.'))
    h.append(S('Informar tempos'))
    h.append(P('Pra quando você faz questão de um disco que o programa não conseguiu separar sozinho. Cole a '
               'lista das músicas com o tempo de cada uma, uma por linha: o início ("0:00 Nome", "3:12 Nome"...) '
               'ou a duração ("Nome 3:12"). Dá pra copiar de um comentário do vídeo, do Discogs ou de um site. '
               'O disco entra na fila e é cortado nesses tempos, ajustados à pausa mais próxima.'))
    h.append(img('tempos', maxh=6 * cm))
    h.append(S('Corrigir busca'))
    h.append(P('Digite o artista e o álbum como aparecem no Discogs (vale abrir discogs.com e procurar). A busca '
               'é refeita e o disco entra na fila.'))
    h.append(img('corrigir', maxh=3.2 * cm))
    h.append(Spacer(1, 6))

    # ------------------------------------------------------------ 8. conferir cortes
    h.append(PageBreak())
    h.append(T('8. Ouvir e acertar os cortes (✂ Editar)'))
    h.append(P('Abre pelo botão <b>✂ Editar</b> de "Precisam de você" ou pelo <b>✂ Editar disco</b> da janela '
               'principal. Mostra o disco inteiro desenhado, com os cortes que o programa achou; você ouve, '
               'confere e acerta.'))
    h.append(img('editor', maxh=10.5 * cm))
    h.append(tabela([
        ['Parte', 'Pra que serve'],
        ['Desenho de cima', 'O disco inteiro. Clique num ponto pra ir até ele. O retângulo é o trecho ampliado.'],
        ['Desenho de baixo', 'O trecho ampliado. Cinza = pausa. Cortes: <font color="#4F46E5">azul</font> = '
         'numa pausa; <font color="#D97706">laranja tracejado</font> = estimado pela duração (ouça esses); '
         '<font color="#0D9488">verde</font> = marcado por você. Clique pra pôr o cursor ali.'],
        ['▶ Tocar / Pausar', 'Toca a partir do cursor, até o fim do disco se quiser (tecla: espaço).'],
        ['◀ marca · marca ▶', 'Leva o cursor ao corte anterior ou ao próximo (Ctrl+← / Ctrl+→).'],
        ['◀◀ 10s · 10s ▶▶ · início · fim', 'Volta ou avança 10 s; os dois botões das pontas vão ao começo e ao fim do disco (← / → andam 1 s).'],
        ['✂ Marcar corte', 'Põe um corte onde está o cursor (tecla M). Se já houver um a menos de 2 s, ele muda '
         'de lugar.'],
        ['Ouvir a emenda', 'Toca 5 s antes e 5 s depois do corte escolhido (tecla E).'],
        ['⇤ 0,5s · 0,5s ⇥', 'Empurra o corte escolhido meio segundo.'],
        ['Ao silêncio mais perto', 'Leva o corte à pausa mais próxima.'],
        ['Apagar marca', 'Tira o corte escolhido: as duas músicas viram uma (tecla Del).'],
        ['Tabela', 'As músicas com início e duração; a coluna Discogs é a duração que o Discogs dá. Clique '
         'pra ir à música.'],
        ['Nome (duplo clique)', 'Escreva outro, ou escolha na lista os nomes achados no Discogs, nos capítulos, '
         'na descrição e nos comentários do vídeo.'],
        ['Colar nomes', 'Cole a lista inteira (de um site, do Discogs, de um comentário), um nome por linha: '
         'número e tempo na frente saem sozinhos.'],
    ], [4.2 * cm, 12.8 * cm]))
    h.append(P('Em cima da tabela aparece se falta ou sobra corte (a música longa demais fica em vermelho) e '
               'quantos estão estimados.'))
    h.append(S('As guias: ajudam a achar o corte, não cortam nada'))
    h.append(L('<font color="#A16207"><b>Amarelo</b></font>: onde o Discogs poria cada corte, somando as '
               'durações das músicas (e a duração de cada uma, em cima). Um tracinho amarelo sem corte perto '
               'costuma ser o corte que falta.'))
    h.append(L('<font color="#7C3AED"><b>Roxo</b></font>: onde o som muda de repente, sem pausa (outro '
               'instrumento, outro andamento). Pode ser a troca de duas músicas emendadas - ou só um solo. '
               'Ouça ali. Clicar perto de uma guia leva o cursor exatamente pra ela.'))
    h.append(S('Você tem a última palavra'))
    h.append(P('Se você apagar um corte, juntar músicas ou deixar menos faixas do que o Discogs diz, o disco sai '
               'assim, com os nomes da tabela. Os nomes acompanham os cortes: juntar duas músicas dá "A / B"; '
               'um corte no meio de uma dá "A (2)"; marcar de novo um corte apagado devolve os nomes.'))
    h.append(S('Disco que o Discogs não confirmou'))
    h.append(P('Em "Confiança baixa", "Não achado" ou "Talvez outro disco", o palpite do Discogs pode ser outro '
               'disco, então ele não entra. O artista, o álbum e o ano vêm do título do vídeo, num quadro '
               'amarelo pra você conferir (o título tinha "Sotfly"; corrija pra "Softly"). Os cortes e os nomes '
               'vêm dos capítulos, da descrição ou de um comentário do vídeo, se houver.'))
    h.append(img('editor_sem_discogs', maxh=9 * cm))
    salvar_ = [S('Salvar')]
    salvar_.append(L('<b>Em "Precisam de você"</b>: o disco entra na fila e é cortado exatamente onde você marcou, '
               'com os nomes da tabela. O áudio já está guardado, não baixa de novo.'))
    salvar_.append(L('<b>Disco já cortado</b> (✂ Editar disco: escolha a pasta do disco): a pasta é regravada nos '
               'cortes novos, com as mesmas tags e a capa. Os arquivos de antes ficam em '
               '<b>.audios_pasta_pendencia\\antes_da_edicao</b>, na pasta dos discos.'))
    salvar_.append(L('<b>As suas correções</b> (o que o programa sugeriu e o que você deixou) ficam anotadas em '
               '<b>logs\\correcoes_do_editor.txt</b>. De tempos em tempos, mande esse arquivo na conversa de '
               'suporte: é com ele que os cortes automáticos são ajustados. Dá pra desligar nas Configurações.'))
    salvar_.append(D('o som sai pelo alto-falante do computador. Se ele não tocar, a tela diz por quê e continua '
                     'funcionando para ver e marcar.'))
    h.append(KeepTogether(salvar_))
    h.append(Spacer(1, 12))

    # ------------------------------------------------------------ 9. problemas
    h.append(T('9. Quando algo der errado'))
    h.append(P('Cada vez que o programa abre, ele grava um arquivo de log em <b>&lt;pasta dos discos&gt;\\logs\\</b>, '
               'com nome <b>DiscoFacil_&lt;data&gt;_&lt;hora&gt;.log</b>. O caminho aparece no começo do log da '
               'tela.'))
    h.append(P('<b>É só anexar esse arquivo</b> na conversa de suporte: ele tem a versão, as configurações, '
               'cada disco com a edição escolhida, o motivo de cada recusa e o local de cada erro. As chaves '
               '(Discogs, Groq, YouTube) nunca aparecem nele.'))
    h.append(L('<b>Áudio com qualidade baixa ou "bloqueado"</b>: confira os cookies (seção 1) e se o navegador '
               'está com login no YouTube.'))
    h.append(L('<b>Primeira abertura num computador novo</b>: o programa instala sozinho o Deno (~40 MB), que o '
               'YouTube exige pra liberar o áudio de boa qualidade. A fila espera a instalação (até 10 min).'))
    h.append(Spacer(1, 12))
    h.append(Paragraph(f'DiscoFácil {versao} · Elaborado por Glauco - Barra do Piraí - RJ', st_n))

    doc = SimpleDocTemplate(destino, pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=1.8 * cm, bottomMargin=2 * cm,
                            title=f'DiscoFácil {versao} - Tutorial', author='DiscoFácil')
    doc.build(h, onFirstPage=capa, onLaterPages=rodape)
    return destino


if __name__ == '__main__':
    import versao
    destino = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(PROJ, f'Tutorial_DiscoFacil_{versao.APP_VERSION}.pdf')
    fotos, _ = capturar()
    print('fotos:', sorted(fotos))
    print('pdf:', montar_pdf(fotos, destino, versao.APP_VERSION))

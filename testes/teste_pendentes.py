"""
12.3 - janela "Precisam de você": tabela, seleção, filtro, busca, ações em lote,
YouTube por linha, Descartados, uma gravação por ação.
"""
import os, sys, subprocess, time
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1400x1000x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import janela

FOTOS = os.environ.get('DF_FOTOS')


def esperar(root, seg=0.35):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


def foto(root, w, nome):
    if FOTOS:
        os.makedirs(FOTOS, exist_ok=True)
        janela.foto(root, os.path.join(FOTOS, nome + '.png'))


root, app, main = janela.abrir()
import pending_queue, janela_pendentes as JP
pq = app.pending_queue
exemplos = [
    ('nao_encontrado', 'Wes Montgomery (Jazz)', 0, 'Álbum não encontrado no Discogs', 'video'),
    ('baixa_confianca', 'Simone 1980 Pedaço de Mim', 62, 'Confiança 62% abaixo do mínimo (80%)', 'video'),
    ('falha_corte', 'Nico Assumpção (1981) Full Album', 91, 'Corte achou 9 faixas, Discogs tem 10', 'video'),
    ('nao_encontrado', 'Art Farmer - Live', 0, 'Álbum não encontrado no Discogs', 'video'),
    ('falha_download', 'Steely Dan - Aja', 88, 'HTTP 403', 'playlist'),
    ('baixa_confianca', 'Gloria Lynne - Gloria, Marty & Strings', 70, 'Confiança 70%', 'video'),
    ('nao_encontrado', 'Yusef Lateef - Eastern Sounds', 0, 'Álbum não encontrado no Discogs', 'video'),
    ('falha_corte', 'Frank - Amy Winehouse', 95, 'Faixa 2 com duração errada', 'video'),
]
for i, (k, tit, c, mot, st) in enumerate(exemplos):
    pq.add(kind=k, url=f'https://youtu.be/p{i}', video_title=tit, confidence_pct=c, reason=mot, source_type=st)
app._refresh_main_buttons_state()
t('botão principal mostra a contagem', '(8)' in app.pendentes_button.cget('text'))

gravacoes = {'pend': 0, 'desc': 0}
_save, _sd = pq.save, pq._salvar_descartados
pq.save = lambda: (gravacoes.__setitem__('pend', gravacoes['pend'] + 1), _save())[1]
pq._salvar_descartados = lambda: (gravacoes.__setitem__('desc', gravacoes['desc'] + 1), _sd())[1]

app.open_pending_queue_manually(); esperar(root, 0.8)
J = app._janela_pendentes
J.win.geometry('940x600+10+10'); esperar(root, 0.5)
tv = J.tree
foto(root, J.win, '10_pendentes')
t('abre em tabela com 8 linhas', len(tv.get_children()) == 8)
t('colunas: título, motivo, confiança, data, ▶ YouTube',
  [tv.heading(c)['text'] for c in tv['columns']] == ['Título', 'Motivo', 'Confiança', 'Data', '▶ YouTube'])
v = tv.item(tv.get_children()[1], 'values')
t(f'linha com motivo, confiança e data ({v})', v[1] == 'Confiança baixa' and v[2] == '62%' and '/' in v[3] and 'abrir' in v[4])
t('seleção múltipla (Ctrl/Shift) ligada', str(tv.cget('selectmode')) == 'extended')
t('abrir de novo não cria outra janela', app._show_pending_queue() is J)

# ---- clique na coluna YouTube: abre sem mexer na seleção
abertos = []
JP.webbrowser.open = lambda u: abertos.append(u)
ids = tv.get_children()
tv.selection_set((ids[0], ids[2])); esperar(root)
bbox = tv.bbox(ids[4], '#5')
tv.event_generate('<Button-1>', x=bbox[0] + 5, y=bbox[1] + 5); tv.event_generate('<ButtonRelease-1>', x=bbox[0] + 5, y=bbox[1] + 5)
esperar(root)
t(f'clicar em "▶ abrir" abre o vídeo daquela linha ({abertos})', abertos == ['https://youtu.be/p4'])
t('...sem mexer na seleção', set(tv.selection()) == {ids[0], ids[2]})
bb = tv.bbox(ids[6], '#1')
class _Ev: pass
e = _Ev(); e.x, e.y = bb[0] + 20, bb[1] + 5
t('duplo clique está ligado na tabela', bool(tv.bind('<Double-1>')))
J._duplo_clique(e); esperar(root)
t('duplo clique na linha também abre', abertos[-1] == 'https://youtu.be/p6')

# ---- clique / ctrl / shift de verdade
def clicar(iid, mod=''):
    b = tv.bbox(iid, '#1')
    ev = '<%sButton-1>' % (mod + '-' if mod else '')
    tv.event_generate(ev, x=b[0] + 30, y=b[1] + 5)
    tv.event_generate('<ButtonRelease-1>', x=b[0] + 30, y=b[1] + 5)
    esperar(root, 0.15)
clicar(ids[1]); clicar(ids[3], 'Control');
t('clique + Ctrl+clique: 2 selecionados', set(tv.selection()) == {ids[1], ids[3]})
clicar(ids[5], 'Shift')
t(f'Shift+clique: faixa contínua ({len(tv.selection())})', set(tv.selection()) >= {ids[3], ids[4], ids[5]})
t('botões mostram quantos agem', '(' in J.b_enfileirar.cget('text') and str(len(tv.selection())) in J.b_remover.cget('text'))

# ---- selecionar tudo / mesmo motivo
J.selecionar_tudo(); esperar(root)
t('Selecionar tudo', len(tv.selection()) == 8)
tv.selection_set(ids[0]); J.selecionar_mesmo_motivo(); esperar(root)
t('Todos com este motivo (3 "não achado")', len(tv.selection()) == 3 and
  all(J._por_id[i]['kind'] == 'nao_encontrado' for i in tv.selection()))
t('Buscar outra versão só com 1 selecionado', str(J.b_buscar.cget('state')) == 'disabled')
tv.selection_set(ids[1]); esperar(root)
buscas = []
app._show_playlist_search = lambda artista_inicial=None, album_inicial=None: buscas.append((artista_inicial, album_inicial))
app._dados_para_busca = lambda it: ('Simone', 'Pedaço de Mim')
J.b_buscar.invoke(); esperar(root)
t(f'Buscar outra versão abre a busca preenchida ({buscas})', buscas == [('Simone', 'Pedaço de Mim')])

# ---- filtro e busca
op = [o for o in J.combo['values'] if o.startswith('Corte não bateu')]
J.filtro.set(op[0]); J.recarregar(); esperar(root)
t(f'filtro por motivo ({op[0]}): 2 linhas', len(tv.get_children()) == 2 and op[0] == 'Corte não bateu (2)')
J.filtro.set(JP.TODOS); J.busca.set('gloria'); esperar(root, 0.4)
t('busca por texto: 1 linha', [J._por_id[i]['video_title'] for i in tv.get_children()] == ['Gloria Lynne - Gloria, Marty & Strings'])
J.busca.set('não encontrado'); esperar(root, 0.4)
t('busca também no motivo: 3 linhas', len(tv.get_children()) == 3)
J.busca.set(''); esperar(root, 0.4)
t('limpar a busca volta tudo', len(tv.get_children()) == 8)

# ---- enfileirar 3: uma gravação da fila, só as linhas afetadas mudam
fila = app._garantir_fila()
grav_fila = {'n': 0}
_fs = fila.salvar
def _conta():
    if not fila._adiando:
        grav_fila['n'] += 1
    _fs()
fila.salvar = _conta
app._iniciar_trabalhador = lambda: None
recargas = {'n': 0}
_rec = J.recarregar
J.recarregar = lambda: (recargas.__setitem__('n', recargas['n'] + 1), _rec())[1]
tv.selection_set((ids[0], ids[3], ids[6])); esperar(root)
antes_p = gravacoes['pend']
J.b_enfileirar.invoke(); esperar(root)
na_fila = [i for i in fila.items if i['tipo'] == 'pendencia']
t(f'Enfileirar 3: 3 pendências na fila de processamento ({len(na_fila)})', len(na_fila) == 3)
t(f'fila gravada uma vez só ({grav_fila["n"]})', grav_fila['n'] == 1)
t('lista de pendências não regravada à toa', gravacoes['pend'] == antes_p)
t('as 3 linhas ganham ⏳, as outras não mudam', all(tv.item(i, 'values')[0].startswith('⏳') for i in (ids[0], ids[3], ids[6]))
  and not tv.item(ids[1], 'values')[0].startswith('⏳'))
t('sem redesenhar a tabela inteira', recargas['n'] == 0)
foto(root, J.win, '11_enfileirados')

# ---- remover 3: uma confirmação, uma gravação, vão pra Descartados
perguntas = []
JP.messagebox.askyesno = lambda *a, **k: (perguntas.append(a[1] if len(a) > 1 else k.get('message')), True)[1]
tv.selection_set((ids[1], ids[2], ids[7])); esperar(root)
antes_p, antes_d = gravacoes['pend'], gravacoes['desc']
J.b_remover.invoke(); esperar(root)
t(f'Remover 3: UMA confirmação ({len(perguntas)})', len(perguntas) == 1 and 'os 3' in perguntas[0])
t(f'uma gravação de cada arquivo ({gravacoes["pend"] - antes_p}, {gravacoes["desc"] - antes_d})',
  gravacoes['pend'] - antes_p == 1 and gravacoes['desc'] - antes_d == 1)
t('as 3 linhas saem, as outras ficam', len(tv.get_children()) == 5 and not any(tv.exists(i) for i in (ids[1], ids[2], ids[7])))
t('sem redesenhar a tabela inteira', recargas['n'] == 0)
t('a seleção passa pra linha seguinte', len(tv.selection()) == 1)
t('título e botão "Descartados (3)"', '5 álbum' in J.titulo.cget('text') and '(3)' in J.btn_descartados.cget('text'))
app._refresh_main_buttons_state()
t('botão principal atualizado (5)', '(5)' in app.pendentes_button.cget('text'))

# ---- descartados: recuperar
J.alternar_descartados(); esperar(root)
foto(root, J.win, '12_descartados')
t('Descartados mostra os 3', len(tv.get_children()) == 3 and J.b_recuperar.winfo_ismapped() and not J.b_remover.winfo_ismapped() and not J.acoes_pend.winfo_ismapped())
tv.selection_set(tv.get_children()[:2]); esperar(root)
J.b_recuperar.invoke(); esperar(root)
t('Recuperar 2: voltam pra lista', len(pq.items) == 7 and len(pq.descartados) == 1 and len(tv.get_children()) == 1)
J.alternar_descartados(); esperar(root)
t('de volta aos pendentes: 7 linhas', len(tv.get_children()) == 7)
pq2 = pending_queue.PendingQueue(janela.SAIDA_MUSICAS)
t('gravado em disco (7 pendentes, 1 descartado)', len(pq2.items) == 7 and len(pq2.descartados) == 1)

# ---- a lista muda por fora (trabalhador): a janela acompanha
pq.add(kind='nao_encontrado', url='https://youtu.be/novo', video_title='Disco novo', reason='x')
esperar(root, 1.8)
t('item novo aparece sozinho', len(tv.get_children()) == 8)
pq.remove(pq.items[0]['id'])
esperar(root, 1.8)
t('item tirado por fora some sozinho', len(tv.get_children()) == 7)

# ---- desempenho: 3000 itens
J.fechar(); esperar(root)
import uuid
pq.items = [{'id': uuid.uuid4().hex[:12], 'kind': 'nao_encontrado', 'url': f'https://youtu.be/x{i}',
             'video_title': f'Álbum {i}', 'confidence_pct': 0, 'reason': 'Álbum não encontrado no Discogs',
             'added_at': '2026-10-01 10:00:00'} for i in range(3000)]
pq.save()
t0 = time.time(); app._show_pending_queue(); esperar(root, 0.1); dt = time.time() - t0
J = app._janela_pendentes
t(f'3000 itens abrem em {dt:.2f}s (< 3s)', dt < 3 and len(J.tree.get_children()) == 3000)
t0 = time.time(); J.selecionar_tudo(); root.update(); dt2 = time.time() - t0
t(f'selecionar tudo com 3000: {dt2:.2f}s', dt2 < 1.5 and len(J.tree.selection()) == 3000)
J.fechar()
root.destroy()
fim()

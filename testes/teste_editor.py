"""
12.17 - Tela "Conferir cortes" (ouvir, ver e marcar os cortes), o áudio
guardado dos pendentes em .audios_pasta_pendencia, os cortes exatos do editor
e a edição de um disco já cortado. Sem som de verdade (tocador falso) e sem rede.
"""
import os, sys, subprocess, time, shutil, glob, types, threading
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1400x1000x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
import numpy as np
from sint import *
from pathlib import Path
import main
import edicao_cortes as EC
from util import PECA_APAGADA
from tocador import Tocador, TocadorFalso
from mutagen.id3 import ID3


def plana(seg):
    x = np.convolve(rng.standard_normal(int(seg * SR)), np.ones(8) / 8, 'same')
    return 0.3 * x / np.std(x)


# Ray Charles "Ingredients" sintético: 10 músicas, 3 trocas sem pausa (depois da 3ª, 4ª e 7ª)
DRAY = [124, 205, 180, 256, 330, 290, 150, 160, 200, 190]
EMEND = (2, 3, 6)
RAY = ['Busted', 'Where Can I Go?', 'Born To Be Blue', 'That Lucky Old Sun', "Ol' Man River", 'In The Evening',
       'A Stranger In Town', "Ol' Man Time", 'Over The Rainbow', "You'll Never Walk Alone"]
partes, inicios = [], []
pos = 0.0
for i, d in enumerate(DRAY):
    inicios.append(pos)
    if i in EMEND or (i - 1) in EMEND:
        partes.append(plana(d) if (i in EMEND or i == len(DRAY) - 1)
                      else np.concatenate([plana(d - 1), fade(musica(1))]))
        pos += d
        if i not in EMEND and i < len(DRAY) - 1:
            partes.append(silencio(2.0)); pos += 2.0
    elif i == len(DRAY) - 1:
        partes.append(musica(d)); pos += d
    else:
        partes += [musica(d - 1), fade(musica(1)), silencio(2.0)]; pos += d + 2.0
disco = salvar(np.concatenate(partes), 'editor_ray.wav')
cad = [d + (2 if i not in EMEND and i < len(DRAY) - 1 else 0) for i, d in enumerate(DRAY)]
OFICIAIS = [{'title': n, 'duration': c} for n, c in zip(RAY, cad)]

# ------------------------------------------------------------------ áudio guardado dos pendentes
base = tmp('editor', 'base', 'x')[:-2]; shutil.rmtree(base, ignore_errors=True); os.makedirs(base)
url = 'https://www.youtube.com/watch?v=NfancbR7EDU'
t('id do vídeo: watch?v=, youtu.be/ e com mais parâmetros',
  EC.id_do_video(url) == 'NfancbR7EDU' and EC.id_do_video('https://youtu.be/NfancbR7EDU?t=3') == 'NfancbR7EDU'
  and EC.id_do_video('https://www.youtube.com/watch?v=NfancbR7EDU&list=X') == 'NfancbR7EDU')
g_ = EC.guardar_audio(base, url, disco)
t('áudio guardado em .audios_pasta_pendencia (na frente na ordem alfabética), com o id do vídeo',
  g_ and g_.parent.name == '.audios_pasta_pendencia' and g_.name == 'NfancbR7EDU.wav'
  and EC.audio_guardado(base, url) == g_)
EC.guardar_audio(base, 'https://youtu.be/AAAAAAAAAAA', disco)
t('limpar: apaga só o de quem saiu da lista', EC.limpar_audios(base, [url]) == 1
  and EC.audio_guardado(base, url) and not EC.audio_guardado(base, 'https://youtu.be/AAAAAAAAAAA'))

# ------------------------------------------------------------------ Edicao: marcas iniciais e estado
ed = EC.Edicao(disco, OFICIAIS, titulo='Ray Charles - Ingredients').carregar()
tipos = [m['tipo'] for m in ed.marcas]
t(f'marcas iniciais: as 9 trocas, as 3 sem pausa como "estimado" ({tipos})',
  len(ed.marcas) == 9 and [i for i, x in enumerate(tipos) if x == 'estimado'] == [2, 3, 6])
reais = inicios[1:]
t(f'...as de silêncio no lugar certo (pior {max(abs(m["pos"] - r) for m, r in zip(ed.marcas, reais) if m["tipo"] == "silencio"):.1f}s)',
  all(abs(m['pos'] - r) <= 3 for m, r in zip(ed.marcas, reais) if m['tipo'] == 'silencio'))
t('nomes do Discogs (mesmo nº de pedaços) e nada faltando', ed.nomes() == RAY and ed.faltam() == 0 and ed.sobram() == 0)
t('volume (envelope) e silêncios medidos pra desenhar', ed.envelope is not None and len(ed.envelope) > 1000
  and len(ed.silencios) >= 5)

# ------------------------------------------------------------------ a tela
import tkinter as tk
from janela_editor import JanelaEditor
root = tk.Tk(); root.withdraw()


def esperar(seg=0.3):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


salvos = []
toc = TocadorFalso()
j = JanelaEditor(root, ed, lambda e: salvos.append(e.texto_tempos()), tocador=toc)
j.win.geometry('1360x760+0+0'); esperar(0.8)
t('abre no primeiro corte a conferir (estimado), selecionado', j.sel == 2 and abs(j.cursor - ed.marcas[2]['pos']) < 0.1)
txt_avisos = ' '.join(w.cget('text') for f in j.avisos.winfo_children() for w in f.winfo_children())
t('aviso: 3 cortes estimados, com as faixas', '3 cortes estimados' in txt_avisos and '3→4' in txt_avisos)
linhas = [j.tabela.item(i)['values'] for i in j.tabela.get_children()]
t('tabela: 10 músicas com nome, início, duração e a do Discogs',
  len(linhas) == 10 and linhas[0][1] == 'Busted' and str(linhas[2][5]) == '⚠')
botoes = {}
def acha(w):
    for f in w.winfo_children():
        if f.winfo_class() == 'Button':
            botoes[f.cget('text')] = f
        acha(f)
acha(j.win)
bm, be, bt_ = botoes.get('✂  Marcar corte'), botoes.get('🎧 Ouvir a emenda (±5s)'), botoes.get('▶  Tocar')
t('"Marcar corte" em destaque e longe do Tocar (no lugar do "Ouvir a emenda")',
  bm is not None and be is not None and bm.cget('bg') != be.cget('bg') and bm.winfo_rootx() < be.winfo_rootx()
  and abs((bm.winfo_rootx() + bm.winfo_width() / 2) - (bt_.winfo_rootx() + bt_.winfo_width() / 2)) > 120)
largura_ok = all(b.winfo_rootx() + b.winfo_width() <= j.c_zoom.winfo_rootx() + j.c_zoom.winfo_width() + 2
                 for b in botoes.values() if b.winfo_ismapped() and b.master.master is j.c_zoom.master)
t('todos os botões cabem na largura', largura_ok)

j.cursor = 100.0
j.tocar_pausar(); esperar(0.3)
t('▶ toca a partir do cursor (o disco inteiro, não só um trecho)', toc.chamadas[-1] == ('tocar', 100.0, None)
  and botoes['⏸  Pausar' if '⏸  Pausar' in botoes else '▶  Tocar'] is not None and j.b_tocar.cget('text').startswith('⏸'))
j.tocar_pausar(); esperar(0.1)
t('...⏸ pausa e o cursor fica onde parou', not toc.tocando and 100.0 <= j.cursor < 102)
j.ir(10.0)
j.ir_marca(1)
t('marca ▶: leva o cursor à próxima marca e seleciona', j.sel == 0 and abs(j.cursor - ed.marcas[0]['pos']) < 0.01)
j.ir_marca(1); j.ir_marca(-1)
t('◀ marca volta', j.sel == 0)
j.sel = 2
j.ouvir_emenda()
p2 = ed.marcas[2]['pos']
t('🎧 ouvir a emenda: 5s antes e depois da marca selecionada',
  toc.chamadas[-1] == ('tocar', round(p2 - 5, 2), round(p2 + 5, 2)))
toc.pausar()
j.cursor = p2 + 3.2
j.marcar()
t('✂ marcar perto (menos de 2s... ou não): marca nova vira "marcado por você"',
  any(m['tipo'] == 'usuario' and abs(m['pos'] - (p2 + 3.2)) < 0.01 for m in ed.marcas))
n_antes = len(ed.marcas)
j.sel = ed.marca_mais_perto(p2 + 3.2)
j.apagar()
t('🗑 apagar a marca selecionada', len(ed.marcas) == n_antes - 1)
j.sel = 2
j.empurrar(0.5)
t('0,5s ⇥ empurra a marca e ela vira "marcado por você"', abs(ed.marcas[2]['pos'] - (p2 + 0.5)) < 0.01
  and ed.marcas[2]['tipo'] == 'usuario')
j.sel = 0
ed.marcas[0]['pos'] += 4.0
j.ao_silencio()
t('🧲 ao silêncio mais perto: a marca volta pro silêncio', abs(ed.marcas[0]['pos'] - reais[0]) <= 2.5
  and ed.marcas[0]['tipo'] == 'silencio')
# apagar uma: falta 1 corte -> aviso vermelho e a faixa longa em vermelho
j.sel = 4
j.apagar(); esperar(0.2)
txt_avisos = ' '.join(w.cget('text') for f in j.avisos.winfo_children() for w in f.winfo_children())
t('faltando 1 corte: aviso vermelho e a faixa longa apontada', 'Falta 1 corte' in txt_avisos
  and 'ouça a faixa 5' in txt_avisos)
t('...e o pedaço longo fica vermelho na tabela', 'longo' in j.tabela.item('4')['tags'])
# teclado: M marca no cursor
j.ir(reais[4] - 0.4)
j.win.focus_force(); esperar(0.2)
j.win.event_generate('<KeyPress-m>'); esperar(0.2)
t('tecla M marca o corte no cursor (e o aviso some)', len(ed.marcas) == 9 and ed.faltam() == 0)
j.win.event_generate('<Control-Right>'); esperar(0.1)
t('Ctrl+→ vai pra próxima marca', abs(j.cursor - ed.marcas[5]['pos']) < 0.01)
# nome editado
ed.renomear(0, 'Busted (Live)')
j.redesenhar()
t('nome editado aparece na tabela', j.tabela.item('0')['values'][1] == 'Busted (Live)')
# clique numa linha da tabela leva o cursor
j.tabela.selection_set('6'); esperar(0.2)
t('clicar numa música leva o cursor ao começo dela', abs(j.cursor - (ed.pecas()[6][0] + 0.5)) < 0.01)
# clique no desenho geral
j._clique_geral(types.SimpleNamespace(x=j.c_geral.winfo_width() // 2, y=10))
t('clique no "disco inteiro" leva o cursor e o trecho ampliado pra lá',
  abs(j.cursor - ed.duracao / 2) < ed.duracao * 0.02 and j.vista[0] <= j.cursor <= j.vista[1])
j.zoom(0.5)
t('zoom +', (j.vista[1] - j.vista[0]) <= 300.1)
j.ver_tudo()
t('disco inteiro no trecho ampliado', j.vista == (0.0, ed.duracao))
j.salvar(); esperar(0.2)
t('salvar: os cortes viram tempos EXATOS (#exato) com os nomes da tabela',
  salvos and salvos[0].startswith('#exato') and 'Busted (Live)' in salvos[0] and len(salvos[0].splitlines()) == 11
  and not j.win.winfo_exists())

# ------------------------------------------------------------------ cortes exatos no processamento
saida = tmp('editor', 'exato', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
g.config = types.SimpleNamespace(get_output_directory=lambda: saida, get=lambda *a, **k: None)
g.metadata_manager = main.MetadataManager(); g.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 60
g.acervo_index = types.SimpleNamespace(add=lambda *a, **k: None, has=lambda *a: False)
g.catalogo = types.SimpleNamespace(musicbrainz=lambda *a, **k: None, musicbrainz_edicoes=lambda *a, **k: [],
                                   ultimo_motivo_mb='x', deezer=lambda *a: None, itunes=lambda *a: None)
baixados = []
g.downloader = types.SimpleNamespace(download_audio=lambda *a, **k: baixados.append(1) or None, last_error='x',
                                     comentarios=lambda *a, **k: [])
g.pre_download = None; g._notas_corte = {}
EC.guardar_audio(saida, url, disco)
dd = {'title': 'Ingredients In A Recipe For Soul', 'artists': ['Ray Charles'], 'year': '1963', 'cover_image': None,
      'tracks': [{'number': i + 1, 'title': n, 'duration': f'{c // 60}:{c % 60:02d}'} for i, (n, c) in
                 enumerate(zip(RAY, cad))], 'discogs_master_id': None, 'discogs_release_id': 963549}
ok = g._download_and_process(url, {'duration': ed.duracao}, 'Ray Charles', 'Ingredients In A Recipe For Soul',
                             '1963', 'discogs', dd['tracks'], True, dd, from_pending=True, tempos_usuario=salvos[0])
arqs = sorted(glob.glob(os.path.join(saida, 'Ray*', '*.mp3')))
durs = [main.duracao_do_arquivo(p) for p in arqs]
esperado = [b - a for a, b in ed.pecas()]
t(f'processar com os cortes do editor: {len(arqs)} faixas, cortadas EXATAMENTE nos pontos marcados '
  f'(pior {max(abs(a - b) for a, b in zip(durs, esperado)) if len(durs) == 10 else 99:.2f}s)',
  ok and len(durs) == 10 and max(abs(a - b) for a, b in zip(durs, esperado)) <= 0.15)
t('...sem baixar de novo (usou o áudio guardado) e o guardado é apagado ao terminar',
  not baixados and any('Áudio guardado da pendência' in l for l in logs) and EC.audio_guardado(saida, url) is None)
t('...e o arquivo da rodada diz que vieram do editor', any(l.startswith('REG FONTE') and 'cortes do editor' in l
                                                           for l in logs))

# o editor é a última palavra: 8 pedaços num disco que o Discogs diz ter 10 -> sai com 8, com os nomes da tabela
saida2 = tmp('editor', 'exato8', 'x')[:-2]; shutil.rmtree(saida2, ignore_errors=True); os.makedirs(saida2)
g.config = types.SimpleNamespace(get_output_directory=lambda: saida2, get=lambda *a, **k: None)
ed8 = EC.Edicao(disco, OFICIAIS, titulo='x')
ed8.duracao, ed8.marcas = ed.duracao, [{'pos': m['pos'], 'tipo': m['tipo']} for m in ed.marcas]
ed8.rotular()
ed8.apagar(8); ed8.apagar(2)                     # junta 3+4 e 9+10
t(f'apagar um corte junta os nomes ("A / B") e os outros ficam na música certa ({ed8.nomes()[2:4]})',
  ed8.nomes()[2] == 'Born To Be Blue / That Lucky Old Sun' and ed8.nomes()[3] == "Ol' Man River"
  and ed8.nomes()[7] == "Over The Rainbow / You'll Never Walk Alone"
  and ed8.duracoes_oficiais()[2] == OFICIAIS[2]['duration'] + OFICIAIS[3]['duration'])
ed8.renomear(7, 'Medley Final')
EC.guardar_audio(saida2, url, disco)
logs.clear()
ok8 = g._download_and_process(url, {'duration': ed.duracao}, 'Ray Charles', 'Ingredients In A Recipe For Soul',
                              '1963', 'discogs', dd['tracks'], True, dd, from_pending=True,
                              tempos_usuario=ed8.texto_tempos())
arqs8 = sorted(glob.glob(os.path.join(saida2, 'Ray*', '*.mp3')))
nomes8 = [str(ID3(p).get('TIT2')) for p in arqs8]
t(f'editor é a última palavra: 8 faixas (o Discogs tem 10), com os nomes da tabela ({len(arqs8)}: {nomes8[2:3]}...)',
  ok8 and len(arqs8) == 8 and nomes8[2] == 'Born To Be Blue / That Lucky Old Sun' and nomes8[7] == 'Medley Final'
  and nomes8[6] == "Ol' Man Time"
  and nomes8[0] == RAY[0] and str(ID3(arqs8[-1]).get('TRCK')) in ('8/8', '8'))

# 12.21: 🗑 Apagar pedaço - o pedaço não é gravado e os de depois andam uma casa
eda = EC.Edicao(disco, OFICIAIS, titulo='x')
eda.duracao, eda.marcas = ed.duracao, [{'pos': m['pos'], 'tipo': m['tipo']} for m in ed.marcas]
eda.silencios = ed.silencios
eda.rotular()
eda.marcar(inicios[5] - 20.0)                    # um defeito no fim da faixa 5: corte novo, pedaço "Ol' Man River (2)"
t(f'apagar pedaço: corte novo no fim de uma faixa dá um pedaço a mais ({eda.nomes()[4:6]})',
  len(eda.pecas()) == 11 and eda.nomes()[5] == "Ol' Man River (2)" and eda.sobram() == 1)
eda.alternar_apagado(5)
t(f'...apagado: não conta (bate com o Discogs de novo), as faixas de depois andam uma casa '
  f'({[eda.numero_da_faixa(i) for i in (4, 5, 6)]})',
  eda.apagados == {5} and eda.sobram() == 0 and eda.faltam() == 0 and eda.numero_da_faixa(6) == 6
  and eda.numero_da_faixa(5) is None and eda.nomes()[6] == 'In The Evening' and eda.situacao_pecas()[5] == 'apagado')
tx_a = eda.texto_tempos()
lidos_a = EC.ler_tempos_exatos(tx_a)
t('...nos cortes salvos (#exato) o pedaço vai marcado como apagado',
  lidos_a and len(lidos_a) == 11 and lidos_a[5]['title'] == PECA_APAGADA and lidos_a[6]['title'] == 'In The Evening')
eda.alternar_apagado(5)
t('...apagar de novo traz o pedaço de volta', not eda.apagados and eda.sobram() == 1)
eda.alternar_apagado(5)
eda.marcar(inicios[7] + 30.0)                    # corte novo depois do apagado: o apagado continua o mesmo pedaço
t('...cortar depois do apagado não muda qual pedaço está apagado', eda.apagados == {5}
  and eda.nomes()[6] == 'In The Evening')
eda.apagar(eda.marca_mais_perto(inicios[7] + 30.0))
eda.apagar(4)                                    # junta o apagado com o pedaço de antes: volta a ficar (não perde música)
t('...juntar um apagado com um pedaço que fica: fica tudo (apagar música por engano é pior)',
  not eda.apagados and len(eda.pecas()) == 10 and eda.nomes()[4] == "Ol' Man River")
edu = EC.Edicao(disco, [], titulo='x'); edu.duracao = 100.0
edu.marcas = [{'pos': 30.0, 'tipo': 'silencio'}, {'pos': 60.0, 'tipo': 'silencio'}]; edu.rotular()
edu.alternar_apagado(0)
t(f'...sem nomes: "Track N" conta só os que ficam ({edu.nomes()})', edu.nomes()[1:] == ['Track 1', 'Track 2'])
edu.alternar_apagado(1)
t('...e não deixa apagar todos', edu.alternar_apagado(2) is False and edu.pecas_que_ficam() == [2])
edd = EC.Edicao(disco, OFICIAIS[:3], titulo='x'); edd.duracao = 400.0
edd.marcas = [{'pos': p_, 'tipo': 'silencio'} for p_ in (100.0, 110.0, 250.0)]; edd.rotular()
edd.alternar_apagado(1)                          # 4 pedaços, 1 é silêncio: os 3 que ficam pegam os nomes do Discogs
t(f'...4 pedaços com um silêncio apagado e 3 músicas no Discogs: os nomes vão nos que ficam ({edd.nomes()})',
  [edd.nomes()[i] for i in (0, 2, 3)] == RAY[:3] and edd.faltam() == 0 and edd.sobram() == 0
  and [edd.duracoes_oficiais()[i] for i in (0, 2, 3)] == [OFICIAIS[k]['duration'] for k in range(3)])
# a faixa 3 inteira apagada (uma música que você não quer): sai com 9 faixas, numeradas sem buraco
saida_a = tmp('editor', 'apagado', 'x')[:-2]; shutil.rmtree(saida_a, ignore_errors=True); os.makedirs(saida_a)
g.config = types.SimpleNamespace(get_output_directory=lambda: saida_a, get=lambda *a, **k: None)
eda2 = EC.Edicao(disco, OFICIAIS, titulo='x')
eda2.duracao, eda2.marcas = ed.duracao, [{'pos': m['pos'], 'tipo': m['tipo']} for m in ed.marcas]
eda2.rotular(); eda2.alternar_apagado(2)
EC.guardar_audio(saida_a, url, disco); logs.clear()
oka = g._download_and_process(url, {'duration': ed.duracao}, 'Ray Charles', 'Ingredients In A Recipe For Soul',
                              '1963', 'discogs', dd['tracks'], True, dd, from_pending=True,
                              tempos_usuario=eda2.texto_tempos())
arqsa = sorted(glob.glob(os.path.join(saida_a, 'Ray*', '*.mp3')))
nomesa = [str(ID3(p).get('TIT2')) for p in arqsa]
pecas_a = eda2.pecas()
t(f'processar com um pedaço apagado: {len(arqsa)} faixas, sem a apagada, numeradas 1 a 9 ({os.path.basename(arqsa[2]) if len(arqsa) > 2 else ""})',
  oka and len(arqsa) == 9 and 'Born To Be Blue' not in nomesa and nomesa[2] == 'That Lucky Old Sun'
  and os.path.basename(arqsa[2]).startswith('03 - That Lucky Old Sun') and str(ID3(arqsa[2]).get('TRCK')) in ('3/9',)
  and abs(main.duracao_do_arquivo(arqsa[2]) - (pecas_a[3][1] - pecas_a[3][0])) <= 0.15
  and any('pedaço(s) apagado(s)' in l for l in logs))
g.config = types.SimpleNamespace(get_output_directory=lambda: saida, get=lambda *a, **k: None)
# #exato que não dá pra ler: o disco não é cortado por conta própria
saida3 = tmp('editor', 'exato_ruim', 'x')[:-2]; shutil.rmtree(saida3, ignore_errors=True); os.makedirs(saida3)
g.config = types.SimpleNamespace(get_output_directory=lambda: saida3, get=lambda *a, **k: None)
EC.guardar_audio(saida3, url, disco); logs.clear()
ok9 = g._download_and_process(url, {'duration': ed.duracao}, 'Ray Charles', 'Ingredients In A Recipe For Soul',
                              '1963', 'discogs', dd['tracks'], True, dd, from_pending=True,
                              tempos_usuario='#exato\n0:00:00.000 Busted\nisto não é um tempo')
t('cortes do editor ilegíveis: nada de corte automático por conta própria (o disco continua esperando)',
  not ok9 and not glob.glob(os.path.join(saida3, 'Ray*', '*.mp3'))
  and any('Não consegui ler os cortes salvos' in l for l in logs))
g.config = types.SimpleNamespace(get_output_directory=lambda: saida, get=lambda *a, **k: None)

# ------------------------------------------------------------------ disco já cortado: editar a pasta
pasta = Path(arqs[0]).parent
from PIL import Image as _Im
_Im.new('RGB', (60, 60), 'red').save(pasta / 'cover.jpg')
import saida as SAIDA
SAIDA.embutir_capa(pasta, pasta / 'cover.jpg')
for p in arqs:
    main.MetadataManager().add_discogs_ids(p, master_id=75497, release_id=963549)
info = EC.ler_pasta(pasta)
t('ler a pasta: 10 faixas, nomes das tags, tags do álbum e a capa',
  len(info['arquivos']) == 10 and info['nomes'][1] == 'Where Can I Go?' and info['album'].get('TALB')
  and info['album'].get('capa') and info['album'].get('DISCOGS_RELEASE_ID') == '963549')
juntado = EC.pasta_audios(saida) / '_editando_teste.mp3'
EC.juntar_pasta(pasta, juntado)
t('os 10 MP3 juntados num arquivo só, com a duração do disco',
  abs(main.duracao_do_arquivo(str(juntado)) - sum(info['duracoes'])) < 2)
marcas, acc = [], 0.0
for d in info['duracoes'][:-1]:
    acc += d
    marcas.append({'pos': acc, 'tipo': 'usuario'})
ed2 = EC.Edicao(juntado, [], titulo=pasta.name, nomes_fixos=info['nomes'], origem='pasta').carregar(marcas=marcas)
t('a edição abre com os cortes e os nomes de antes', len(ed2.marcas) == 9 and ed2.nomes()[0] == info['nomes'][0])
ed2.apagar(8)                                   # junta as duas últimas
ed2.renomear(8, 'Over The Rainbow / You\'ll Never Walk Alone')
r = EC.regravar_pasta(pasta, saida, ed2, info, log=lambda *a: None)
novos = sorted(pasta.glob('*.mp3'))
tags = ID3(str(novos[-1]))
t(f'regravar: 9 faixas na pasta, a última com o nome novo ({novos[-1].name})',
  r['faixas'] == 9 and len(novos) == 9 and novos[-1].name.startswith('09 - Over The Rainbow'))
t('...com as tags do álbum, nº/total, capa e os IDs do Discogs',
  str(tags.get('TALB')) == info['album']['TALB'] and str(tags.get('TRCK')) == '9/9' and tags.getall('APIC')
  and any(f.desc == 'DISCOGS_RELEASE_ID' and f.text[0] == '963549' for f in tags.getall('TXXX')))
t('...e os 10 arquivos de antes guardados em .audios_pasta_pendencia/antes_da_edicao',
  r['antes'].parent.name == 'antes_da_edicao' and len(list(Path(r['antes']).glob('*.mp3'))) == 10)
from acervo_index import AcervoIndex
idx = AcervoIndex(saida, metadata_manager=main.MetadataManager())
idx.load_or_rebuild(log_func=lambda *a: None, force_rebuild=True)
t(f'o acervo acha o disco na pasta dele, não na cópia de antes ({(idx.get(75497) or {}).get("folder")})',
  (idx.get(75497) or {}).get('folder') == pasta.name and len(idx.data) == 1)

# ------------------------------------------------------------------ tocador de verdade (sem placa de som)
toc_real = Tocador()
t('sem sounddevice/PortAudio: o tocador diz que não há som (e a tela continua funcionando)',
  toc_real.disponivel is False and toc_real.motivo)


class StreamFalso:
    """Imita o RawOutputStream: chama o callback numa thread até CallbackStop."""
    def __init__(self, samplerate, channels, dtype, callback, finished_callback):
        self.cb, self.fim, self.parar = callback, finished_callback, False

    def start(self):
        def rodar():
            buf = bytearray(1024 * 4)
            while not self.parar:
                try:
                    self.cb(memoryview(buf), 1024, None, None)
                except SDFalso.CallbackStop:
                    break
                time.sleep(0.001)
            self.fim()
        threading.Thread(target=rodar, daemon=True).start()

    def abort(self):
        self.parar = True

    def close(self):
        pass


class SDFalso:
    class CallbackStop(Exception):
        pass
    RawOutputStream = StreamFalso


toc2 = Tocador(sd=SDFalso)
acabou = []
toc2.ao_terminar = lambda: acabou.append(1)
toc2.tocar(disco, 120.0, 122.0)
for _ in range(1600):
    if acabou:
        break
    time.sleep(0.02)
t(f'tocador: toca o trecho pedido (ffmpeg → som) e avisa quando acaba ({toc2.posicao():.2f}s)',
  acabou and abs(toc2.posicao() - 122.0) < 0.1 and not toc2.tocando)
toc2.tocar(disco, 300.0)
time.sleep(0.3)
toc2.pausar()
t('...pausar guarda a posição', 300.0 < toc2.posicao() < 400.0 and not toc2.tocando)

# ------------------------------------------------------------------ achados da revisão independente
# tocar de novo logo em seguida (← → seguidos, cliques rápidos): o ffmpeg velho não para o novo
parou_sozinho = 0
toc3 = Tocador(sd=SDFalso)
for k in range(25):
    toc3.tocar(disco, 100.0 + k)
    time.sleep(0.01 * (k % 4))
    toc3.tocar(disco, 200.0 + k)
    time.sleep(0.15)
    if not toc3.tocando:
        parou_sozinho += 1
    toc3.pausar()
t(f'tocar de novo logo depois de outro tocar: nunca para sozinho ({parou_sozinho} de 25)', parou_sozinho == 0)


class SDSemSaida(SDFalso):
    class RawOutputStream:
        def __init__(self, *a, **k):
            raise OSError('Error opening RawOutputStream: Invalid device')


toc4 = Tocador(sd=SDSemSaida)
t('sem saída de som (fone tirado): tocar diz que não deu e a tela mostra o motivo',
  toc4.tocar(disco, 10.0) is False and not toc4.disponivel and 'saída de som' in (toc4.motivo or ''))

# tempos exatos: nomes que a lista colada pularia, arredondamento e marcas a 1 s
ed3 = EC.Edicao(disco, OFICIAIS[:5], titulo='x')
ed3.duracao = 1000.0
ed3.marcas = [{'pos': 59.9996, 'tipo': 'usuario'}, {'pos': 60.9996, 'tipo': 'usuario'},
              {'pos': 315.0, 'tipo': 'usuario'}, {'pos': 3725.5, 'tipo': 'usuario'}][:3] + [{'pos': 500.25, 'tipo': 'usuario'}]
for i, n in enumerate(['Side by Side', 'Lado a Lado', '5:15', '1. Allegro', 'Total Eclipse']):
    ed3.renomear(i, n)
txt = ed3.texto_tempos()
volta = EC.ler_tempos_exatos(txt)
t(f'#exato: "0:01:00.000" (nunca "0:00:60.000") e os nomes voltam como foram escritos',
  '0:01:00.000 Lado a Lado' in txt and volta is not None and len(volta) == 5
  and [x['title'] for x in volta] == ['Side by Side', 'Lado a Lado', '5:15', '1. Allegro', 'Total Eclipse']
  and abs(volta[1]['start_time'] - 60.0) < 0.001 and abs(volta[2]['start_time'] - 61.0) < 0.001)
gx = main.FullTracksDownloaderGUI.__new__(main.FullTracksDownloaderGUI)
gx.log = lambda *a: None
fx = gx._faixas_dos_tempos(txt, {'tracks': OFICIAIS[:5]}, 1000.0)
t('...e o processamento usa esses nomes (sem trocar pelo Discogs) e todos os 5 cortes',
  fx and [f['title'] for f in fx] == ['Side by Side', 'Lado a Lado', '5:15', '1. Allegro', 'Total Eclipse'])
from corte_estrategias import SmartCutter
sc_ = SmartCutter({'tracks': []}, {}, disco, log_func=lambda *a: None)
t('marcas a exatamente 1 s uma da outra passam no corte exato (antes a lista inteira era recusada)',
  sc_.cut_at_positions([0.0, 59.9996, 60.9996, 315.0, 500.25], ['a', 'b', 'c', 'd', 'e'],
                       marcar_sem_silencio=False, exato=True) is not None)

# nomes acompanham os pedaços (disco já cortado) e os editados andam junto
ed4 = EC.Edicao(disco, [], nomes_fixos=['A', 'B', 'C'], origem='pasta', duracoes_fixas=[100, 100, 100])
ed4.duracao = 300.0
ed4.marcas = [{'pos': 100.0, 'tipo': 'usuario'}, {'pos': 200.0, 'tipo': 'usuario'}]
ed4.rotular()
ed4.marcar(150.0)
t(f'separar a faixa B: "B" e "B (2)" ({ed4.nomes()})', ed4.nomes() == ['A', 'B', 'B (2)', 'C'])
ed4.apagar(0)
t(f'juntar A com B: "A / B" ({ed4.nomes()})', ed4.nomes() == ['A / B', 'B (2)', 'C'])
ed4.mover(1, 160.0)
t(f'mover um corte não troca os nomes ({ed4.nomes()})', ed4.nomes() == ['A / B', 'B (2)', 'C'])
ed4.renomear(2, 'Cê')
ed4.marcar(50.0)
t(f'nome editado continua na mesma música depois de um corte novo antes dela ({ed4.nomes()})',
  ed4.nomes()[3] == 'Cê')
ed4.apagar(0)
t(f'...e depois de apagar um corte antes dela ({ed4.nomes()})', ed4.nomes()[2] == 'Cê')

# Esc na caixa do nome só cancela (não fecha a tela)
j5 = JanelaEditor(root, EC.Edicao(disco, OFICIAIS, titulo='x').carregar(), lambda e: None, tocador=TocadorFalso())
esperar(0.5)
bb = j5.tabela.bbox('1', '#2')
j5._editar_nome(types.SimpleNamespace(x=bb[0] + 5, y=bb[1] + 3)); esperar(0.2)
j5._caixa_nome.focus_force(); esperar(0.1)
j5._caixa_nome.event_generate('<Escape>'); esperar(0.3)
t('Esc na caixa do nome: cancela o nome e a tela continua aberta', j5.win.winfo_exists()
  and j5.ed.nomes()[1] == RAY[1])

# ------------------------------------------------------------------ 12.18: guias, nomes (a roxa saiu na 12.21)
from janela_editor import GUIA
ed5x = j5.ed
guias = ed5x.guias_discogs()
t(f'guias do Discogs: {len(guias)} pontos onde as durações põem cada troca '
  f'(pior {max(abs(g_ - r_) for g_, r_ in zip(guias, inicios[1:])):.1f}s)',
  len(guias) == 9 and max(abs(g_ - r_) for g_, r_ in zip(guias, inicios[1:])) <= 3)
j5.vista = (0.0, 600.0); j5.redesenhar(); esperar(0.2)
cz = j5.c_zoom
amarelos = [i for i in cz.find_all() if cz.type(i) in ('line', 'polygon') and cz.itemcget(i, 'fill') == GUIA]
textos = [cz.itemcget(i, 'text') for i in cz.find_all() if cz.type(i) == 'text']
t(f'...em amarelo na onda, com a duração de cada música do Discogs ({[x for x in textos if x.startswith("Discogs")][:2]})',
  len(amarelos) >= 4 and 'Discogs 1: 2:06' in textos and 'Discogs 2: 3:27' in textos)

def _textos_da_tela(w):
    saida = []
    for f in w.winfo_children():
        try:
            saida.append(str(f.cget('text')))
        except tk.TclError:
            pass
        saida += _textos_da_tela(f)
    return saida


ROXO = '#7C3AED'
roxos = [i for c_ in (cz, j5.c_geral) for i in c_.find_all() if c_.type(i) in ('line', 'polygon', 'rectangle')
         and c_.itemcget(i, 'fill').upper() == ROXO]
t('12.21: a guia roxa ("o som muda de repente") saiu da onda, do disco inteiro e da legenda',
  not roxos and not any('som muda' in x for x in _textos_da_tela(j5.win)))
g_am = max(guias, key=lambda g_: min(abs(g_ - m_['pos']) for m_ in ed5x.marcas))
j5.vista = (g_am - 15.0, g_am + 15.0); j5.redesenhar(); esperar(0.1)     # de perto: a guia longe da marca
x_am = j5._x(g_am, cz.winfo_width(), *j5.vista)
j5._clique_zoom(types.SimpleNamespace(x=x_am + 3, y=200))
t('clicar perto da guia amarela leva o cursor exatamente pra ela', abs(j5.cursor - g_am) < 0.01)
j5.vista = (0.0, 600.0)
# 12.21: 🗑 Apagar pedaço no ✂ Editar da pendência: o do cursor; o desenho fica cinza e riscado
j5.vista = (inicios[4] - 60.0, inicios[5] + 240.0)
j5.ir(inicios[4] + 5.0); esperar(0.1)
j5.apagar_peca(); esperar(0.1)
cinzas = [i for i in cz.find_all() if cz.type(i) == 'rectangle' and cz.itemcget(i, 'fill') == '#9CA3AF']
textos_z = [cz.itemcget(i, 'text') for i in cz.find_all() if cz.type(i) == 'text']
t(f'✂ Editar: "🗑 Apagar pedaço" apaga o pedaço do cursor (faixa 5), cinza na onda e "— apagado —" '
  f'({j5.tabela.item("4", "values")[:2]})', ed5x.apagados == {4} and cinzas and '— apagado —' in textos_z
  and j5.tabela.item('4', 'values')[1] == '— apagado —' and str(j5.tabela.item('5', 'values')[0]) == '5'
  and '5. In The Evening' in textos_z)
j5.apagar_peca(); esperar(0.1)
t('...e "↩ Desfazer apagar" traz de volta', not ed5x.apagados and 'Apagar pedaço' in j5.b_apagar_peca.cget('text'))
ed5x.mudou = False
j5.vista = (0.0, 600.0)
ed5x.apagar(0); j5.redesenhar(); esperar(0.1)
avisos_txt = ' '.join(w.cget('text') for f in j5.avisos.winfo_children() for w in f.winfo_children())
t('faltando um corte: o aviso não fala mais de marca roxa', 'Falta 1 corte' in avisos_txt
  and 'roxa' not in avisos_txt)
ed5x.marcar(inicios[1])
t(f'apagar e marcar de novo o mesmo corte devolve os nomes ({ed5x.nomes()[:2]})', ed5x.nomes()[:2] == RAY[:2])
# nomes: candidatos de cada fonte no duplo clique
ed5x.adicionar_candidatos('descrição do vídeo', [n + ' (Remaster)' for n in RAY])
cands = ed5x.candidatos_da_faixa(1)
t(f'candidatos da faixa 2: o da mesma posição primeiro ({cands[0]})',
  cands[0] == ('descrição do vídeo', 'Where Can I Go? (Remaster)') and len(cands) == 10)
j5.vista = (0.0, ed5x.duracao); j5.redesenhar(); esperar(0.2)
bb = j5.tabela.bbox('1', '#2')
j5._editar_nome(types.SimpleNamespace(x=bb[0] + 5, y=bb[1] + 3)); esperar(0.2)
cx = j5._caixa_nome
t('duplo clique no nome: caixa com a lista dos nomes achados', 'Where Can I Go? (Remaster)' in cx.cget('values'))
cx.set('Where Can I Go? (Remaster)'); cx.event_generate('<<ComboboxSelected>>'); esperar(0.2)
t('escolher um nome da lista troca o nome da música', j5.ed.nomes()[1] == 'Where Can I Go? (Remaster)')
jc = j5.colar_nomes(); esperar(0.2)
_, caixa_txt, usar = j5._janela_colar
caixa_txt.insert('1.0', '01 - Um\n2. Dois (3:12)\nA3 Três\n4:05 Quatro\n\nTotal 40:00\n')
usar(); esperar(0.2)
t(f'📋 Colar nomes: número, lado e tempo saem; linhas vazias e "Total" não contam ({j5.ed.nomes()[:5]})',
  j5.ed.nomes()[:5] == ['Um', 'Dois', 'Três', 'Quatro', RAY[4]] and not jc.winfo_exists())
bb = j5.tabela.bbox('6', '#2')
j5._editar_nome(types.SimpleNamespace(x=bb[0] + 5, y=bb[1] + 3)); esperar(0.2)
j5._caixa_nome.delete(0, 'end'); j5._caixa_nome.insert(0, 'Nome Seis')
j5.cursor = inicios[2] + 30; j5.sel = None; j5.marcar(); esperar(0.2)
t(f'marcar um corte com a caixa do nome aberta: o nome vale pra música em que foi escrito ({j5.ed.nomes()[7]})',
  j5.ed.nomes()[7] == 'Nome Seis' and getattr(j5, '_caixa_nome', None) is None)
j5.fechar(perguntar=False)

# nomes acompanham os cortes também quando o disco abre com corte faltando
LETRAS = [{'title': c, 'duration': 0} for c in 'ABCDE']
ed6 = EC.Edicao(disco, LETRAS); ed6.duracao = 500.0
ed6.marcas = [{'pos': p_, 'tipo': 'silencio'} for p_ in (100.0, 200.0, 300.0)]; ed6.rotular()
ed6.marcar(400.0)
t(f'abriu faltando um corte: marcar o que faltava dá os nomes do Discogs ({ed6.nomes()})', ed6.nomes() == list('ABCDE'))
ed6.marcar(450.0)
t(f'...e daí em diante os nomes acompanham os cortes ({ed6.nomes()})', ed6.nomes() == list('ABCDE') + ['E (2)'])
ed6.apagar(0)
t(f'...juntar continua dando "A / B" ({ed6.nomes()[:2]})', ed6.nomes()[0] == 'A / B')
ed7 = EC.Edicao(disco, LETRAS[:3]); ed7.duracao = 300.0
ed7.marcas = [{'pos': 100.0, 'tipo': 'silencio'}, {'pos': 200.0, 'tipo': 'silencio'}]; ed7.rotular()
ed7.colar_nomes('P1\nP2\nP3')
ed7.apagar(1); ed7.marcar(200.0)
t(f'nome que você deu volta quando o corte apagado é marcado de novo ({ed7.nomes()})', ed7.nomes() == ['P1', 'P2', 'P3'])
ed7b = EC.Edicao(disco, LETRAS[:3]); ed7b.duracao = 300.0
ed7b.marcas = [{'pos': 100.0, 'tipo': 'silencio'}, {'pos': 200.0, 'tipo': 'silencio'}]; ed7b.rotular()
ed7b.marcar(50.0); ed7b.apagar(1)
t(f'apagar o corte depois de um "A (2)": o pedaço junto é "A (2) / B" ({ed7b.nomes()})',
  ed7b.nomes() == ['A', 'A (2) / B', 'C'])
ed7b.marcar(100.0)
t(f'...e marcar de novo volta a "A", "A (2)", "B" ({ed7b.nomes()})', ed7b.nomes() == ['A', 'A (2)', 'B', 'C'])
ed8b = EC.Edicao(disco, []); ed8b.duracao = 500.0; ed8b.silencios = [(118.0, 121.0, 3)]
mt = ed8b.marcas_dos_tempos([117.5, 123.0, 250.0])
t(f'dois tempos na mesma pausa não viram dois cortes no mesmo lugar ({[round(m_["pos"], 1) for m_ in mt]})',
  len(mt) == 3 and all(b_['pos'] - a_['pos'] >= 2 for a_, b_ in zip(mt, mt[1:])))
t('colar nomes sem número na lista: "99 Luftballons" e "(I Can\'t Get No) Satisfaction" ficam inteiros',
  EC.nomes_de_lista("(I Can't Get No) Satisfaction\n99 Luftballons\nYesterday") ==
  ["(I Can't Get No) Satisfaction", '99 Luftballons', 'Yesterday'])

# 12.21: medir o áudio é só o volume (pro desenho): sem as "mudanças no som"
env_s, sug_s = EC.medir_audio(salvar(np.concatenate([musica(150), np.zeros(SR * 3), musica(120)]), 'editor_som.wav'))
k_pausa = int(151.5 / EC.ENVELOPE_PASSO_SEC)
t(f'medir o áudio: o volume a cada {EC.ENVELOPE_PASSO_SEC}s, sem guia roxa ({len(env_s)} pontos)',
  sug_s == [] and abs(len(env_s) - 273 / EC.ENVELOPE_PASSO_SEC) <= 3 and env_s[k_pausa] < 0.05
  and float(np.median(env_s[:k_pausa - 40])) > 0.2)

# arquivo de correções: o que o programa sugeriu × o que você deixou
edc = EC.Edicao(disco, OFICIAIS, titulo='Ray Charles - Ingredients')
edc.duracao, edc.silencios = ed5x.duracao, ed5x.silencios
edc.marcas = [{'pos': r_i, 'tipo': 'silencio' if k not in (2, 3, 6) else 'estimado'} for k, r_i in enumerate(inicios[1:])]
edc.rotular()
edc.mover(2, inicios[3] + 4.0)
edc.apagar(4)
edc.marcar(inicios[8] + 60.0)
edc.renomear(1, 'Nome Novo')
reg = EC.registro_de_correcoes(edc, {'url': url})
import collections as _col
acoes = _col.Counter(c['acao'] for c in reg['cortes'])
movido = next(c for c in reg['cortes'] if c['acao'] == 'movido')
t(f'correções: mantidos, movido (quanto), apagado e novo ({dict(acoes)})',
  acoes == {'mantido': 7, 'movido': 1, 'apagado': 1, 'novo': 1} and abs(movido['diferenca_s'] - 4.0) < 0.01
  and movido['tipo'] == 'estimado' and reg['pecas_finais'] == 10)
t('...com o que havia perto (pausa, guia do Discogs) e os nomes trocados',
  all('pausa_perto_s' in c and 'discogs_perto_s' in c and 'som_perto_s' in c for c in reg['cortes'])
  and any(x_['final'] == 'Nome Novo' for x_ in reg['nomes_trocados']))
base_c = tmp('editor', 'correcoes', 'x')[:-2]; shutil.rmtree(base_c, ignore_errors=True)
EC.gravar_correcao(base_c, reg); EC.gravar_correcao(base_c, reg)
import json as _json
linhas_c = EC.caminho_correcoes(base_c).read_text(encoding='utf-8').splitlines()
res_c = EC.resumo_correcoes(base_c)
t(f'...uma linha por disco em logs/correcoes_do_editor.txt, e o resumo ({res_c})',
  len(linhas_c) == 2 and _json.loads(linhas_c[0])['disco'] == 'Ray Charles - Ingredients'
  and res_c and 'últimas 2 edições' in res_c and '78%' in res_c)

# medidas guardadas: abrir de novo não mede de novo
copia = Path(tmp('editor', 'medidas', 'disco.wav')); shutil.rmtree(copia.parent, ignore_errors=True)
copia.parent.mkdir(parents=True); shutil.copy2(disco, copia)
med = copia.parent / '_medidas' / 'X.npz'
t0_ = time.time(); ed_m1 = EC.Edicao(copia, OFICIAIS).carregar(medidas=med); t1_ = time.time() - t0_
from corte_album import AlbumCutter as _AC
_orig_med, _orig_det, _orig_ini = EC.medir_audio, _AC.detect_gaps, EC.Edicao._marcas_iniciais
EC.medir_audio = lambda *a: (_ for _ in ()).throw(RuntimeError('mediu de novo'))
_AC.detect_gaps = lambda self: (_ for _ in ()).throw(RuntimeError('mediu de novo'))
EC.Edicao._marcas_iniciais = lambda *a: (_ for _ in ()).throw(RuntimeError('cortou de novo'))
try:
    t0_ = time.time(); ed_m2 = EC.Edicao(copia, OFICIAIS).carregar(medidas=med); t2_ = time.time() - t0_
    erro_m = None
except RuntimeError as e:
    ed_m2, erro_m = None, str(e)
t(f'medidas guardadas: abrir de novo reaproveita volume, silêncios e cortes sugeridos ({t1_:.1f}s → '
  f'{t2_ if ed_m2 else 0:.1f}s)', ed_m2 is not None and len(ed_m2.envelope) == len(ed_m1.envelope)
  and [m['pos'] for m in ed_m2.marcas] == [m['pos'] for m in ed_m1.marcas])
try:
    EC.Edicao(copia, OFICIAIS[:-1]).carregar(medidas=med)
    erro_m2 = None
except RuntimeError as e:
    erro_m2 = str(e)
t('...mas com outra lista de faixas os cortes sugeridos são feitos de novo', erro_m2 == 'cortou de novo')
EC.gravar_medidas(med, copia, fontes=[['capítulos do vídeo', ['A', 'B'], [0.0, 100.0]]])
lido_m = EC.ler_medidas(med, copia)
t('...as listas do vídeo ficam guardadas junto, sem perder o resto',
  lido_m.get('fontes') == [['capítulos do vídeo', ['A', 'B'], [0.0, 100.0]]] and lido_m.get('envelope') is not None
  and len(lido_m.get('marcas') or {}) == 1 and lido_m.get('gaps'))
os.utime(copia, (time.time() + 100, time.time() + 100))
t('...e áudio trocado não usa as medidas velhas', EC.ler_medidas(med, copia) == {})
EC.medir_audio, _AC.detect_gaps, EC.Edicao._marcas_iniciais = _orig_med, _orig_det, _orig_ini

# regravar: arquivo aberto noutro programa -> não mexe em nada; troca que falha no meio -> volta tudo
antes_pasta = sorted(p.name for p in pasta.glob('*.mp3'))
info5 = EC.ler_pasta(pasta)
ed5 = EC.Edicao(juntado, [], nomes_fixos=info5['nomes'], origem='pasta', duracoes_fixas=info5['duracoes'])
ed5.duracao = main.duracao_do_arquivo(str(juntado))
acc5, ed5.marcas = 0.0, []
for d in info5['duracoes'][:-1]:
    acc5 += d
    ed5.marcas.append({'pos': acc5, 'tipo': 'usuario'})
ed5.apagar(0)
_orig_pode = EC._pode_mexer
EC._pode_mexer = lambda p: not p.name.startswith('02')
try:
    EC.regravar_pasta(pasta, saida, ed5, info5, log=lambda *a: None)
    erro5 = None
except RuntimeError as e:
    erro5 = str(e)
EC._pode_mexer = _orig_pode
t(f'arquivo aberto noutro programa: avisa e a pasta fica como estava ({(erro5 or "")[:50]}...)',
  erro5 and 'abertos em outro programa' in erro5 and sorted(p.name for p in pasta.glob('*.mp3')) == antes_pasta
  and not list(EC.pasta_audios(saida).glob('_novos_*')))
_orig_move, chamadas_move = EC.shutil.move, []


def _move_que_falha(a, b):
    chamadas_move.append(a)
    if str(a).endswith('.mp3') and '_novos_' in str(a) and len([c for c in chamadas_move if '_novos_' in str(c)]) == 3:
        raise PermissionError('[WinError 32] O arquivo já está sendo usado por outro processo')
    return _orig_move(a, b)


EC.shutil.move = _move_que_falha
try:
    EC.regravar_pasta(pasta, saida, ed5, info5, log=lambda *a: None)
    erro6 = None
except RuntimeError as e:
    erro6 = str(e)
EC.shutil.move = _orig_move
t(f'troca que falha no meio: volta tudo como estava ({(erro6 or "")[:60]}...)',
  erro6 and 'ficou como estava' in erro6 and sorted(p.name for p in pasta.glob('*.mp3')) == antes_pasta
  and not list(EC.pasta_audios(saida).glob('_novos_*')))

# limpeza: sobras de trabalhos interrompidos vão embora, menos as em uso; _editando_X não é áudio de pendente
for nome_ in ('_editando_X.mp3', '_editando_velho.mp3', '_novos_123'):
    alvo = EC.pasta_audios(saida) / nome_
    alvo.mkdir() if nome_.startswith('_novos_') else alvo.write_bytes(b'x')
EC.limpar_audios(saida, [])
t('limpar áudios de pendentes não apaga arquivo de trabalho ("_editando_X")',
  (EC.pasta_audios(saida) / '_editando_X.mp3').exists())
EC.limpar_sobras(saida, {'_editando_X.mp3'})
t('sobras de trabalho interrompido apagadas ao abrir, menos a que está em uso',
  (EC.pasta_audios(saida) / '_editando_X.mp3').exists() and not (EC.pasta_audios(saida) / '_editando_velho.mp3').exists()
  and not (EC.pasta_audios(saida) / '_novos_123').exists())
(EC.pasta_audios(saida) / '_editando_X.mp3').unlink()
root.destroy()

# ------------------------------------------------------------------ na janela do programa
import janela
root, app, mainj = janela.abrir()
iniciou = []
app._iniciar_trabalhador = lambda: iniciou.append(1)
app._tocador_teste = TocadorFalso()
videos_info = {}                                   # o "YouTube" dos testes (sem rede)
app.downloader.get_video_info = lambda u, *a, **k: videos_info.get(u, {})
app.downloader.comentarios = lambda u, *a, **k: []
t('tela principal: botão "✂ Editar disco"', any(
  w.winfo_class() == 'Button' and 'Editar disco' in w.cget('text')
  for f in app.action_frame.winfo_children() for w in f.winfo_children()))
pq = app.pending_queue
url2 = 'https://www.youtube.com/watch?v=RayCharles01'
pq.add(kind='falha_corte', url=url2, video_title='Ray Charles - Ingredients In A Recipe For Soul -1963 (FULL ALBUM)',
       title_artist='Ray Charles', title_album='Ingredients In A Recipe For Soul', confidence_pct=100,
       reason='Corte não bateu', discogs_data={'title': 'Ingredients In A Recipe For Soul', 'artists': ['Ray Charles'],
                                               'tracks': OFICIAIS})
EC.guardar_audio(app.config.get_output_directory(), url2, disco)


def esperar2(seg=0.4):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


app.open_pending_queue_manually(); esperar2(0.8)
J = app._janela_pendentes
t('Precisam de você: "✂ Editar" desligado sem seleção', str(J.b_editar.cget('state')) == 'disabled')
J.tree.selection_set(pq.items[0]['id']); esperar2()
t('...ligado com 1 selecionado', str(J.b_editar.cget('state')) == 'normal')
J.editar()
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
je = getattr(app, '_janela_editor', None)
t('✂ Editar abre a tela com o áudio guardado (sem baixar)', je is not None and je.win.winfo_exists()
  and len(je.ed.marcas) == 9)
if os.environ.get('DF_FOTOS'):
    janela.foto(root, tmp('editor', 'tela.png'))
je.salvar(); esperar2(0.4)
it = pq.items[0]
fi = app.fila.por_url(url2)
t('...salvar: o item guarda os cortes (#exato) e vai pra fila', it.get('tempos_usuario', '').startswith('#exato')
  and fi and fi['tipo'] == 'pendencia' and iniciou)
pq.descartar([it['id']])
app._limpar_audios_pendentes()
t('descartado: o áudio guardado é apagado', EC.audio_guardado(app.config.get_output_directory(), url2) is None)
base_app = app.config.get_output_directory()
linhas_corr = EC.caminho_correcoes(base_app).read_text(encoding='utf-8').splitlines() \
    if EC.caminho_correcoes(base_app).exists() else []
t('o salvar anotou as correções em logs/correcoes_do_editor.txt',
  linhas_corr and _json.loads(linhas_corr[-1]).get('url') == url2 and _json.loads(linhas_corr[-1]).get('confirmado'))
# 12.19: o "desenho do volume" do disco editado, pra testar ajustes do corte com os discos corrigidos
nome_med = _json.loads(linhas_corr[-1]).get('medidas') if linhas_corr else None
arq_med = EC.caminho_medidas_editor(base_app) / (nome_med or '-')
ok_med = False
if arq_med.exists():
    with np.load(str(arq_med)) as z_:
        ok_med = (len(z_['volume_db']) > 1000 and float(z_['passo_s']) == EC.ENVELOPE_PASSO_SEC
                  and len(_json.loads(str(z_['cortes_finais']))) == 9 and EC.id_do_video(url2) in nome_med
                  and 'ffmpeg' in str(z_['gaps']) and float(z_['duracao_s']) > 100)
t(f'...e guardou as medidas em logs/medidas_do_editor ({nome_med}, '
  f'{arq_med.stat().st_size // 1024 if arq_med.exists() else 0} KB)', ok_med and arq_med.stat().st_size < 400_000)

# confiança baixa (Ruth Brown - "Sotfly" com o palpite "Peaks Iration - Zen Garden"): o palpite não entra
url3 = 'https://www.youtube.com/watch?v=4xfpPje_Qww'
dur3 = main.duracao_do_arquivo(disco)
videos_info[url3] = {'title': 'Ruth Brown - Sotfly (FULL ALBUM)', 'duration': dur3, 'description': '',
                     'chapters': [{'title': n, 'start_time': a_, 'end_time': b_}
                                  for n, a_, b_ in zip(RAY, inicios, inicios[1:] + [dur3])]}
pq.add(kind='baixa_confianca', url=url3, video_title='Ruth Brown - Sotfly (FULL ALBUM)', title_artist='Ruth Brown',
       title_album='Sotfly', confidence_pct=0, reason='Confiança 0% abaixo do mínimo automático (60%) - score=-27',
       discogs_data={'title': 'Zen Garden', 'artists': ['Peaks Iration'],
                     'tracks': [{'title': f'Zen {k}', 'duration': 0} for k in range(6)]})
EC.guardar_audio(base_app, url3, disco)
J.recarregar(); esperar2(0.5)
item3 = next(i for i in pq.items if i['url'] == url3)
J.tree.selection_set(item3['id']); esperar2()
app._janela_editor = None
J.editar()
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
je3 = app._janela_editor
t(f'confiança baixa: o editor não usa o palpite do Discogs (outro disco) - "{je3.ed.titulo if je3 else None}"',
  je3 is not None and je3.ed.oficiais == [] and 'Peaks' not in je3.ed.titulo and 'Ruth Brown' in je3.ed.titulo
  and je3.disco and not any('Zen' in n for i in range(10) for _, n in je3.ed.candidatos_da_faixa(i)))
t(f'...cortes e nomes sugeridos pelos capítulos do vídeo ({getattr(je3.ed, "fonte_dos_cortes", None)})',
  je3.ed.nomes() == RAY and len(je3.ed.marcas) == 9
  and getattr(je3.ed, 'fonte_dos_cortes', '') == 'capítulos do vídeo'
  and max(abs(m['pos'] - r) for m, r in zip(je3.ed.marcas, inicios[1:])) < 3)
# 12.21: reabrir o mesmo disco não lê o vídeo de novo nem refaz os cortes (ficaram guardados)
leituras_video = []
_info_orig = app.downloader.get_video_info
app.downloader.get_video_info = lambda u, *a, **k: (leituras_video.append(u), videos_info.get(u, {}))[1]
_ini_orig = EC.Edicao._marcas_iniciais
EC.Edicao._marcas_iniciais = lambda *a: (_ for _ in ()).throw(RuntimeError('cortou de novo'))
je3.fechar(perguntar=False); esperar2(0.2)
app._janela_editor = None
t0_ = time.time()
J.editar()
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
t_reabrir = time.time() - t0_
je3 = app._janela_editor
__import__('gc').collect()            # a tela fechada (com as variáveis do Tk) vai embora aqui, na thread principal
EC.Edicao._marcas_iniciais, app.downloader.get_video_info = _ini_orig, _info_orig
t(f'reabrir: sem ler o vídeo de novo e com os mesmos cortes e nomes ({t_reabrir:.1f}s)',
  je3 is not None and not leituras_video and je3.ed.nomes() == RAY and len(je3.ed.marcas) == 9
  and getattr(je3.ed, 'fonte_dos_cortes', '') == 'capítulos do vídeo')
je3.v_album.set(''); erros_salvar = []
_mb_err = __import__('tkinter').messagebox.showerror
__import__('tkinter').messagebox.showerror = lambda *a, **k: erros_salvar.append(a)
je3.salvar(); esperar2(0.3)
t('...sem o nome do álbum não salva (pede pra escrever)', erros_salvar and je3.win.winfo_exists())
# 12.19: uma lista de faixas colada no campo do artista virou o nome da pasta (WinError 123) e o disco se perdeu
je3.v_album.set('Softly'); erros_salvar.clear()
je3.v_artista.set('01 - Eu sei que vou te amar (Tom Jobim/Vinícius de Moraes)\n02 - Paca tatu, cotia não\n03 - Cor de Rosa')
je3.salvar(); esperar2(0.3)
t(f'...lista colada no campo do artista: não salva e explica ({str(erros_salvar[-1:])[:70]})',
  erros_salvar and 'lista colada' in str(erros_salvar[-1]) and je3.win.winfo_exists()
  and not next(i for i in pq.items if i['url'] == url3).get('tempos_usuario'))
je3.v_artista.set('Ruth Brown')
je3.v_album.set('Softly'); je3.v_ano.set('1957')
je3.salvar(); esperar2(0.4)
__import__('tkinter').messagebox.showerror = _mb_err
it3 = next(i for i in pq.items if i['url'] == url3)
t('...ao salvar, o item guarda artista, álbum e ano da tela e vai sem o Discogs',
  it3.get('editor_sem_discogs') and it3['title_album'] == 'Softly' and it3['year'] == '1957'
  and it3['tempos_usuario'].startswith('#exato') and 'Editar' in it3['reason'])
ok3 = app._process_pending_video_item(it3)
arqs3 = sorted(glob.glob(os.path.join(base_app, 'Ruth Brown - Softly*', '*.mp3')))
t(f'...e o disco sai como Ruth Brown - Softly, com os nomes da tela ({len(arqs3)} faixas), nada de Zen Garden',
  ok3 and len(arqs3) == 10 and str(ID3(arqs3[0]).get('TALB')) == 'Softly'
  and str(ID3(arqs3[0]).get('TPE1')) == 'Ruth Brown' and str(ID3(arqs3[1]).get('TIT2')) == RAY[1]
  and not glob.glob(os.path.join(base_app, 'Peaks*')))
pq.corrigir_busca(it3['id'], 'Ruth Brown', 'Softly')
t('Corrigir busca depois do editor: a busca nova vale (o "sem Discogs" do editor sai)',
  not next(i for i in pq.items if i['url'] == url3).get('editor_sem_discogs'))

# "talvez outro disco": os campos do item têm o nome do disco errado - o editor usa o título do vídeo
url4 = 'https://www.youtube.com/watch?v=OutroDisco1'
videos_info[url4] = {'title': 'Ruth Brown - Softly (1957) FULL ALBUM', 'duration': dur3, 'description': ''}
pq.add(kind='outro_disco', url=url4, video_title='Ruth Brown - Softly (1957) FULL ALBUM', title_artist='Peaks Iration',
       title_album='Zen Garden', year='2014', confidence_pct=90, reason='Provavelmente é outro disco',
       discogs_data={'title': 'Zen Garden', 'artists': ['Peaks Iration'], 'year': '2014',
                     'tracks': [{'title': n, 'duration': c} for n, c in zip(RAY, cad)]})
EC.guardar_audio(base_app, url4, disco)
J.recarregar(); esperar2(0.5)
J.tree.selection_set(next(i for i in pq.items if i['url'] == url4)['id']); esperar2()
app._janela_editor = None
J.editar()
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
je4 = app._janela_editor
t(f'"talvez outro disco": artista, álbum e ano vêm do título do vídeo ({je4.dados_do_disco() if je4 else None})',
  je4 is not None and je4.dados_do_disco() == {'artista': 'Ruth Brown', 'album': 'Softly', 'ano': '1957'}
  and je4.ed.oficiais == [])
t('...e os nomes do palpite (talvez outro disco) não entram sozinhos (12.19)',
  je4.ed.fonte_dos_nomes() is None and not any(n in RAY for n in je4.ed.nomes()))
je4.fechar(perguntar=False)

# ✂ Editar disco (tela principal): pasta já cortada -> tela -> salvar -> regrava
from tkinter import messagebox as _mb
avisos_mb, erros_mb = [], []
_mb.showinfo = lambda *a, **k: avisos_mb.append(a)
_mb.showerror = lambda *a, **k: erros_mb.append(a)
app._janela_editor = None
app.abrir_editor_pasta(str(pasta))
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
je = app._janela_editor
base_app = app.config.get_output_directory()
juntados = list(EC.pasta_audios(base_app).glob('_editando_*.mp3'))
t('✂ Editar disco: abre a tela com os 9 pedaços de agora e os nomes das tags',
  je is not None and len(je.ed.marcas) == 8 and je.ed.nomes()[8].startswith('Over The Rainbow') and juntados)
je.ed.marcar(je.ed.marcas[-1]['pos'] + 60.0)            # mais um corte
je.redesenhar()
je.salvar()
for _ in range(600):
    esperar2(0.05)
    if avisos_mb:
        break
t(f'...salvar regrava a pasta ({len(list(pasta.glob("*.mp3")))} faixas), avisa e apaga o arquivo juntado',
  avisos_mb and len(list(pasta.glob('*.mp3'))) == 10 and not list(EC.pasta_audios(base_app).glob('_editando_*.mp3')))
t('...e a tela só fecha depois de gravado (se falhar, as marcas continuam lá)', je.salvou and not je.win.winfo_exists())
# abrir e salvar sem mudar nada: não regrava (MP3 recodificado à toa perde qualidade)
mtimes = {p.name: p.stat().st_mtime for p in pasta.glob('*.mp3')}
avisos_mb.clear(); app._janela_editor = None
app.abrir_editor_pasta(str(pasta))
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
t(f'abre de novo a mesma pasta ({erros_mb})', app._janela_editor is not None)
app._janela_editor.salvar(); esperar2(0.5)
t('salvar sem mudar nada: avisa "Nada mudou" e não regrava a pasta',
  avisos_mb and 'Nada mudou' in avisos_mb[0][1] and {p.name: p.stat().st_mtime for p in pasta.glob('*.mp3')} == mtimes
  and not list(EC.pasta_audios(base_app).glob('_editando_*.mp3')))
# 12.19: mesmo sem mudança, os cortes do disco já conferido viram gabarito (medidas + linha "sem_mudanca")
ult = _json.loads(EC.caminho_correcoes(base_app).read_text(encoding='utf-8').splitlines()[-1])
med = EC.caminho_medidas_editor(base_app) / (ult.get('medidas') or '-')
with np.load(str(med)) as z_:
    cortes_med = _json.loads(str(z_['cortes_finais']))
t(f'...mas guarda as medidas do disco com os cortes de agora ({ult.get("medidas")}) sem contar no resumo',
  ult.get('sem_mudanca') and med.exists() and len(cortes_med) == 9
  and 'sem_mudanca' not in str(EC.resumo_correcoes(base_app)))
# 12.21: 🗑 Apagar pedaço também no ✂ Editar disco (a faixa 3 sai e as de depois andam uma casa)
antes_ap = [str(ID3(str(p_)).get('TIT2')) for p_ in sorted(pasta.glob('*.mp3'))]
avisos_mb.clear(); app._janela_editor = None
app.abrir_editor_pasta(str(pasta))
for _ in range(1600):
    esperar2(0.05)
    if getattr(app, '_janela_editor', None) is not None:
        break
jp = app._janela_editor
jp.tabela.selection_set('2'); esperar2(0.3)
t('Editar disco: botão "🗑 Apagar pedaço"', jp.b_apagar_peca.winfo_exists() and 'Apagar pedaço' in jp.b_apagar_peca.cget('text'))
jp.apagar_peca(); esperar2(0.2)
linha2, linha3 = jp.tabela.item('2', 'values'), jp.tabela.item('3', 'values')
t(f'...o pedaço do cursor fica "— apagado —" (cinza, riscado), o seguinte vira o nº 3 ({linha2[:2]}, {linha3[:2]})',
  linha2[1] == '— apagado —' and 'apagado' in jp.tabela.item('2', 'tags') and str(linha3[0]) == '3'
  and 'Desfazer' in jp.b_apagar_peca.cget('text')
  and any('apagado' in w.cget('text') for f in jp.avisos.winfo_children() for w in f.winfo_children()))
jp.apagar_peca(); esperar2(0.2)
t('...de novo: volta', jp.tabela.item('2', 'values')[1] == antes_ap[2] and not jp.ed.apagados)
jp.apagar_peca(); esperar2(0.1)
jp.salvar()
for _ in range(600):
    esperar2(0.05)
    if avisos_mb:
        break
depois_ap = sorted(pasta.glob('*.mp3'))
t(f'...salvar: a pasta fica com {len(depois_ap)} faixas, sem a apagada e numeradas sem buraco ({depois_ap[2].name if len(depois_ap) > 2 else ""})',
  len(depois_ap) == len(antes_ap) - 1 and [str(ID3(str(p_)).get('TIT2')) for p_ in depois_ap] == antes_ap[:2] + antes_ap[3:]
  and depois_ap[2].name.startswith('03 - ') and str(ID3(str(depois_ap[-1])).get('TRCK')) == f'{len(depois_ap)}/{len(depois_ap)}')
ult_ap = _json.loads(EC.caminho_correcoes(base_app).read_text(encoding='utf-8').splitlines()[-1])
t('...e o arquivo de correções anota o pedaço apagado', [x_['faixa'] for x_ in ult_ap.get('pecas_apagadas') or []] == [3])
root.destroy()
fim()

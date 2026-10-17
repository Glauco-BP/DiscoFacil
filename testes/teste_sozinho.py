"""
12.21 - gravar sozinho o disco que o Discogs não confirmou (gravar_sozinho.py), as propostas 1 e 2
do refinamento com as correções do ✂ Editar:
  - as travas, uma a uma, numa edição montada à mão (casos das 30 edições de 13 a 17/10);
  - de ponta a ponta, com discos sintéticos e um "YouTube" falso (sem internet): proposta 1 (lista do
    vídeo, nomes a conferir), proposta 2 ("Track N" + "Gravados com Track N"), e os que ficam em
    "Precisam de você" (pedaço curto, tempos da lista fora das pausas, lista que não bate, título sem
    álbum), com o áudio já guardado pro ✂ Editar.
"""
import os, sys, shutil, glob, types, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import numpy as np
from sint import musica, silencio, fade, salvar, SR
from pathlib import Path
from mutagen.id3 import ID3
import main
import edicao_cortes as EC
import gravar_sozinho as GS
from pending_queue import PendingQueue

# ------------------------------------------------------------------ as travas, numa edição montada à mão


def edicao(durs, pausa=3.0, tipos=None, pausas=None):
    """Pedaços com estas durações; cada corte no meio de uma pausa (de `pausa` s, ou pausas[k])."""
    ed = EC.Edicao('nada.wav', [], titulo='x')
    acc, ed.marcas, ed.silencios = 0.0, [], []
    for k, d in enumerate(durs[:-1]):
        acc += d
        p = (pausas or [pausa] * len(durs))[k]
        ed.silencios.append((acc - p / 2, acc + p / 2, 3))
        ed.marcas.append({'pos': acc, 'tipo': (tipos or {}).get(k, 'silencio')})
    ed.duracao = acc + durs[-1]
    ed.rotular()
    return ed


def video(ed, nomes, fonte='capítulos do vídeo', com_tempos=True, desvio=0.0):
    """A lista do vídeo (como editor_acoes._nomes_do_video): nomes e, se for o caso, os tempos."""
    tempos = [0.0] + [m['pos'] + desvio for m in ed.marcas] if com_tempos else None
    fontes = [(fonte, list(nomes), tempos)]
    for f, nm, _ in fontes:
        ed.adicionar_candidatos(f, nm)
    ed.rotular()
    return fontes


DURS = [194, 166, 169, 161, 267, 188, 125, 116, 194, 243, 160]       # Antônio Adolfo e a Brazuca (11 pedaços)
NOMES = [f'Música {k + 1}' for k in range(len(DURS))]
ed = edicao(DURS)
r = GS.avaliar(ed, [], 'Antônio Adolfo E A Brazuca', 'Antônio Adolfo')
t(f'pausas claras, pedaços de 116 a 267 s, o vídeo sem lista: proposta 2, "Track N" ({r["decisao"]}: {r["motivo"]})',
  r['decisao'] == 'P2' and r['nomes'][:2] == ['Track 1', 'Track 2'] and len(r['nomes']) == 11)
ed = edicao(DURS)
r = GS.avaliar(ed, video(ed, NOMES), 'Bola Sete', 'Bossa Nova')
t(f'com os capítulos do vídeo (mesmo nº e tempos nas pausas): proposta 1, com os nomes ({r["fonte"]})',
  r['decisao'] == 'P1' and r['nomes'] == NOMES and r['fonte'] == 'capítulos do vídeo')
ed = edicao(DURS)
r = GS.avaliar(ed, video(ed, NOMES, fonte='descrição do vídeo', com_tempos=False), 'Copa Combo', 'Bossa E Agogô')
t('...lista da descrição sem tempos, com o mesmo nº: proposta 1 também', r['decisao'] == 'P1' and r['nomes'] == NOMES)
# Breno Sauer: um corte a mais deixava um pedaço de 57 s
ed = edicao([193, 169, 198, 151, 195, 189, 164, 179, 156, 122, 57, 217, 175])
r = GS.avaliar(ed, [], 'Breno Sauer', 'Quatro Na Bossa')
t(f'pedaço de 57 s (Breno Sauer, o corte que você apagou): fica pra você ({r["motivo"]})',
  r['decisao'] is None and '57 s' in r['motivo'])
ed = edicao([173, 171, 217, 89.5, 153, 159, 186])
t('...89,5 s também (a trava é 90 s)', GS.avaliar(ed, [], 'Tempo Trio', 'Tempo Trio')['decisao'] is None)
ed = edicao([200, 180, 210, 640, 190, 205])
r = GS.avaliar(ed, [], 'X', 'Y')
t(f'pedaço comprido demais (2 músicas juntas?): fica ({r["motivo"]})', r['decisao'] is None and 'juntas' in r['motivo'])
ed = edicao(DURS, tipos={4: 'estimado'})
r = GS.avaliar(ed, [], 'X', 'Y')
t(f'um corte estimado (sem silêncio): fica ({r["motivo"]})', r['decisao'] is None and 'silêncio claro' in r['motivo'])
ed = edicao(DURS, pausas=[3.0] * 5 + [0.7] + [3.0] * 5)
r = GS.avaliar(ed, [], 'X', 'Y')
t(f'um corte numa pausa de 0,7 s: fica ({r["motivo"]})', r['decisao'] is None and 'pausa curta' in r['motivo'])
ed = edicao([200, 190, 210])
t('só 3 pedaços: fica', GS.avaliar(ed, [], 'X', 'Y')['decisao'] is None)
ed = edicao(DURS)
r = GS.avaliar(ed, [], 'Wes Montgomery', 'Full Album')
t(f'"Fulano - Full Album" (sem o álbum): fica ({r["motivo"]})', r['decisao'] is None and 'título' in r['motivo'])
t('disco com o nome do artista ("Som 3 - Som 3") e com nome de gênero ("Bola Sete - Bossa Nova") valem',
  GS.avaliar(edicao(DURS), [], 'Som 3', 'Som 3')['decisao'] == 'P2'
  and GS.avaliar(edicao(DURS), [], 'Bola Sete', 'Bossa Nova')['decisao'] == 'P2')
G0 = main.FullTracksDownloaderGUI.__new__(main.FullTracksDownloaderGUI)
t('o título precisa ter "Artista - Álbum" (com o traço)', G0._titulo_tem_artista_e_album('Som 3 - Som 3 (1966)')
  and G0._titulo_tem_artista_e_album('João Gilberto - João Gilberto (1961) Full Album')
  and not G0._titulo_tem_artista_e_album('Wes Montgomery (Jazz)')
  and not G0._titulo_tem_artista_e_album('Fulano (1970) Full Album'))
r = GS.avaliar(ed, [], '01 - Eu sei que vou te amar\n02 - Paca tatu', 'Disco')
t('artista com lista colada: fica', r['decisao'] is None)
# Edu Lôbo: os tempos do comentário não caíam nas pausas
ed = edicao(DURS)
fontes = video(ed, NOMES, fonte='comentário do vídeo', desvio=9.0)
r = GS.avaliar(ed, fontes, 'Edu Lôbo', 'Cantiga de Longe')
t(f'lista do comentário com os tempos 9 s fora das pausas (Edu Lôbo): fica ({r["motivo"]})',
  r['decisao'] is None and 'não cai na pausa' in r['motivo'])
ed = edicao(DURS)
r = GS.avaliar(ed, video(ed, NOMES[:9], fonte='descrição do vídeo', com_tempos=False), 'Búzios', 'Búzios Live')
t(f'lista do vídeo com 9 músicas e 11 pedaços: nem nomes nem "Track N" ({r["motivo"]})',
  r['decisao'] is None and '9 músicas' in r['motivo'])
ed = edicao(DURS)
ed.adicionar_candidatos('palpite do Discogs', NOMES)          # o palpite pode ser outro disco
r = GS.avaliar(ed, [('palpite do Discogs', NOMES, None)], 'X', 'Y')
t('o palpite do Discogs nunca dá nome (mesmo com o mesmo nº): "Track N"', r['decisao'] == 'P2'
  and r['nomes'][0] == 'Track 1')
ed = edicao(DURS)
r = GS.avaliar(ed, video(ed, [f'Track {k + 1}' for k in range(11)]), 'X', 'Y')
t('lista do vídeo só com "Track N": não é nome', r['decisao'] is None)
ed = edicao(DURS)
txt = GS.texto_dos_cortes(ed, NOMES)
lidos = EC.ler_tempos_exatos(txt)
t('os cortes vão no formato do ✂ Editar (#exato), com os nomes', lidos and len(lidos) == 11
  and lidos[1]['title'] == 'Música 2' and abs(lidos[1]['start_time'] - 194) < 0.01)

# ------------------------------------------------------------------ de ponta a ponta (sem internet)
D = [150, 128, 165, 140, 172, 135]                  # 6 músicas, 2,5 s de pausa entre elas
NOMES6 = ['Samba De Uma Nota Só', 'Desafinado', 'Corcovado', 'Chega De Saudade', 'Insensatez', 'Meditação']


def disco(durs, nome, pausa=2.5):
    partes, inicios, pos = [], [], 0.0
    for k, d in enumerate(durs):
        inicios.append(pos)
        partes += [musica(d - 1), fade(musica(1))]
        pos += d
        if k < len(durs) - 1:
            partes.append(silencio(pausa)); pos += pausa
    return salvar(np.concatenate(partes), nome), inicios


wav6, ini6 = disco(D, 'sozinho_6.wav')
wav_curto, ini_curto = disco([150, 128, 60, 140, 172, 135], 'sozinho_curto.wav')
dur6 = main.duracao_do_arquivo(wav6)
out = tmp('sozinho', 'SOM', 'x')[:-2]; shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
g.config = types.SimpleNamespace(get_output_directory=lambda: out, get=lambda *a, **k: None)
g.metadata_manager = main.MetadataManager(); g.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 60
g.acervo_index = types.SimpleNamespace(add=lambda *a, **k: None, has=lambda *a: False)
g._ensure_acervo_and_queue = lambda: None
g.groq = None; g.pre_download = None; g._notas_corte = {}; g.stats = {'albums_skipped': 0}
g.pending_queue = PendingQueue(out)
videos, arquivos, baixados = {}, {}, []


def baixar(url, pasta, progresso=None):
    baixados.append(url)
    if url not in arquivos:
        return None
    destino = os.path.join(pasta, EC.id_do_video(url) + '.wav')
    shutil.copy2(arquivos[url], destino)
    return destino


g.downloader = types.SimpleNamespace(get_video_info=lambda u, *a, **k: videos.get(u), download_audio=baixar,
                                     comentarios=lambda *a, **k: [], last_error='x', last_error_retryable=False)
# o Discogs acha um palpite com confiança baixa (outro disco): nunca dá nome
palpite = {'title': 'Zen Garden', 'artists': ['Peaks Iration'], 'year': '2001', 'confidence_pct': 30, 'score': -10,
           'master_id': None, 'release_id': 1,
           'tracks': [{'number': k + 1, 'title': f'Zen {k + 1}', 'duration': '2:30'} for k in range(6)]}
g.catalogo = types.SimpleNamespace(last_error=None, discogs=lambda *a, **k: [dict(palpite)],
                                   musicbrainz=lambda *a, **k: None, musicbrainz_edicoes=lambda *a, **k: [],
                                   ultimo_motivo_mb='x', deezer=lambda *a: None, itunes=lambda *a: None)


def capitulos(nomes, inicios, dur, desvio=0.0):
    return [{'title': n, 'start_time': (a + desvio) if a else 0.0, 'end_time': b}
            for n, a, b in zip(nomes, inicios, inicios[1:] + [dur])]


def pasta_de(prefixo):
    return sorted(p for p in glob.glob(os.path.join(out, prefixo + '*')) if os.path.isdir(p))


def item(url):
    return next((i for i in g.pending_queue.items if i['url'] == url and i['kind'] != 'track_n'), None)


# proposta 1: os capítulos do vídeo dão os nomes
u1 = 'https://www.youtube.com/watch?v=Sozinho0001'
videos[u1] = {'title': 'João Gilberto - O Amor, O Sorriso E A Flor (1960) Full Album', 'duration': dur6,
              'description': '', 'chapters': capitulos(NOMES6, ini6, dur6)}
arquivos[u1] = wav6
logs.clear()
g.process_single_video(u1)
p1 = pasta_de('João Gilberto - O Amor')
arqs1 = sorted(glob.glob(os.path.join(p1[0], '*.mp3'))) if p1 else []
tags1 = [ID3(a) for a in arqs1]
t(f'proposta 1 (confiança baixa, capítulos no vídeo): gravado sozinho com os nomes dos capítulos '
  f'({[os.path.basename(a) for a in arqs1[:2]]})',
  len(arqs1) == 6 and [str(x.get('TIT2')) for x in tags1] == NOMES6 and str(tags1[0].get('TALB')) == 'O Amor, O Sorriso E A Flor'
  and str(tags1[0].get('TPE1')) == 'João Gilberto' and not any('Zen' in str(x.get('TIT2')) for x in tags1))
t('...marcado "conferir" nas tags, sem ir pra Precisam de você e sem lembrete de "Track N"',
  all('conferir' in str(x.get('TXXX:DISCOFACIL_NOTA')) for x in tags1) and not g.pending_queue.items)
durs1 = [main.duracao_do_arquivo(a) for a in arqs1]
t(f'...cada faixa do tamanho certo (pior {max(abs(a - b) for a, b in zip(durs1, D)) if durs1 else 99:.1f}s)',
  durs1 and max(abs(a - b) for a, b in zip(durs1, D)) <= 3.0)
t('...o log e o arquivo da rodada dizem que foi sozinho', any('Gravo sozinho' in l for l in logs)
  and any(l.startswith('REG SOZINHO') and 'P1' in l for l in logs))
t('...e o áudio guardado pro ✂ Editar foi apagado (o disco está pronto)', EC.audio_guardado(out, u1) is None)

# proposta 2: sem lista no vídeo - "Track N" e o lembrete em "Gravados com Track N"
u2 = 'https://www.youtube.com/watch?v=Sozinho0002'
videos[u2] = {'title': 'Tamba 4 - Samba Blim (1968)', 'duration': dur6, 'description': 'Disco lindo.', 'chapters': []}
arquivos[u2] = wav6
g.pending_queue.add(kind='falha_corte', url='https://youtu.be/velho000001', video_title='outro', reason='x')
g.pending_queue.anotar_track_n(u2, 'Tamba 4 (antigo)', os.path.join(out, 'pasta velha'), 3, 6)
velho_ts = g.pending_queue.items[-1]['gravado_ts']
time.sleep(0.05)
g._inicio_item_fila = time.time()                   # como o trabalhador da fila faz
logs.clear()
g.process_single_video(u2)
p2 = pasta_de('Tamba 4 - Samba Blim')
arqs2 = sorted(glob.glob(os.path.join(p2[0], '*.mp3'))) if p2 else []
tn = [i for i in g.pending_queue.items if i['kind'] == 'track_n']
t(f'proposta 2 (sem lista no vídeo): gravado sozinho com "Track N" ({[os.path.basename(a) for a in arqs2[:2]]})',
  len(arqs2) == 6 and os.path.basename(arqs2[0]) == '01 - Track 1.mp3' and str(ID3(arqs2[0]).get('TALB')) == 'Samba Blim')
t(f'...e entrou em "Gravados com Track N" com a pasta (o lembrete velho do mesmo vídeo saiu) ({tn[0]["reason"][:50] if tn else ""})',
  len(tn) == 1 and tn[0]['url'] == u2 and Path(tn[0]['pasta']) == Path(p2[0]) and '6 de 6' in tn[0]['reason']
  and tn[0]['gravado_ts'] > velho_ts)
g._tirar_das_pendencias(u2, 'concluído')
t('...o fim do item na fila não tira o lembrete que esta rodada anotou',
  [i['kind'] for i in g.pending_queue.items if i['url'] == u2] == ['track_n'])

# pedaço curto (60 s): fica em Precisam de você, com o motivo, e o áudio guardado pro ✂ Editar
u3 = 'https://www.youtube.com/watch?v=Sozinho0003'
videos[u3] = {'title': 'Breno Sauer - Quatro Na Bossa (1963)', 'duration': main.duracao_do_arquivo(wav_curto),
              'description': '', 'chapters': []}
arquivos[u3] = wav_curto
logs.clear()
g.process_single_video(u3)
it3 = item(u3)
t(f'pedaço de 60 s: não grava, fica em Precisam de você com o motivo ({(it3 or {}).get("reason", "")[-60:]})',
  it3 and it3['kind'] == 'baixa_confianca' and 'não gravei sozinho' in it3['reason'] and 'pedaço 3 tem só' in it3['reason']
  and not pasta_de('Breno Sauer'))
med3 = EC.arquivo_de_medidas(out, u3)
lido3 = EC.ler_medidas(med3, EC.audio_guardado(out, u3)) if EC.audio_guardado(out, u3) else {}
t('...com o áudio já guardado e medido: o ✂ Editar abre sem baixar nem medir de novo',
  EC.audio_guardado(out, u3) is not None and lido3.get('envelope') is not None and lido3.get('marcas')
  and lido3.get('fontes') == [])

# tempos dos capítulos fora das pausas (Edu Lôbo): fica
u4 = 'https://www.youtube.com/watch?v=Sozinho0004'
videos[u4] = {'title': 'Edu Lôbo - Cantiga De Longe (1970)', 'duration': dur6, 'description': '',
              'chapters': capitulos(NOMES6, ini6, dur6, desvio=12.0)}
arquivos[u4] = wav6
logs.clear()
g.process_single_video(u4)
it4 = item(u4)
t(f'capítulos com os tempos 12 s fora das pausas: fica em Precisam de você ({(it4 or {}).get("reason", "")[-70:]})',
  it4 and 'não gravei sozinho' in it4['reason'] and not pasta_de('Edu Lôbo'))

# lista na descrição com 5 nomes e 6 pedaços: nem nomes nem "Track N"
u5 = 'https://www.youtube.com/watch?v=Sozinho0005'
videos[u5] = {'title': 'Som 3 - Som 3 (1966)', 'duration': dur6, 'chapters': [],
              'description': 'Faixas:\n' + '\n'.join(f'{k + 1}. {n}' for k, n in enumerate(NOMES6[:5]))}
arquivos[u5] = wav6
logs.clear()
g.process_single_video(u5)
it5 = item(u5)
t(f'lista da descrição com 5 músicas e 6 pedaços: fica ({(it5 or {}).get("reason", "")[-50:]})',
  it5 and 'não gravei sozinho' in it5['reason'] and not pasta_de('Som 3'))

# título sem o álbum: nem baixa
u6 = 'https://www.youtube.com/watch?v=Sozinho0006'
videos[u6] = {'title': 'Wes Montgomery (Jazz)', 'duration': dur6, 'description': '', 'chapters': []}
arquivos[u6] = wav6
baixados.clear()
g.process_single_video(u6)
t('título sem o álbum: não baixa nem tenta gravar sozinho (fica pra você, como antes)',
  item(u6) and not baixados and 'não gravei sozinho' not in item(u6)['reason'])

# download que falha: fica como antes
u7 = 'https://www.youtube.com/watch?v=Sozinho0007'
videos[u7] = {'title': 'Milton Banana - Balançando (1966)', 'duration': dur6, 'description': '', 'chapters': []}
g.process_single_video(u7)
t('download que falha: fica em Precisam de você como antes', item(u7) and item(u7)['kind'] == 'baixa_confianca'
  and not pasta_de('Milton Banana'))

# talvez outro disco (o áudio já guardado depois do corte que não bateu): o mesmo caminho
u8 = 'https://www.youtube.com/watch?v=Sozinho0008'
videos[u8] = {'title': 'Bola Sete - Bossa Nova (1962)', 'duration': dur6, 'description': '',
              'chapters': capitulos(NOMES6, ini6, dur6)}
g8 = EC.guardar_audio(out, u8, wav6)
logs.clear()
ok8 = g._tentar_gravar_sozinho(u8, videos[u8], audio=g8)
arqs8 = sorted(glob.glob(os.path.join(out, 'Bola Sete - Bossa Nova*', '*.mp3')))
t(f'talvez outro disco, com o áudio guardado: grava sozinho pelos capítulos ({len(arqs8)} faixas)',
  ok8 and len(arqs8) == 6 and str(ID3(arqs8[2]).get('TIT2')) == NOMES6[2])

# talvez outro disco de ponta a ponta: o Discogs confiante num disco que não cabe no áudio
u9 = 'https://www.youtube.com/watch?v=Sozinho0009'
videos[u9] = {'title': 'Baden Powell Quarteto - Vol 1 (1970)', 'duration': dur6, 'description': '', 'chapters': []}
arquivos[u9] = wav6
dd9 = {'title': 'Zen Garden', 'artists': ['Peaks Iration'], 'year': '2001', 'cover_image': None, 'confidence_pct': 90,
       'tracks': [{'number': i + 1, 'title': f'Zen {i + 1}', 'duration': f'{c // 60}:{c % 60:02d}'}
                  for i, c in enumerate([300, 120, 280, 90, 110])], 'discogs_master_id': None, 'discogs_release_id': 9}
logs.clear()
ok9 = g._download_and_process(u9, videos[u9], 'Peaks Iration', 'Zen Garden', '2001', 'discogs', dd9['tracks'], True, dd9)
arqs9 = sorted(glob.glob(os.path.join(out, 'Baden Powell Quarteto - Vol 1*', '*.mp3')))
t(f'talvez outro disco (o corte do Discogs não cabe): gravado sozinho com "Track N", sem nada do outro disco '
  f'({len(arqs9)} faixas)', ok9 and len(arqs9) == 6 and not pasta_de('Peaks Iration') and not item(u9)
  and any(i['kind'] == 'track_n' and i['url'] == u9 for i in g.pending_queue.items)
  and any('outro disco' in l for l in logs))

# o mesmo vídeo de novo (canal, fila): não grava um "(2)"
logs.clear()
g.process_single_video(u1)
t('o mesmo vídeo de novo: o disco já está gravado, não grava outra pasta "(2)" nem vai pra lista',
  len(pasta_de('João Gilberto - O Amor')) == 1 and not item(u1) and any('já foi gravado' in l for l in logs))

# o ✂ Editar abre igual ao que o "gravar sozinho" avaliou (mesma preparação, sem o palpite)
fontes6 = [('capítulos do vídeo', NOMES6, [c['start_time'] for c in capitulos(NOMES6, ini6, dur6)])]
eda = EC.edicao_sem_discogs(wav6, 'x', fontes6)
t(f'edicao_sem_discogs: cortes pelos capítulos, nos silêncios, e os nomes deles ({eda.nomes()[:2]})',
  eda.nomes() == NOMES6 and all(m['tipo'] == 'silencio' for m in eda.marcas) and len(eda.marcas) == 5)
fim()

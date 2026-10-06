"""
12.16 - Casos reais dos logs do usuário, com os números de verdade (nada aqui
usa a rede). Cada disco que já saiu errado vira um teste, pra nenhuma versão
futura voltar a errar:
  - Milton Banana "Vê": trocado depois do corte por "Aos Amigos Tom, Chico e
    Vinicius" (outro LP), com nomes juntados do outro disco;
  - Os Cobras: trocado por "Cobras Criadas" (Os Partideiros do Plá);
  - "Can't Play A Playgirl", Ray Charles "Forever"/"Ingredients": a regra de
    "mesmo disco" que vale em toda troca de edição;
  - Os Cobras no Deezer/iTunes (título que não bate), tempos num comentário do
    vídeo, e o botão "Informar tempos" de "Precisam de você".
"""
import os, sys, types, subprocess, time, shutil, glob
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1400x1000x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
import numpy as np
from pathlib import Path
from sint import *
import main
import catalogo as CAT
from mutagen.id3 import ID3
from pontuacao import mesmo_disco, titulos_do_mesmo_disco

# ------------------------------------------------------------------ a regra "mesmo disco"
t('"Vê" = "Ve" (acento)', titulos_do_mesmo_disco('Vê', 'Ve'))
t('"Vê" ≠ "Aos Amigos Tom, Chico E Vinicius"', not titulos_do_mesmo_disco('Vê', 'Aos Amigos Tom, Chico E Vinicius'))
t('"Os Cobras" ≠ "Cobras Criadas"', not titulos_do_mesmo_disco('Os Cobras', 'Cobras Criadas'))
t('"Forever" ≠ "Forever Gold"', not titulos_do_mesmo_disco('Forever', 'Forever Gold'))
t('"Samba E Violão" ≠ "Samba E Violão Vol. 2"', not titulos_do_mesmo_disco('Samba E Violão', 'Samba E Violão Vol. 2'))
t('"Ingredients In A Recipe For Soul" = "... (Remastered)"',
  titulos_do_mesmo_disco('Ingredients In A Recipe For Soul', 'Ingredients In A Recipe For Soul (Remastered)'))
t('compacto e coletânea "Can\'t Play A Playgirl": mesmo título, artista diferente = outro disco',
  not mesmo_disco({'title': "Can't Play A Playgirl", 'artists': ['The Jillettes']},
                  {'album_title': "Can't Play A Playgirl (1960's Girl Goodies Lost & Found)", 'artists': ['Various']}))
t('mesmo master do Discogs = mesmo disco, mesmo com título escrito diferente',
  mesmo_disco({'title': 'Vê', 'discogs_master_id': 3334399}, {'title': 'Ve (Remasterizado)', 'master_id': 3334399}))
t('"Os Cobras" (Os Cobras) ≠ "Cobras Criadas" (Os Partideiros Do Plá)',
  not mesmo_disco({'title': 'Os Cobras', 'artists': ['Os Cobras']},
                  {'album_title': 'Cobras Criadas', 'artists': ['Os Partideiros Do Plá']}))


# revisão independente (12.16): casos que a regra NÃO pode juntar
t('mesmo título e artista, masters diferentes (o artista tem 2 LPs com o nome dele) = discos diferentes',
  not mesmo_disco({'title': 'Caetano Veloso', 'artists': ['Caetano Veloso'], 'master_id': 1},
                  {'title': 'Caetano Veloso', 'artists': ['Caetano Veloso'], 'master_id': 2}))
t('"Vê" ≠ "Vê (Ao Vivo)" e ≠ "Vê [Vol. 2]" (o que está entre parênteses conta quando muda o disco)',
  not titulos_do_mesmo_disco('Vê', 'Vê (Ao Vivo)') and not titulos_do_mesmo_disco('Vê', 'Vê [Vol. 2]'))
t('título longo: "... Hits Vol 1" ≠ "... Hits Vol 2"',
  not titulos_do_mesmo_disco('The Best Of Milton Banana Trio Bossa Nova Hits Vol 1',
                             'The Best Of Milton Banana Trio Bossa Nova Hits Vol 2'))
t('"(2013 Remaster)" continua sendo o mesmo disco', titulos_do_mesmo_disco('Forever', 'Forever (2013 Remaster)'))
from pontuacao import artistas_parecidos
t('"Zimbo Trio" ≠ "Tamba Trio"; "Ray Charles and his Orchestra" ≠ "Count Basie and his Orchestra"',
  not artistas_parecidos('Zimbo Trio', 'Tamba Trio')
  and not artistas_parecidos('Ray Charles and his Orchestra', 'Count Basie and his Orchestra'))
t('"V.A." só é parecido com "Various"', not artistas_parecidos('V.A.', 'Ray Charles') and artistas_parecidos('V.A.', 'Various'))

# ------------------------------------------------------------------ reavaliação depois do corte
def app_sem_janela():
    G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
    g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
    g.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 60
    return g, logs


def cortador(fronteiras_min, total):
    pos = [0.0] + [m * 60 for m in fronteiras_min]
    cuts = [{'track': i + 1, 'title': f'Track {i + 1}', 'start': pos[i],
             'end': pos[i + 1] if i + 1 < len(pos) else None} for i in range(len(pos))]
    return types.SimpleNamespace(cuts=cuts, metadata=None)


# Milton Banana "Vê" (log de 03/10 21:13): 13 pedaços em 1700s; o Discogs não tem durações do "Vê"
VE_FRONT = [2.0, 4.8, 6.1, 7.5, 10.2, 12.0, 13.7, 16.1, 18.4, 20.4, 22.2, 25.9]
cut = cortador(VE_FRONT, 1700)
reais = [((c['end'] if c['end'] is not None else 1700) - c['start']) for c in cut.cuts]
ve = {'title': 'Vê', 'artists': ['Milton Banana Trio'], 'year': '1965', 'master_id': 1222837, 'release_id': 4469001,
      'tracks': [{'title': f'Música {i + 1} do Vê', 'duration': 0} for i in range(12)]}
# "Aos Amigos...": um LP de 14 faixas cujas durações juntadas FECHAM com os 13 pedaços (como no log)
aos = list(reais[:12]) + [reais[12] / 2, reais[12] / 2]
amigos = {'title': 'Aos Amigos Tom, Chico E Vinicius', 'artists': ['Milton Banana'], 'year': '1979',
          'master_id': 3334399, 'release_id': 9878165,
          'tracks': [{'title': f'Medley {i + 1}', 'duration': round(d)} for i, d in enumerate(aos)]}
dd = {'title': 'Vê', 'artists': ['Milton Banana Trio'], 'year': '1965', 'discogs_master_id': 1222837,
      'discogs_release_id': 4469001, 'titulo_buscado': 'Vê'}
g, logs = app_sem_janela()
meta = {'artist': 'Milton Banana Trio', 'album': 'Vê', 'year': '1965', 'tracks': []}
novo = g._reavaliar_com_o_corte(cut, meta, dd, [ve, amigos], {'duration': 1700})
t('Vê: "Aos Amigos Tom, Chico e Vinicius" fica de fora, mesmo encaixando nas durações',
  novo.get('discogs_release_id') == 4469001 and any('1 outro(s) disco(s) da busca ficam de fora' in l for l in logs))
t('...os 13 pedaços continuam "Track N" (nada de "Chega De Saudade / Desafinado")',
  [c['title'] for c in cut.cuts] == [f'Track {i + 1}' for i in range(13)] and not any('Medley' in c['title'] for c in cut.cuts))
t('...capa e IDs continuam os do "Vê"', novo.get('discogs_master_id') == 1222837 and meta['album'] == 'Vê')

# outra edição do MESMO "Vê", com durações que casam uma a uma: aí sim troca e nomeia
ve2 = {'title': 'Vê', 'artists': ['Milton Banana Trio'], 'year': '1968', 'master_id': 1222837, 'release_id': 5550002,
       'tracks': [{'title': f'Faixa {i + 1} do Vê', 'duration': round(d) + 1} for i, d in enumerate(reais)]}
cut = cortador(VE_FRONT, 1700)
g, logs = app_sem_janela()
novo = g._reavaliar_com_o_corte(cut, dict(meta, tracks=[]), dd, [ve, amigos, ve2], {'duration': 1700})
t('...outra edição do mesmo "Vê" com as durações: troca de edição e dá os nomes',
  novo.get('discogs_release_id') == 5550002 and [c['title'] for c in cut.cuts] == [f'Faixa {i + 1} do Vê' for i in range(13)])

# nº igual mas durações que não casam uma a uma: não nomeia (antes bastava ±1 faixa)
ve3 = dict(ve2, release_id=5550003, tracks=[{'title': f'X{i}', 'duration': 130} for i in range(13)])
cut = cortador(VE_FRONT, 1700)
g, logs = app_sem_janela()
g._reavaliar_com_o_corte(cut, dict(meta, tracks=[]), dd, [ve3], {'duration': 1700})
t('...mesmo nº de faixas sem as durações casarem: os nomes não entram',
  [c['title'] for c in cut.cuts] == [f'Track {i + 1}' for i in range(13)])
ve4 = dict(ve2, release_id=5550004, tracks=[{'title': f'Y{i}', 'duration': round(d)} for i, d in enumerate(reais[:12])])
cut = cortador(VE_FRONT, 1700)
g, logs = app_sem_janela()
g._reavaliar_com_o_corte(cut, dict(meta, tracks=[]), dd, [ve4], {'duration': 1700})
t('...1 faixa a menos (antes: nomes pela ordem, deslocados): os nomes não entram',
  [c['title'] for c in cut.cuts] == [f'Track {i + 1}' for i in range(13)])

# Os Cobras (mesmo log): 10 pedaços em 1980s; trocado por "Cobras Criadas", de outro artista
CB_FRONT = [2.8, 5.8, 8.3, 11.1, 13.5, 15.6, 18.4, 23.9, 26.9]
cut = cortador(CB_FRONT, 1980)
reais_cb = [((c['end'] if c['end'] is not None else 1980) - c['start']) for c in cut.cuts]
cobras = {'title': 'Os Cobras', 'artists': ['Os Cobras'], 'year': '1960', 'release_id': 8325155,
          'tracks': [{'title': n, 'duration': 0} for n in ['Cheiro De Saudade', 'Love Me Or Leave Me',
                     'Do Jeito Que A Gente Quer', 'Doce Melancolia', 'Misty', 'Menina Feia', 'É Bom Assim', 'Athena',
                     'A Flor Do Amor', "Don'Cha Go Way Mad", 'Bateria Maluco']]}
criadas = {'title': 'Cobras Criadas', 'artists': ['Os Partideiros Do Plá'], 'year': '1973', 'release_id': 1253694,
           'tracks': [{'title': f'Samba {i}', 'duration': round(d)} for i, d in
                      enumerate(reais_cb[:9] + [reais_cb[9] / 3, reais_cb[9] / 3, reais_cb[9] / 3])]}
dd_cb = {'title': 'Os Cobras', 'artists': ['Os Cobras'], 'year': '1960', 'discogs_release_id': 8325155,
         'titulo_buscado': 'Os Cobras'}
g, logs = app_sem_janela()
novo = g._reavaliar_com_o_corte(cut, {'artist': 'Os Cobras', 'album': 'Os Cobras', 'year': '1960', 'tracks': []},
                                dd_cb, [cobras, criadas], {'duration': 1980})
t('Os Cobras: "Cobras Criadas" (outro artista) fica de fora; capa e IDs continuam os d\'Os Cobras',
  novo.get('discogs_release_id') == 8325155 and not any('Samba' in c['title'] for c in cut.cuts))

# ano: o do lançamento, não o da reedição que casou melhor
ve5 = dict(ve2, release_id=5550005, year='2003')
cut = cortador(VE_FRONT, 1700)
g, logs = app_sem_janela()
meta5 = dict(meta, tracks=[])
novo = g._reavaliar_com_o_corte(cut, meta5, dd, [ve, ve5], {'duration': 1700})
t('...trocando pela reedição de 2003 do mesmo disco, o ano continua 1965',
  novo.get('discogs_release_id') == 5550005 and meta5['year'] == '1965' and novo.get('year') == '1965')

# ------------------------------------------------------------------ lojas: título sem par
COBRAS_T = ['Cheiro De Saudade', 'Love Me Or Leave Me', 'Do Jeito Que A Gente Quer', 'Doce Melancolia', 'Misty',
            'Menina Feia', 'É Bom Assim', 'Athena', 'A Flor Do Amor', "Don´Cha Go Way Mad", 'Bateria Maluco']
loja = [{'title': x, 'seg': 150 + i} for i, x in enumerate(COBRAS_T)]
loja[9] = {'title': "Don't You Go 'Way Mad", 'seg': 159}           # escrito diferente na loja
r, sem_par, na_loja = CAT.Catalogo._casar_titulos(COBRAS_T, loja)
t('loja: 1 título escrito diferente, todos os outros na mesma posição → vale pela posição',
  r and r[9]['duration'] == 159 and sem_par == ["Don´Cha Go Way Mad"] and na_loja == ["Don't You Go 'Way Mad"])
loja2 = [dict(x) for x in loja]
loja2[2], loja2[3] = loja[3], loja[2]                                  # e mais 2 fora de ordem
loja2[5] = {'title': 'Outra Coisa', 'seg': 155}
loja2[6] = {'title': 'Mais Outra', 'seg': 156}
r, sem_par, _ = CAT.Catalogo._casar_titulos(COBRAS_T, loja2)
t('...títulos fora de ordem e 3 sem par: não vale (sem chute)', r is None and len(sem_par) == 3)


class Resp:
    def __init__(self, dados):
        self.dados, self.status_code = dados, 200

    def json(self):
        return self.dados


class SessaoDeezer:
    def get(self, url, params=None, timeout=None, headers=None):
        if url.endswith('search/album'):
            return Resp({'data': [{'id': 1, 'title': 'Os Cobras', 'nb_tracks': 11, 'artist': {'name': 'Os Cobras'}}]})
        return Resp({'data': [{'title': x['title'], 'duration': x['seg']} for x in loja2]})


cat = CAT.Catalogo({}); cat.session = SessaoDeezer(); CAT.AjustesCatalogo.DEEZER_INTERVALO_SEG = 0
t('...e o log diz quais títulos não bateram e o que a loja tinha no lugar',
  cat.deezer('Os Cobras', 'Os Cobras', COBRAS_T) is None
  and "'Menina Feia' (na loja: 'Outra Coisa')" in cat.ultimo_motivo_deezer)

# ------------------------------------------------------------------ tempos num comentário do vídeo
def plana(seg):
    x = np.convolve(rng.standard_normal(int(seg * SR)), np.ones(8) / 8, 'same')
    return 0.3 * x / np.std(x)


DCB = [170, 179, 146, 170, 140, 129]
EMEND = (2, 4)                      # sem pausa DEPOIS da 3ª e da 5ª (músicas emendadas)
partes, inicios_reais, pos = [], [], 0.0
for i, d in enumerate(DCB):
    inicios_reais.append(pos)
    if i in EMEND or (i - 1) in EMEND:
        partes.append(plana(d)); pos += d
    else:
        partes += [musica(d - 1), fade(musica(1))]; pos += d
    if i not in EMEND and i < len(DCB) - 1:
        partes.append(silencio(2.0)); pos += 2.0
disco = salvar(np.concatenate(partes), 'reais_cobras.wav')
dur_disco = main.duracao_do_arquivo(disco)
NOMES6 = COBRAS_T[:6]


def mss(x):
    return f"{int(x // 60)}:{int(round(x % 60)):02d}"


desvio = [0, 1.5, -2, 1, -1.5, 2]          # quem digitou errou uns segundos
comentario = '\n'.join(f"{i + 1:02d} - {n} {mss(max(0, ini + dv))}" for i, (n, ini, dv) in
                       enumerate(zip(NOMES6, inicios_reais, desvio)))
comentarios = ['Que disco lindo! Meu pai tinha esse LP. 2:50 é demais', comentario,
               '0:00 Outra Lista\n3:00 De Outro Disco\n6:00 Com Seis\n9:00 Linhas\n12:00 Que Não\n15:00 Batem']


class Baixador:
    def __init__(self, coments):
        self.coments, self.pedidos = coments, 0
        self.last_error = None

    def comentarios(self, url, maximo=None):
        self.pedidos += 1
        return self.coments

    def download_audio(self, url, pasta, progresso=None):
        destino = os.path.join(pasta, 'audio.wav'); shutil.copy(disco_atual[0], destino); return destino


def app_disco(saida, coments):
    G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
    g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
    g.config = types.SimpleNamespace(get_output_directory=lambda: saida, get=lambda *a, **k: None)
    g.metadata_manager = main.MetadataManager(); g.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 60
    g.acervo_index = types.SimpleNamespace(add=lambda *a, **k: None, has=lambda *a: False)
    g.catalogo = types.SimpleNamespace(musicbrainz=lambda *a, **k: None, musicbrainz_edicoes=lambda *a, **k: [],
                                       ultimo_motivo_mb='álbum não encontrado', deezer=lambda *a: None,
                                       ultimo_motivo_deezer='álbum não encontrado', itunes=lambda *a: None,
                                       ultimo_motivo_itunes='álbum não encontrado')
    g.downloader = Baixador(coments); g.pre_download = None; g._notas_corte = {}
    return g, logs


def dados_cb(com_duracoes=False):
    return {'title': 'Os Cobras', 'artists': ['Os Cobras'], 'year': '1960', 'cover_image': None,
            'tracks': [{'number': i + 1, 'title': n, 'duration': mss(d + (2 if i not in EMEND else 0))
                        if com_duracoes else '0:00'} for i, (n, d) in enumerate(zip(NOMES6, DCB))],
            'discogs_master_id': None, 'discogs_release_id': 8325155, 'titulo_buscado': 'Os Cobras'}


disco_atual = [disco]
saida = pasta = tmp('reais', 'cobras', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = app_disco(saida, comentarios)
dd = dados_cb()
ok = g._download_and_process('https://youtu.be/cobras', {'duration': dur_disco, 'title': 'Os Cobras - 1960'},
                             'Os Cobras', 'Os Cobras', '1960', 'discogs', dd['tracks'], True, dd,
                             discogs_candidates=None, from_pending=True, allow_cross_validation=False)
arqs = sorted(glob.glob(os.path.join(saida, '*', '*.mp3')))
t(f'Os Cobras sem durações: o comentário com os tempos dá os 6 nomes ({len(arqs)} arquivos)',
  ok and [os.path.basename(p) for p in arqs] == [f'{i + 1:02d} - {main.sanitize(n)}.mp3' for i, n in enumerate(NOMES6)])
durs = [main.duracao_do_arquivo(p) for p in arqs]
reais_d = [b - a for a, b in zip(inicios_reais, inicios_reais[1:] + [dur_disco])]
# com pausa, o corte vai pro silêncio (erro do comentário some); na emenda sem pausa, fica perto do
# tempo informado (o ruído sintético não tem o "respiro" que uma emenda de verdade tem)
erros = [abs(a - b) for a, b in zip(durs, reais_d)]
t(f'...cada música no lugar, mesmo com o tempo do comentário errado em até 2s '
  f'(1ª e 2ª, com pausa: {erros[0] if erros else 99:.1f}s e {erros[1] if len(erros) > 1 else 99:.1f}s; pior {max(erros or [99]):.1f}s)',
  len(durs) == 6 and max(erros[:2]) <= 1.0 and max(erros) <= 5)
notas = [bool(str(ID3(p).get('TXXX:DISCOFACIL_NOTA') or '')) for p in arqs]
t('...só as faixas das emendas sem pausa ficam "conferir" (3, 4, 5, 6)', notas == [False, False, True, True, True, True])
t('...o comentário errado (outra lista) e o sem tempos não atrapalham; log e arquivo da rodada dizem de onde veio',
  any('Um comentário tem os tempos das 6 faixas (6/6' in l for l in logs)
  and any(l.startswith('REG FONTE') and 'comentário' in l for l in logs))

saida = tmp('reais', 'cobras2', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = app_disco(saida, ['Bom demais', comentarios[2]])
dd = dados_cb()
ok = g._download_and_process('https://youtu.be/cobras', {'duration': dur_disco}, 'Os Cobras', 'Os Cobras', '1960',
                             'discogs', dd['tracks'], True, dd, from_pending=True, allow_cross_validation=False)
t('...sem comentário com os tempos DESTE disco: não usa a lista de outro (fica como antes)',
  not ok and any('nenhum com os tempos das 6 faixas' in l for l in logs))

# disco COM durações e sem pausa nenhuma: o corte falha e os comentários salvam (sem "processar mesmo assim")
EMEND = (0, 1, 2, 3, 4)
partes = [plana(d) for d in DCB]
disco_atual[0] = salvar(np.concatenate(partes), 'reais_cobras_sem_pausa.wav')
inicios_sp = list(np.cumsum([0] + DCB[:-1]))
coment_sp = '\n'.join(f"{mss(ini + dv)} {n}" for n, ini, dv in zip(NOMES6, inicios_sp, desvio))
saida = tmp('reais', 'cobras3', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = app_disco(saida, [coment_sp])
dd = dados_cb(com_duracoes=True)
ok = g._download_and_process('https://youtu.be/sp', {'duration': sum(DCB)}, 'Os Cobras', 'Os Cobras', '1960',
                             'discogs', dd['tracks'], True, dd, from_pending=False, allow_cross_validation=False)
arqs = sorted(glob.glob(os.path.join(saida, '*', '*.mp3')))
t(f'disco com durações mas sem pausa: o corte falha, o comentário corta com os nomes ({len(arqs)} arquivos)',
  ok and len(arqs) == 6 and g.downloader.pedidos == 1)
saida = tmp('reais', 'cobras4', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
disco_atual[0] = disco
g, logs = app_disco(saida, [comentario])
dd = dados_cb(com_duracoes=True)
EMEND = (2, 4)
ok = g._download_and_process('https://youtu.be/ok', {'duration': dur_disco}, 'Os Cobras', 'Os Cobras', '1960',
                             'discogs', dd['tracks'], True, dd, from_pending=True, allow_cross_validation=True)
t('...disco que já corta pelo caminho normal nem consulta os comentários (mais rápido, nada muda)',
  ok and g.downloader.pedidos == 0)

# revisão: comentário que PULA uma música e tem uma linha de total -> não serve (nomes deslocados)
from catalogo import inicios_de_texto
pulado = [x for i, x in enumerate(zip(NOMES6, inicios_reais)) if i != 2]
coment_pulado = '\n'.join(f"{mss(ini)} {n}" for n, ini in pulado) + f"\n{mss(dur_disco - 5)} Total"
t('linha "Total" não vira faixa', len(inicios_de_texto(coment_pulado, dur_disco)) == 5)
coment_pulado2 = coment_pulado.replace('Total', 'Bateria Maluco')
g, logs = app_disco(tmp('reais', 'x', 'y'), [coment_pulado2])
t('comentário que pula uma música (6 linhas, uma de outro disco no fim): não serve',
  g._tempos_dos_comentarios('u', dados_cb(), dur_disco) is None)
t('introdução antes da 1ª música ("0:45 ..."): continua sendo início, não duração',
  [x['start_time'] for x in inicios_de_texto('0:45 A\n3:40 B\n7:10 C\n11:00 D', 1200)] == [0, 220, 430, 660])
t('"0:00 - 3:12 Nome": vale o primeiro tempo e o nome sai limpo',
  inicios_de_texto('0:00 - 3:12 Song\n3:12 - 6:00 Other', 400) == [{'title': 'Song', 'start_time': 0.0},
                                                                    {'title': 'Other', 'start_time': 192.0}])

# revisão: tempos de comentário de OUTRO upload (deslocados 30s): o áudio tem pausas e nenhuma cai perto
from corte_estrategias import SmartCutter
sc = SmartCutter({'tracks': []}, {}, disco, log_func=lambda *a: None)
sc.cluster_gaps = lambda tolerance=5.0: [{'position': p, 'votes': 3} for p in (172, 353, 671)]
sc._find_rms_minimum = lambda pos, janela: None
desloc = [x + 30 for x in inicios_reais]
desloc[0] = 0
t('comentário deslocado 30s (outro upload): recusado em vez de cortar no lugar errado',
  sc.cut_at_positions(desloc, NOMES6, True, conferir_com_pausas=True) is None)
t('...os tempos certos passam', sc.cut_at_positions(inicios_reais, NOMES6, True, conferir_com_pausas=True) is not None)

# revisão: capítulos sem duração no Discogs - o nome oficial só vai se o capítulo tem o mesmo nome
g, logs = app_disco(tmp('reais', 'x', 'y'), [])
caps = [{'title': n, 'start_time': ini, 'end_time': ini + 100, 'duration_seconds': 100}
        for n, ini in zip(['Intro', 'Cheiro de Saudade', 'Love Me or Leave Me', 'Do Jeito Que a Gente Quer',
                           'Doce Melancolia', 'Misty'], inicios_reais)]
juntos = g._merge_chapters_with_discogs(caps, dados_cb())
t('capítulos com uma "Intro" a mais e sem durações no Discogs: nenhum nome deslocado',
  [j['title'] for j in juntos] == ['Intro', 'Cheiro de Saudade', 'Love Me or Leave Me', 'Do Jeito Que a Gente Quer',
                                   'Doce Melancolia', 'Misty'])

# revisão: "processar mesmo assim" com durações - consenso com a contagem certa mas pedaços trocados
sc = SmartCutter({'tracks': [{'title': f'F{i}', 'duration': d} for i, d in enumerate([200, 200, 200, 200])]},
                 {}, disco, log_func=lambda *a: None)
for m in ('cut_hybrid_with_validation', 'cut_directly_on_gaps', 'cut_with_durations', 'cut_by_interval_alignment'):
    setattr(sc, m, lambda *a, **k: None)
sc._get_total_audio_duration = lambda: 800
sc.cut_by_cross_validation = lambda: [{'track': 1, 'title': 'F0', 'start': 0, 'end': 200},
                                      {'track': 2, 'title': 'F1', 'start': 200, 'end': 600},     # F1+F2 grudadas
                                      {'track': 3, 'title': 'F2', 'start': 600, 'end': 780},     # na verdade F3
                                      {'track': 4, 'title': 'F3', 'start': 780, 'end': None}]    # aplausos
t('nomes do cadastro pela posição só se cada pedaço tem a duração da sua faixa (senão fica pendente)',
  sc.decide_and_cut(allow_cross_validation=True) is None)

# revisão: estimativa num trecho que não comporta as faixas (música a mais no vídeo)
sc = SmartCutter({'tracks': []}, {}, disco, log_func=lambda *a: None)
sc._find_rms_minimum = lambda pos, janela: None
b = [{'pos': 100.0}, {'pos': None}, {'pos': 700.0}, {'pos': 800.0}]
t('estimativa recusada quando o trecho entre cortes confirmados (600s) não comporta as faixas (450s)',
  not sc._estimar_fronteiras(b, [{'duration': 100}, {'duration': 200}, {'duration': 250}, {'duration': 100},
                                 {'duration': 100}], [1]))

# ------------------------------------------------------------------ 12.16 (completada em 04/10)
import requests
from pontuacao import e_varios_artistas, avaliar_identificacao


class SessaoQueCai:
    """O Discogs fecha a conexão sem responder (log de 04/10, "Vê")."""
    def __init__(self, cair_na='busca'):
        self.cair_na, self.urls = cair_na, []

    def get(self, url, params=None, timeout=None, headers=None):
        self.urls.append((url, dict(params or {})))
        if self.cair_na == 'busca' or '/releases/' in url:
            raise requests.exceptions.ConnectionError("Remote end closed connection without response")
        return Resp({'results': [{'id': 1, 'title': 'Milton Banana - Vê'}, {'id': 2, 'title': 'Milton Banana - Vê'}]})


CAT.AjustesCatalogo.DISCOGS_INTERVALO_MIN_SEG = 0
for onde in ('busca', 'edicoes'):
    cat = CAT.Catalogo({'discogs_token': 'x'}); cat.session = SessaoQueCai(onde)
    r = cat.discogs('Milton Banana', 'Vê', log_func=lambda *a: None, return_all_candidates=True)
    t(f'Discogs: conexão caiu na {onde} → "não respondeu" (volta pra fila), não "álbum não encontrado"',
      r == [] and cat.last_error == 'rate_limited' and cat.ultimo_erro_discogs == 'conexão')


class Pendencias:
    def __init__(self):
        self.itens = []

    def add(self, **k):
        self.itens.append(k)


G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: None
g._ensure_acervo_and_queue = lambda: None
g.config = types.SimpleNamespace(get_output_directory=lambda: tmp('reais', 'pv'), get=lambda *a, **k: None)
g.downloader = types.SimpleNamespace(get_video_info=lambda u: {'title': 'Milton Banana - Vê - 1965 - Full Album',
                                                              'description': '', 'duration': 1700, 'chapters': []})
g.catalogo = CAT.Catalogo({'discogs_token': 'x'}); g.catalogo.session = SessaoQueCai('busca')
g.pending_queue = Pendencias(); g.groq = None; g.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 60
g.process_single_video('https://youtu.be/E2CtsfdB2A4')
p_ = g.pending_queue.itens[-1] if g.pending_queue.itens else {}
t('...e o vídeo vai pra "Precisam de você" como "Discogs não respondeu", com o motivo certo',
  p_.get('kind') == 'erro_discogs' and 'conexão caiu' in p_.get('reason', '')
  and any('a conexão caiu' in l for l in logs))

t('"VA", "V.A.", "V/A", "Vários Artistas", "Various Artists", "Varius" = vários artistas',
  all(e_varios_artistas(x) for x in ('VA', 'V.A.', 'V/A', 'Vários Artistas', 'Various Artists', 'Varius', 'Various'))
  and not any(e_varios_artistas(x) for x in ('Vanusa', 'Ray Charles', 'Vava')))
cat = CAT.Catalogo({'discogs_token': 'x'}); cat.session = SessaoQueCai('busca')
cat.discogs('V.A.', "Can't Play A Playgirl", log_func=lambda *a: None)
t('...e o Discogs é consultado com o artista "Various"',
  any(p.get('artist') == 'various' for u, p in cat.session.urls))

# Milton Banana "1967" (log de 04/10): LP de 1973 com 0 dos 12 títulos do vídeo, duração batendo, 100%
T73 = ['Do Lado Direito Da Rua Direita', 'Alô! Alô! Taí Carmen Miranda', 'Se O Caso É Chorar', 'Amor Amor',
       'Pasárgada, O Amigo Do Rei', 'Viagem', 'Fim De Caso', 'Pois É', 'Vai Levando', 'Folhas Secas',
       'Batida Diferente', 'Cotidiano']
video67 = ['Samba De Verão', 'Garota De Ipanema', 'Tristeza', 'Arrastão', 'Canto De Ossanha', 'Upa Neguinho',
           'Berimbau', 'Primavera', 'Minha Saudade', 'Nanã', 'Reza', 'Consolação']
lp73 = {'album_title': 'Milton Banana', 'year': 1973, 'is_compilation': False,
        'tracks': [{'title': x, 'duration': 140} for x in T73]}
ident = avaliar_identificacao(lp73, reference_duration=12 * 140 * 1.04, reference_track_titles=video67,
                              year_in_title=1967, search_album_title='Milton Banana', search_artist_name='Milton Banana')
t(f'0 de 12 títulos do vídeo no disco: a nota não passa de 40 ({ident["nota"]}%)',
  ident['nota'] <= 40 and 'não batem' in ident['partes']['titulos_faixas'])
ok_ = dict(lp73, tracks=[{'title': x, 'duration': 140} for x in video67])
t('...com os títulos batendo, continua alta', avaliar_identificacao(
  ok_, reference_duration=12 * 140, reference_track_titles=video67, search_album_title='Milton Banana',
  search_artist_name='Milton Banana')['nota'] >= 90)

# capa que não entra num arquivo (aberto noutro programa): o log e o arquivo da rodada avisam
import saida as SAIDA
pasta_c = tmp('reais', 'capa', 'x')[:-2]; shutil.rmtree(pasta_c, ignore_errors=True); os.makedirs(pasta_c)
open(os.path.join(pasta_c, '01 - Boa.mp3'), 'wb').write(open(glob.glob(os.path.join(TMP, 'reais', '*', '*', '01 - *.mp3'))[0], 'rb').read()
                                                         if glob.glob(os.path.join(TMP, 'reais', '*', '*', '01 - *.mp3')) else b'')
open(os.path.join(pasta_c, '02 - Quebrada.mp3'), 'wb').write(b'isto nao e um mp3')
from PIL import Image as _Im
_Im.new('RGB', (40, 40), 'red').save(os.path.join(pasta_c, 'cover.jpg'))
falhas = SAIDA.embutir_capa(pasta_c, Path(os.path.join(pasta_c, 'cover.jpg')))
t('capa: o arquivo em que não deu aparece na lista de falhas', '02 - Quebrada.mp3' in falhas)

# ------------------------------------------------------------------ tempos informados pelo usuário
disco_atual[0] = disco
saida = tmp('reais', 'usuario', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = app_disco(saida, [])
dd = dados_cb()
duracoes_txt = '\n'.join(f"{n} {mss(d)}" for n, d in zip(NOMES6, reais_d))     # o usuário colou as DURAÇÕES
ok = g._download_and_process('https://youtu.be/cobras', {'duration': dur_disco}, 'Os Cobras', 'Os Cobras', '1960',
                             'discogs', dd['tracks'], True, dd, from_pending=True, tempos_usuario=duracoes_txt)
arqs = sorted(glob.glob(os.path.join(saida, '*', '*.mp3')))
durs = [main.duracao_do_arquivo(p) for p in arqs]
t(f'tempos informados por você (durações coladas): 6 músicas com os nomes, no lugar ({len(arqs)} arquivos)',
  ok and len(durs) == 6 and max(abs(a - b) for a, b in zip(durs, reais_d)) <= 4 and g.downloader.pedidos == 0)
t('...sem marca "conferir" (os tempos são seus) e o arquivo da rodada registra a fonte',
  not any(str(ID3(p).get('TXXX:DISCOFACIL_NOTA') or '') for p in arqs)
  and any(l.startswith('REG FONTE') and 'tempos informados pelo usuário' in l for l in logs))
saida = tmp('reais', 'usuario2', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = app_disco(saida, [])
dd = dados_cb()
inicios_txt = '\n'.join(f"{mss(ini)} {n}" for n, ini in zip(['A', 'B', 'C', 'D'], inicios_reais[:4]))
g._download_and_process('https://youtu.be/cobras', {'duration': dur_disco}, 'Os Cobras', 'Os Cobras', '1960',
                        'discogs', dd['tracks'], True, dd, from_pending=True, tempos_usuario=inicios_txt)
arqs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(saida, '*', '*.mp3')))
saida = tmp('reais', 'usuario3', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = app_disco(saida, [])
dd = dados_cb()
trocado = [1, 0, 2, 3, 4, 5]          # o vídeo tem as duas primeiras invertidas e a lista diz isso
ordem_txt = '\n'.join(f"{mss(ini)} {NOMES6[k].upper()}" for k, ini in zip(trocado, inicios_reais))
lista_u = g._faixas_dos_tempos(ordem_txt, dd, dur_disco)
t('...o nome escrito decide qual faixa é (lista na ordem do vídeo), com a grafia do Discogs',
  [x['title'] for x in lista_u] == [NOMES6[k] for k in trocado])
t('...4 tempos e 6 faixas no Discogs: usa os nomes escritos na lista', arqs == ['01 - A.mp3', '02 - B.mp3',
                                                                                '03 - C.mp3', '04 - D.mp3'])

# ------------------------------------------------------------------ botão "Informar tempos"
import janela
root, app, mainj = janela.abrir()
iniciou = []
app._iniciar_trabalhador = lambda: iniciou.append(1)
pq = app.pending_queue
pq.add(kind='falha_corte', url='https://youtu.be/sem_pausa', video_title='Moacir Santos - Opus 3 - 1979',
       title_artist='Moacir Santos', title_album='Opus 3', confidence_pct=90, reason='Corte não bateu',
       discogs_data={'tracks': [], 'title': 'Opus 3 No. 1'})


def esperar(seg=0.4):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


app.open_pending_queue_manually(); esperar(0.8)
J = app._janela_pendentes
t('botão "Informar tempos" desligado sem seleção', str(J.b_tempos.cget('state')) == 'disabled')
J.tree.selection_set(pq.items[0]['id']); esperar()
t('...ligado com 1 selecionado', str(J.b_tempos.cget('state')) == 'normal')
cx = J.informar_tempos(); esperar()
t('caixa abre com o campo de texto', cx is not None and cx.winfo_exists() and cx.title() == 'Informar tempos')
cx._texto.insert('1.0', 'só texto, sem tempo nenhum')
cx._ok(); esperar()
t('texto sem tempos não é aceito (e nada vai pra fila)', 'tempos_usuario' not in pq.items[0] and not iniciou)
J.tree.selection_set(pq.items[0]['id']); esperar()
cx = J.informar_tempos(); esperar()
cx._texto.insert('1.0', '0:00 Luanne\n4:10 Kamba\n8:02 Coisa Nº 5')
cx._ok(); esperar()
it = pq.items[0]
fi = app.fila.por_url('https://youtu.be/sem_pausa')
t('tempos guardados no item e o item vai pra fila', it.get('tempos_usuario', '').startswith('0:00 Luanne')
  and fi and fi['tipo'] == 'pendencia' and fi['pendencia_item'].get('tempos_usuario') and iniciou)
J.win.geometry('400x420'); esperar(0.6)      # menor que o mínimo: a janela não deixa
dentro = [b.winfo_rootx() + b.winfo_width() <= J.win.winfo_rootx() + J.win.winfo_width() and b.winfo_ismapped()
          for b in (J.b_corrigir, J.b_tempos, J.b_buscar, J.b_remover, J.b_enfileirar, J.b_fechar)]
t('na largura mínima da janela, todos os botões aparecem (Enfileirar inclusive)', all(dentro))
root.destroy()
fim()

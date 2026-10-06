"""
12.14 - Neco "Coquetel Bossa Nova" (disco sem nenhuma duração: o Deezer as dá)
e "Tocando Victor Assis Brasil" (músicas emendadas: quando o usuário manda
processar, a fronteira sem silêncio vai pela duração, marcada "conferir";
no consenso, com o nº de músicas conhecido, nenhum pedaço < 60s).
Nada aqui usa a rede.
"""
import os, sys, shutil, glob, types
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
import numpy as np
from sint import *
import main
import catalogo as CAT
from mutagen.id3 import ID3

CAT.AjustesCatalogo.DEEZER_INTERVALO_SEG = 0.0


def config_falsa(saida):
    return types.SimpleNamespace(get_output_directory=lambda: saida, get=lambda *a, **k: None)


def app_sem_janela(saida, catalogo):
    G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
    g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
    g.config = config_falsa(saida); g.metadata_manager = main.MetadataManager()
    g.acervo_index = types.SimpleNamespace(add=lambda *a, **k: None, has=lambda *a: False)
    g.catalogo = catalogo
    g._notas_corte = {}
    return g, logs


def pasta_limpa(nome):
    p = tmp('emendas', nome, 'x')[:-2]; shutil.rmtree(p, ignore_errors=True); os.makedirs(p); return p


# ------------------------------------------------------------------ Deezer (cliente, sem rede)
class Resp:
    def __init__(self, dados, status=200):
        self.dados, self.status_code = dados, status

    def json(self):
        return self.dados


class SessaoFalsa:
    """Responde como a API do Deezer; guarda os pedidos."""
    def __init__(self, albuns, faixas, erro=None):
        self.albuns, self.faixas, self.erro, self.pedidos = albuns, faixas, erro, []

    def get(self, url, params=None, timeout=None, headers=None):
        self.pedidos.append((url, dict(params or {})))
        assert url.startswith('https://api.deezer.com/'), url
        if self.erro:
            return Resp({'error': {'type': 'Exception', 'message': self.erro, 'code': 4}})
        if url.endswith('search/album'):
            return Resp({'data': self.albuns, 'total': len(self.albuns)})
        aid = int(url.split('/album/')[1].split('/')[0])
        return Resp({'data': self.faixas.get(aid, []), 'total': len(self.faixas.get(aid, []))})


NECO = ['Jogado Fora', 'Você', 'Está Nascendo Um Samba', 'Se Chegou Assim', 'Ah! Se Eu Pudesse', 'Deixa']
DNECO = [156, 177, 150, 121, 140, 137]
albuns = [{'id': 1, 'title': 'Coquetel Dançante', 'nb_tracks': 6, 'artist': {'name': 'Neco'}},
          {'id': 2, 'title': 'Coquetel Bossa Nova', 'nb_tracks': 12, 'artist': {'name': 'Neco'}},
          {'id': 3, 'title': 'Coquetel Bossa Nova (Remastered)', 'nb_tracks': 6, 'artist': {'name': 'Néco'}}]
# no Deezer: sem acento num, "(Remastered)" noutro e 2 faixas trocadas de lugar
dz3 = [{'title': 'Jogado Fora (Remastered)', 'duration': 156}, {'title': 'Voce', 'duration': 177},
       {'title': 'Se Chegou Assim', 'duration': 121}, {'title': 'Está Nascendo Um Samba', 'duration': 150},
       {'title': 'Ah! Se Eu Pudesse', 'duration': 140}, {'title': 'Deixa', 'duration': 137}]
cat = CAT.Catalogo({})
cat.session = SessaoFalsa(albuns, {3: dz3})
r = cat.deezer('Neco', 'Coquetel Bossa Nova', NECO)
t('Deezer: acha a edição com o mesmo nº de faixas e título do álbum (não "Coquetel Dançante")',
  r and r['album_id'] == 3 and r['source'] == 'Deezer')
t('...durações na ordem do Discogs, casadas pelo título (acento, "Remastered", ordem trocada)',
  r and [x['duration'] for x in r['tracks']] == DNECO and [x['title'] for x in r['tracks']] == NECO)
t('...só a API do Deezer, sem chave nenhuma nos pedidos',
  all(u.startswith('https://api.deezer.com/') and not any('token' in k or 'key' in k for k in p)
      for u, p in cat.session.pedidos))
outro = [dict(x) for x in dz3]; outro[5] = {'title': 'Garota de Ipanema', 'duration': 137}
cat.session = SessaoFalsa(albuns, {3: outro})
t('um título sem par no Deezer: não usa (duração no nome errado é pior)',
  cat.deezer('Neco', 'Coquetel Bossa Nova', NECO) is None and 'não batem' in cat.ultimo_motivo_deezer)
cat.session = SessaoFalsa([{'id': 9, 'title': 'Coquetel Bossa Nova', 'nb_tracks': 6, 'artist': {'name': 'Outro Cara'}}], {})
t('mesmo título de outro artista: não serve', cat.deezer('Neco', 'Coquetel Bossa Nova', NECO) is None
  and cat.ultimo_motivo_deezer == 'álbum não encontrado')
cat.session = SessaoFalsa(albuns, {}, erro='Quota limit exceeded')
t('Deezer recusou (limite): None, com o motivo pro log',
  cat.deezer('Neco', 'Coquetel Bossa Nova', NECO) is None and 'recusou' in cat.ultimo_motivo_deezer)

# 12.15: edição com faixas bônus a mais serve (Os Cobras: nenhuma com as 11 exatas)
COBRAS = ['Cheiro De Saudade', 'Love Me Or Leave Me', 'Do Jeito Que A Gente Quer', 'Doce Melancolia', 'Misty']
cd_bonus = [{'title': 'Cheiro de Saudade', 'duration': 170}, {'title': 'Love Me or Leave Me', 'duration': 179},
            {'title': 'Do Jeito Que a Gente Quer', 'duration': 146}, {'title': 'Doce Melancolia', 'duration': 170},
            {'title': 'Misty', 'duration': 140}, {'title': 'Faixa Bônus (Ao Vivo)', 'duration': 200}]
cat.session = SessaoFalsa([{'id': 7, 'title': 'Os Cobras (Remasterizado)', 'nb_tracks': 6, 'artist': {'name': 'Os Cobras'}},
                           {'id': 8, 'title': 'Os Cobras', 'nb_tracks': 3, 'artist': {'name': 'Os Cobras'}}],
                          {7: cd_bonus})
r = cat.deezer('Os Cobras', 'Os Cobras', COBRAS)
t('Deezer: edição com faixa bônus a mais serve, casada pelo título (a de 3 faixas não)',
  r and r['album_id'] == 7 and r['faixas_a_mais'] == 1 and [x['duration'] for x in r['tracks']] == [170, 179, 146, 170, 140])
cat.session = SessaoFalsa([{'id': 8, 'title': 'Os Cobras', 'nb_tracks': 3, 'artist': {'name': 'Os Cobras'}}], {})
t('...só edição com MENOS faixas: não serve, e o motivo diz quantas tinham',
  cat.deezer('Os Cobras', 'Os Cobras', COBRAS) is None and 'com 3 faixas' in cat.ultimo_motivo_deezer)


class SessaoItunes:
    """Responde como a API de busca do iTunes; guarda os pedidos."""
    def __init__(self, por_pais, faixas):
        self.por_pais, self.faixas, self.pedidos = por_pais, faixas, []

    def get(self, url, params=None, timeout=None, headers=None):
        self.pedidos.append((url, dict(params or {})))
        assert url.startswith('https://itunes.apple.com/'), url
        if url.endswith('/search'):
            return Resp({'resultCount': 1, 'results': self.por_pais.get(params.get('country'), [])})
        cid = params['id']
        return Resp({'results': [{'wrapperType': 'collection', 'collectionId': cid}] + self.faixas.get(cid, [])})


CAT.AjustesCatalogo.ITUNES_INTERVALO_SEG = 0.0
musicas_it = [{'wrapperType': 'track', 'trackName': n, 'trackTimeMillis': d * 1000 + 400, 'trackNumber': i + 1,
               'discNumber': 1} for i, (n, d) in enumerate(zip(COBRAS, [170, 179, 146, 170, 140]))]
musicas_it.reverse()        # a loja pode mandar fora de ordem: vale o nº da faixa
cat.session = SessaoItunes({'US': [{'collectionId': 55, 'collectionName': 'Os Cobras', 'artistName': 'Os Cobras',
                                    'trackCount': 5}]}, {55: musicas_it})
r = cat.itunes('Os Cobras', 'Os Cobras', COBRAS)
t('iTunes: acha (loja do Brasil vazia, depois a dos EUA), durações exatas em ms',
  r and r['source'] == 'iTunes' and [x['duration_exact'] for x in r['tracks']] == [170.4, 179.4, 146.4, 170.4, 140.4]
  and [p.get('country') for u, p in cat.session.pedidos if u.endswith('/search')] == ['BR', 'US'])
t('...sem chave nenhuma nos pedidos', all(not any('key' in k or 'token' in k for k in p) for _, p in cat.session.pedidos))

# ------------------------------------------------------------------ Neco: disco sem durações + Deezer
partes = []
for i, d in enumerate(DNECO):
    partes += [musica(d - 1), fade(musica(1))]
    if i < len(DNECO) - 1:
        partes.append(silencio(2.0))
neco = salvar(np.concatenate(partes), 'emendas_neco.wav')
real = main.duracao_do_arquivo(neco)


def dados_neco():
    return {'title': 'Coquetel Bossa Nova', 'artists': ['Neco'], 'year': '1963', 'cover_image': None,
            'tracks': [{'number': i + 1, 'title': n, 'duration': '0:00'} for i, n in enumerate(NECO)],
            'discogs_master_id': 4126353, 'discogs_release_id': 9433703}


durs_dz = [d + 2 for d in DNECO[:-1]] + [DNECO[-1]]        # o Deezer conta a pausa junto
cat_neco = types.SimpleNamespace(
    musicbrainz_edicoes=lambda *a, **k: [], musicbrainz=lambda *a, **k: None, ultimo_motivo_mb='álbum não encontrado',
    deezer=lambda a, b, titulos: {'tracks': [{'title': x, 'duration': d, 'duration_exact': float(d)}
                                             for x, d in zip(titulos, durs_dz)], 'source': 'Deezer', 'album_id': 3},
    ultimo_motivo_deezer=None)
saida = pasta_limpa('neco')
g, logs = app_sem_janela(saida, cat_neco)
dd = dados_neco()
usou = g._duracoes_de_fora(dd, 'Neco', 'Coquetel Bossa Nova', neco)
t('Neco: sem durações no Discogs → as do Deezer entram nas faixas (nomes continuam os do Discogs)',
  usou and [round(main.segundos_da_faixa(x)) for x in dd['tracks']] == durs_dz
  and [x['title'] for x in dd['tracks']] == NECO and dd.get('fonte_duracoes') == 'Deezer')
t('...log e arquivo da rodada dizem de onde vieram',
  any('Deezer: durações das 6 faixas' in l for l in logs) and any(l.startswith('REG FONTE') and 'Deezer' in l for l in logs))
ok = g._process_separation_by_source(neco, 'discogs', dd['tracks'], True, dd, {'duration': real}, saida,
                                     allow_cross_validation=False)
arqs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(saida, '*.mp3')))
t(f'...e o disco sai sozinho com os 6 nomes ({len(arqs)} arquivos)',
  ok and arqs == [f'{i + 1:02d} - {main.sanitize(n)}.mp3' for i, n in enumerate(NECO)])
t('...o encaixe mostra que as durações são do Deezer', any('durações do Deezer' in l for l in logs))

g, logs = app_sem_janela(pasta_limpa('neco2'), dict(cat_neco.__dict__) and types.SimpleNamespace(
    **dict(cat_neco.__dict__, deezer=lambda a, b, titulos: {'tracks': [
        {'title': x, 'duration': d + 40, 'duration_exact': float(d + 40)} for x, d in zip(titulos, DNECO)]})))
dd = dados_neco()
t('soma do Deezer longe do áudio (outra gravação): não usa',
  not g._duracoes_de_fora(dd, 'Neco', 'Coquetel Bossa Nova', neco)
  and all(main.segundos_da_faixa(x) == 0 for x in dd['tracks']) and any('não bate com o áudio' in l for l in logs))
g, logs = app_sem_janela(pasta_limpa('neco4'), types.SimpleNamespace(
    **dict(cat_neco.__dict__, deezer=lambda *a: None, ultimo_motivo_deezer='nenhuma edição com as 6 faixas',
           itunes=lambda a, b, titulos: {'tracks': [{'title': x, 'duration': d, 'duration_exact': float(d)}
                                                    for x, d in zip(titulos, durs_dz)], 'source': 'iTunes',
                                         'album_id': 99, 'faixas_a_mais': 2},
           ultimo_motivo_itunes=None)))
dd = dados_neco()
t('Deezer sem a edição: vai pro iTunes, e o log diz de onde vieram (e as faixas a mais)',
  g._duracoes_de_fora(dd, 'Neco', 'Coquetel Bossa Nova', neco) and dd.get('fonte_duracoes') == 'iTunes'
  and any('Deezer: nenhuma edição' in l for l in logs) and any('iTunes: durações das 6 faixas' in l
                                                                 and '2 faixa(s) a mais' in l for l in logs))
g, logs = app_sem_janela(pasta_limpa('neco3'), types.SimpleNamespace(
    **dict(cat_neco.__dict__, deezer=lambda *a: None, ultimo_motivo_deezer='álbum não encontrado')))
dd = dados_neco()
t('Deezer sem o álbum: segue como antes, com o motivo no log',
  not g._duracoes_de_fora(dd, 'Neco', 'Coquetel Bossa Nova', neco)
  and any('Deezer: álbum não encontrado - sem durações daqui' in l for l in logs))

# ------------------------------------------------------------------ Tocando Victor Assis Brasil: emendadas
TVA = ['Waltz for Phil', 'Arroio', 'Waltzing', 'Onix', 'Balada for Nadia', 'Blues for Mr Saltzman', 'Fim']
DTVA = [300, 330, 280, 360, 290, 310, 250]
partes, emenda = [], 0.0
for i, d in enumerate(DTVA):
    if i == 4:          # "Balada for Nadia": duas pausas no começo, a 30s uma da outra
        partes += [musica(30), silencio(2.5), musica(28), silencio(2.5), musica(d - 63 - 1), fade(musica(1))]
    elif i == 0:        # Waltz for Phil emenda direto em Arroio: sem pausa nenhuma
        partes += [musica(d)]
    else:
        partes += [musica(d - 1), fade(musica(1))]
    if i not in (0, len(DTVA) - 1):
        partes.append(silencio(2.0))
tva = salvar(np.concatenate(partes), 'emendas_tocando.wav')
real = main.duracao_do_arquivo(tva)
# o catálogo conta a pausa dentro da faixa, com uns segundos de erro aqui e ali
cad = [d + (2 if 0 < i < len(DTVA) - 1 else 0) for i, d in enumerate(DTVA)]
cad = [c + e for c, e in zip(cad, [0, 2, -2, 1, 0, -1, 0])]


def dados_tva():
    return {'title': 'Tocando Victor Assis Brasil', 'artists': ['Luiz Avellar'], 'year': '2000', 'cover_image': None,
            'tracks': [{'number': i + 1, 'title': n, 'duration': f'{c // 60}:{c % 60:02d}'}
                       for i, (n, c) in enumerate(zip(TVA, cad))],
            'discogs_master_id': None, 'discogs_release_id': 24672032}


cat_tva = types.SimpleNamespace(musicbrainz_edicoes=lambda *a, **k: [], musicbrainz=lambda *a, **k: None,
                                ultimo_motivo_mb='álbum não encontrado')
g, logs = app_sem_janela(pasta_limpa('tva_auto'), cat_tva)
dd = dados_tva()
ok = g._process_separation_by_source(tva, 'discogs', dd['tracks'], True, dd, {'duration': real},
                                     pasta_limpa('tva_auto'), allow_cross_validation=False)
t('Tocando, automático: fronteira sem silêncio continua recusada (nada de estimativa sozinho)',
  not ok and not any('ESTIMATIVA PELA DURAÇÃO' in l for l in logs))

saida = pasta_limpa('tva_forcado')
g, logs = app_sem_janela(saida, cat_tva)
dd = dados_tva()
ok = g._process_separation_by_source(tva, 'discogs', dd['tracks'], True, dd, {'duration': real}, saida,
                                     allow_cross_validation=True)
arqs = sorted(glob.glob(os.path.join(saida, '*.mp3')))
nomes = [os.path.basename(p) for p in arqs]
t(f'...você mandou processar: 7 músicas com nome, não "Track N" ({len(arqs)} arquivos)',
  ok and nomes == [f'{i + 1:02d} - {n}.mp3' for i, n in enumerate(TVA)])
durs = [main.duracao_do_arquivo(p) for p in arqs]
t(f'...a emenda 1→2 cai perto do lugar certo ({durs and round(durs[0])}s; a 1ª tem {DTVA[0]}s)',
  len(durs) == 7 and abs(durs[0] - DTVA[0]) <= 10)
t(f'...sem pedaço de 30s na "Balada for Nadia" ({durs and round(min(durs))}s o menor)',
  len(durs) == 7 and min(durs) > 200)
notas = [str(ID3(p).get('TXXX:DISCOFACIL_NOTA') or '') for p in arqs]
t('...as duas faixas da emenda marcadas "conferir" na tag; as outras não',
  len(notas) == 7 and 'conferir' in notas[0] and 'conferir' in notas[1] and not any(notas[2:]))
t('...e no log e no arquivo da rodada',
  any('ESTIMATIVA PELA DURAÇÃO' in l for l in logs)
  and any(l.startswith('REG AVISO') and 'corte estimado' in l and '[1, 2]' in l for l in logs))

# 12.15: Ray Charles "Ingredients" - quase sem pausa: 4 de 9 trocas emendadas, em 2 buracos de 2
RAY = ['Busted', 'Where Can I Go', 'Born To Be Blue', 'That Lucky Old Sun', "Ol' Man River", 'In The Evening',
       'A Stranger In Town', "Ol' Man Time", 'Over The Rainbow', "You'll Never Walk Alone"]
DRAY = [124, 205, 180, 256, 330, 290, 150, 160, 200, 190]
EMENDADAS = (2, 3, 5, 6)        # sem pausa DEPOIS destas (índice da faixa)


def plana(seg):
    """Música sem o vaivém lento de volume do gerador: numa emenda de verdade não há 'buraco' perto."""
    x = np.convolve(rng.standard_normal(int(seg * SR)), np.ones(8) / 8, 'same')
    return 0.3 * x / np.std(x)


def disco_ray(emendadas):
    partes = []
    for i, d in enumerate(DRAY):
        if i in emendadas or (i - 1) in emendadas:
            # emenda: o fim de uma e o começo da outra sem pausa nem queda de volume
            partes.append(plana(d) if i == len(DRAY) - 1 or i in emendadas
                          else np.concatenate([plana(d - 1), fade(musica(1))]))
            if i not in emendadas and i < len(DRAY) - 1:
                partes.append(silencio(2.0))
        elif i == len(DRAY) - 1:
            partes.append(musica(d))
        else:
            partes += [musica(d - 1), fade(musica(1)), silencio(2.0)]
    return np.concatenate(partes)


ray = salvar(disco_ray(EMENDADAS), 'emendas_ray.wav')
real_ray = main.duracao_do_arquivo(ray)
cad_ray = [d + (2 if i not in EMENDADAS and i < len(DRAY) - 1 else 0) for i, d in enumerate(DRAY)]


def dados_ray():
    return {'title': 'Ingredients In A Recipe For Soul', 'artists': ['Ray Charles'], 'year': '1963', 'cover_image': None,
            'tracks': [{'number': i + 1, 'title': n, 'duration': f'{c // 60}:{c % 60:02d}'}
                       for i, (n, c) in enumerate(zip(RAY, cad_ray))],
            'discogs_master_id': 75497, 'discogs_release_id': 963549}


saida = pasta_limpa('ray')
g, logs = app_sem_janela(saida, cat_tva)
dd = dados_ray()
ok = g._process_separation_by_source(ray, 'discogs', dd['tracks'], True, dd, {'duration': real_ray}, saida,
                                     allow_cross_validation=True)
arqs = sorted(glob.glob(os.path.join(saida, '*.mp3')))
t(f'Ray Charles (você mandou processar): as 10 músicas com nome, não 6 "Track N" ({len(arqs)} arquivos)',
  ok and [os.path.basename(p) for p in arqs] == [f'{i + 1:02d} - {main.sanitize(n)}.mp3' for i, n in enumerate(RAY)])
durs = [main.duracao_do_arquivo(p) for p in arqs]
t(f'...cada música no lugar (pior diferença {max(abs(a - b) for a, b in zip(durs, DRAY)) if len(durs) == 10 else "?":.1f}s)'
  if len(durs) == 10 else '...cada música no lugar', len(durs) == 10 and max(abs(a - b) for a, b in zip(durs, DRAY)) <= 10)
notas = [bool(str(ID3(p).get('TXXX:DISCOFACIL_NOTA') or '')) for p in arqs]
t('...as faixas das 4 emendas marcadas "conferir" (3, 4, 5, 6, 7, 8); as outras não',
  notas == [False, False, True, True, True, True, True, True, False, False])
ray3 = salvar(disco_ray((2, 3, 4)), 'emendas_ray3.wav')
cad3 = [d + (2 if i not in (2, 3, 4) and i < len(DRAY) - 1 else 0) for i, d in enumerate(DRAY)]
dd = dados_ray()
for f_, c in zip(dd['tracks'], cad3):
    f_['duration'] = f'{c // 60}:{c % 60:02d}'
saida = pasta_limpa('ray3')
g, logs = app_sem_janela(saida, cat_tva)
ok = g._process_separation_by_source(ray3, 'discogs', dd['tracks'], True, dd, {'duration': real_ray}, saida,
                                     allow_cross_validation=True)
t('...3 trocas seguidas sem pausa: não estima, e também não sai "Track N" cortado no meio (fica pendente)',
  not ok and not glob.glob(os.path.join(saida, '*.mp3'))
  and any('cortar só pelas pausas daria' in l for l in logs))

# limites da estimativa
from corte_estrategias import SmartCutter
sc = SmartCutter({'tracks': []}, {}, tva, log_func=lambda *a: None)
sc._find_rms_minimum = lambda pos, janela: None
faixas = [{'duration': 100}] * 7


def fronteiras(*soltas):
    return [{'pos': None if k in soltas else 100.0 * (k + 1)} for k in range(6)]


b = fronteiras(0)
t('estimativa: 1 de 6 sem silêncio, ancorada nos dois lados → pela proporção',
  sc._estimar_fronteiras(b, faixas, [0]) and abs(b[0]['pos'] - 100.0) < 1e-6 and b[0]['estimado']
  and b[0]['method'].startswith('math_fallback'))
b = fronteiras(1, 2, 3)
t('...3 seguidas sem silêncio: não estima (o erro não fica preso entre cortes)',
  not sc._estimar_fronteiras(b, faixas, [1, 2, 3]) and all(b[k]['pos'] is None for k in (1, 2, 3)))
# 12.15: Ray Charles "Ingredients" - 4 de 9 em 2 buracos de 2
faixas10 = [{'duration': 100}] * 10
b = [{'pos': None if k in (2, 3, 5, 6) else 100.0 * (k + 1)} for k in range(9)]
t('...4 de 9, em 2 buracos de 2 com cortes confirmados dos lados: estima as 4',
  sc._estimar_fronteiras(b, faixas10, [2, 3, 5, 6])
  and [round(b[k]['pos']) for k in (2, 3, 5, 6)] == [300, 400, 600, 700] and all(b[k]['estimado'] for k in (2, 3, 5, 6)))
b = [{'pos': None if k in (0, 2, 4, 6, 8) else 100.0 * (k + 1)} for k in range(9)]
t('...5 de 9 (mais da metade): não estima', not sc._estimar_fronteiras(b, faixas10, [0, 2, 4, 6, 8]))
b = fronteiras(5)
t('...a última sem âncora depois dela (soma não bateu com o fim): não estima',
  not sc._estimar_fronteiras(b, faixas, [5], disc_end_anchor=None) and b[5]['pos'] is None)
t('...com o fim do arquivo como âncora (soma bateu): estima',
  sc._estimar_fronteiras(b, faixas, [5], disc_end_anchor=700.0) and abs(b[5]['pos'] - 600.0) < 1e-6)

# ------------------------------------------------------------------ 60s no consenso
g_ = lambda pos, v, s=2.0, pre=False: {'position': pos, 'votes': v, 'duration': s, 'pre_confirmed': pre}
cortes = [g_(300, 3), g_(900, 7, 1.6, True), g_(930, 4, 3.8), g_(955, 3, 5.1), g_(1300, 3)]
fica = [c['position'] for c in sc._tirar_pedacos_curtos(cortes, 60.0)]
t(f'pedaços < 60s: fica o corte mais forte (confirmado > votos > silêncio) {fica}',
  fica == [300, 900, 1300])
t('...sem pedaço curto, nada muda', [c['position'] for c in sc._tirar_pedacos_curtos(
  [g_(100, 2), g_(200, 2), g_(400, 2)], 60.0)] == [100, 200, 400])

# consenso com e sem o nº de músicas do cadastro (a "Balada for Nadia" com as duas pausas)
def consenso(faixas_cad):
    ac = main.AlbumCutter('Y', 'X', tva, {'tracks': faixas_cad, 'title': 'X'}, pasta_limpa('cv'),
                          log_func=lambda *a: None)
    s = SmartCutter(ac.metadata, ac.detect_gaps(), tva, log_func=lambda *a: None)
    cuts = s.cut_by_cross_validation() or []
    return [c['end'] - c['start'] for c in cuts if c.get('end') is not None]


com = consenso([{'title': n, 'duration': 0} for n in TVA])
sem = consenso([])
t(f'consenso com o nº de músicas: nenhum pedaço < 60s (menor {com and round(min(com))}s)', com and min(com) >= 60)
t(f'...sem cadastro nenhum, nada muda (pausas a 30s ainda viram pedaço: {sem and round(min(sem))}s)',
  sem and min(sem) < 60)
# ------------------------------------------------------------------ "Can't Play A Playgirl": compacto × coletânea
from pontuacao import score_discogs_candidate, avaliar_identificacao
from catalogo import limite_de_faixas
compacto = {'tracks': [{'title': "Can't Play A Playgirl", 'duration': 147}, {'title': 'Why Did I Cry', 'duration': 145}],
            'track_count': 2, 'album_title': "Can't Play A Playgirl", 'year': 1965, 'is_compilation': False}
coletanea = {'tracks': [{'title': f'Faixa {i}', 'duration': 0} for i in range(34)], 'track_count': 34,
             'album_title': "Can't Play A Playgirl (1960's Girl Goodies Lost & Found)", 'year': 2022,
             'is_compilation': True}
VIDEO = 4650            # 77,5 min
t(f'vídeo de 77 min: a coletânea de 34 faixas não é descartada como box set (limite {limite_de_faixas(VIDEO)})',
  limite_de_faixas(VIDEO) >= 34 and limite_de_faixas(1800) == 30 and limite_de_faixas(None) == 30
  and limite_de_faixas(10 ** 5) == 60)
sc_comp = score_discogs_candidate(compacto, VIDEO, search_album_title="Can´t Play A Playgirl", search_artist_name='Varius')
sc_col = score_discogs_candidate(coletanea, VIDEO, search_album_title="Can´t Play A Playgirl", search_artist_name='Varius')
t(f'compacto de 5 min com o mesmo nome perde pra coletânea de 77 min ({sc_comp:.0f} × {sc_col:.0f})', sc_col > sc_comp)
ident = avaliar_identificacao(compacto, VIDEO, search_album_title="Can´t Play A Playgirl", search_artist_name='Varius')
t(f'...e sozinho não passa da confiança mínima ({ident["nota"]}%)',
  ident['nota'] < 60 and 'outro disco' in ident['partes']['duracao_total'])
lp = {'tracks': [{'title': f'F{i}', 'duration': 200} for i in range(10)], 'track_count': 10, 'album_title': 'Disco',
      'year': 1970, 'is_compilation': False}
t('um LP de 33 min num vídeo de 2 LPs (66 min) não leva a penalidade',
  'outro disco' not in avaliar_identificacao(lp, 4000, search_album_title='Disco')['partes']['duracao_total'])
# ------------------------------------------------------------------ textos de ajuda (?)
fonte_jp = open(os.path.join(PROJ, 'janela_principal.py'), encoding='utf-8').read()
fonte_jc = open(os.path.join(PROJ, 'janela_config.py'), encoding='utf-8').read()
t('"?" geral fala em "Precisam de você", não no antigo "Álbuns pendentes (rodapé)"',
  "'Precisam de você'" in fonte_jp and 'botão no rodapé' not in fonte_jp)
t('"?" da chave do YouTube diz que Buscar Playlists precisa dela', "'Buscar Playlists' - sem ela" in fonte_jc)
fim()

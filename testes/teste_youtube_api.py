"""
12.20 - YouTube Data API (busca de playlists e listagem de canal) com requests, sem a biblioteca
do Google: ela não ia no .exe e a busca dizia "chave não configurada" com a chave configurada.
Respostas da API simuladas (nada vai pra internet); a chave nunca aparece em mensagem.
"""
import os, sys, glob, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import requests
import downloader as D

CHAVE = 'CHAVE-SECRETA-DE-TESTE-123'


class Config:
    def __init__(self, chave=CHAVE):
        self.v = {'api_keys.google_custom_search.api_key': chave, 'settings.min_bitrate_kbps': 128,
                  'album_keywords': ['full album']}

    def get(self, k, padrao=None):
        return self.v.get(k, padrao)


class Resp:
    def __init__(self, status, dados):
        self.status_code, self._d = status, dados

    def json(self):
        return self._d


pedidos = []


def api_falsa(respostas):
    def get(url, params=None, timeout=None):
        pedidos.append((url.rsplit('/', 1)[-1], dict(params or {})))
        r = respostas(url.rsplit('/', 1)[-1], params or {})
        if isinstance(r, Exception):
            raise r
        return r
    return get


def respostas_busca(recurso, p):
    if recurso == 'search':
        return Resp(200, {'items': [
            {'id': {'playlistId': 'PL1'}, 'snippet': {'title': 'Tamba Trio - Full Album', 'channelTitle': 'Canal A'}},
            {'id': {'playlistId': 'PL2'}, 'snippet': {'title': 'Tamba Trio - Avanço', 'channelTitle': 'Canal B'}}]})
    if recurso == 'playlists':
        return Resp(200, {'items': [{'id': 'PL1', 'contentDetails': {'itemCount': 12}},
                                    {'id': 'PL2', 'contentDetails': {'itemCount': 10}}]})
    if recurso == 'playlistItems':
        return Resp(200, {'items': [{'contentDetails': {'videoId': 'V' + p['playlistId']}}]})
    return Resp(404, {})


d = D.YouTubeDownloader(Config())
d._probe_best_audio_bitrate = lambda url: 160 if 'PL1' in url else 70     # PL2: fonte abaixo do mínimo
D.requests.get = api_falsa(respostas_busca)
res = d.search_playlists('Tamba Trio full album')
t(f"busca de playlists sem a biblioteca do Google ({[r['playlist_id'] for r in res or []]})",
  res is not None and [r['playlist_id'] for r in res] == ['PL1'] and res[0]['item_count'] == 12
  and res[0]['url'].endswith('list=PL1') and d.ultimo_erro_youtube is None)
t('...a chave vai nos parâmetros de todos os pedidos', pedidos and all(p.get('key') == CHAVE for _, p in pedidos))
t('...nenhum arquivo do programa usa mais a biblioteca do Google (ela não vai no .exe)',
  not any('googleapiclient' in open(f, encoding='utf-8').read() for f in glob.glob(os.path.join(PROJ, '*.py'))))

# motivos de falha, em português e sem a chave
casos = [
    ('sem chave', Config(chave=''), lambda r, p: Resp(200, {}), 'não está configurada'),
    ('chave recusada', Config(), lambda r, p: Resp(400, {'error': {'errors': [{'reason': 'keyInvalid'}]}}), 'recusada'),
    ('cota esgotada', Config(), lambda r, p: Resp(403, {'error': {'errors': [{'reason': 'quotaExceeded'}]}}), 'cota'),
    ('API não ativada', Config(), lambda r, p: Resp(403, {'error': {'errors': [{'reason': 'accessNotConfigured'}]}}),
     'não está ativada'),
    ('sem internet', Config(), lambda r, p: requests.exceptions.ConnectionError(
        f'https://www.googleapis.com/youtube/v3/search?key={CHAVE}'), 'sem conexão'),
]
for nome, cfg, resp, esperado in casos:
    d = D.YouTubeDownloader(cfg)
    D.requests.get = api_falsa(resp)
    r = d.search_playlists('x')
    motivo = d.ultimo_erro_youtube or ''
    t(f"{nome}: \"{motivo[:70]}\"", r is None and esperado in motivo and CHAVE not in motivo and 'CHAVE' not in motivo)

# listagem de canal pela API (paginada)
pedidos.clear()


def respostas_canal(recurso, p):
    if recurso == 'channels':
        return Resp(200, {'items': [{'contentDetails': {'relatedPlaylists': {'uploads': 'UU1'}}}]})
    if recurso == 'playlistItems':
        if p.get('pageToken') == 'P2':
            return Resp(200, {'items': [{'snippet': {'resourceId': {'videoId': 'v3'}}}]})
        return Resp(200, {'items': [{'snippet': {'resourceId': {'videoId': 'v1'}}},
                                    {'snippet': {'resourceId': {'videoId': 'v2'}}}], 'nextPageToken': 'P2'})
    if recurso == 'videos':
        dur = {'v1': 'PT35M10S', 'v2': 'PT3M', 'v3': 'PT4M'}
        tit = {'v1': 'Disco longo', 'v2': 'Clipe', 'v3': 'Elis - Full Album'}
        return Resp(200, {'items': [{'id': v, 'snippet': {'title': tit[v]}, 'contentDetails': {'duration': dur[v]}}
                                    for v in p['id'].split(',')]})
    return Resp(404, {})


d = D.YouTubeDownloader(Config())
d._get_channel_id_from_url = lambda url: 'UCabc'
D.requests.get = api_falsa(respostas_canal)
vids = d._get_channel_videos_via_api('https://www.youtube.com/@canal')
t(f"canal pela API, 2 páginas: álbuns pela duração (>= 25 min) ou pela palavra-chave ({[v['id'] for v in vids or []]})",
  vids is not None and [v['id'] for v in vids] == ['v1', 'v3'] and vids[0]['duration'] == 35 * 60 + 10
  and any(p.get('pageToken') == 'P2' for r, p in pedidos if r == 'playlistItems'))
d = D.YouTubeDownloader(Config())
d._get_channel_id_from_url = lambda url: 'UCabc'
D.requests.get = api_falsa(lambda r, p: Resp(403, {'error': {'errors': [{'reason': 'quotaExceeded'}]}}))
avisos = []
t('canal com a cota esgotada: None (cai pro yt-dlp) e avisa o motivo',
  d._get_channel_videos_via_api('https://www.youtube.com/@canal', avisos.append) is None
  and any('cota' in a for a in avisos) and not any(CHAVE in a for a in avisos))

fim()

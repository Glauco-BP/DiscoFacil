"""
12.8 - caminho simples no lugar do multi-fonte antigo (sem Selenium/Chrome),
pistas do próprio vídeo, capa embutida, pasta de saída, fila e playlist.
Nada aqui usa a rede.
"""
import os, re, sys, types, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
import main, saida, processo_album as PA
from catalogo import pistas_do_video
from falso_discogs import config_falsa

# ------------------------------------------------------------------ sem Selenium nem módulos antigos
t('nenhum módulo do Selenium carregado', not any(m.startswith('selenium') or m.startswith('webdriver') for m in sys.modules))
t('módulos antigos apagados', not any(os.path.exists(os.path.join(PROJ, f)) for f in
      ('metadata_hunter_voting.py', 'api_cache.py', 'description_tracklist_extractor.py')))
fontes = open(os.path.join(PROJ, 'processo_album.py'), encoding='utf-8').read()
t('nenhum "rmtree" de cache com caminho fixo', 'cache_directory' not in fontes
  and not re.search(r'[A-Z]:\\+Users\\+\w', fontes))

# ------------------------------------------------------------------ pistas do vídeo (sem rede)
caps = {'chapters': [{'title': 'A', 'start_time': 0, 'end_time': 200}, {'title': 'B', 'start_time': 200, 'end_time': 380}]}
p = pistas_do_video(caps)
t('capítulos viram faixas com duração', p['source'] == 'YouTube Chapters' and [x['duration'] for x in p['tracks']] == [200, 180])
p = pistas_do_video({'description': '00:00 Um\n03:20 Dois\n07:00 Três\nSiga o canal'})
t('descrição com tempos', p['source'] == 'YouTube Description' and [x['title'] for x in p['tracks']] == ['Um', 'Dois', 'Três'])
t('sem nada: None', pistas_do_video({'description': 'Siga o canal'}) is None and pistas_do_video({}) is None)

# tempos da descrição: inícios (crescentes a partir do zero) ou durações
f = PA.faixas_com_tempo_da_descricao(pistas_do_video({'description': '00:00 Um\n03:20 Dois\n07:00 Três'}), 600)
t(f'inícios -> durações ({f and [x["duration"] for x in f]})', f and [x['duration'] for x in f] == [200, 220, 180])
f = PA.faixas_com_tempo_da_descricao(pistas_do_video({'description': 'Um 3:20\n'}), 600)
t('linha "Nome 3:20" não é lida como tempo de início', f is None)
f = PA.faixas_com_tempo_da_descricao(pistas_do_video({'description': '3:20 Um\n4:10 Dois\n2:05 Três'}), 600)
t(f'durações soltas ficam como estão ({f and [x["duration"] for x in f]})', f and [x['duration'] for x in f] == [200, 250, 125])
f = PA.faixas_com_tempo_da_descricao(pistas_do_video({'description': '00:00 Um\n03:20 Dois'}), None)
t('inícios sem a duração do vídeo: não dá pra saber a última', f is None)

# ------------------------------------------------------------------ dados do álbum
r = {'tracks': [{'title': 'A', 'duration': 200}, {'title': 'B', 'duration': 0}], 'title': 'Disco', 'artists': ['X (2)'],
     'year': 1970, 'genre': 'Jazz; Bossa', 'cover_image': 'u', 'master_id': 5, 'release_id': 9, 'confidence_pct': 90}
d = PA.dados_para_corte(r, 'x', 'y', '')
t('formato do corte: M:SS, IDs com prefixo, gênero junto',
  [x['duration'] for x in d['tracks']] == ['3:20', '0:00'] and d['discogs_master_id'] == 5 and d['genre'] == 'Jazz; Bossa')
G = main.FullTracksDownloaderGUI
cru = G._discogs_data_to_raw_shape(None, d)
t('vai e volta das pendências sem perder nada',
  PA.dados_para_corte(cru, 'x', 'y', '')['tracks'] == d['tracks'] and cru['genre'] == 'Jazz; Bossa' and cru['master_id'] == 5)

# ------------------------------------------------------------------ pendência "não encontrado": a ordem do caminho simples
def app(discogs=None, mb=None):
    g = G.__new__(G); logs = []
    g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
    g.catalogo = types.SimpleNamespace(discogs=lambda *a, **k: list(discogs or []), last_error=None,
                                       musicbrainz=lambda *a, **k: mb, ultimo_motivo_mb='álbum não encontrado')
    return g, logs

cand = dict(r, tracks=[{'title': 'A', 'duration': 200}, {'title': 'B', 'duration': 180}], score=50, confidence_pct=40)
g, logs = app(discogs=[cand])
res = g._resolver_sem_discogs({'title': 'X - Disco', 'duration': 380}, 'X', 'Disco', '')
t('1º: Discogs de novo, com qualquer nota (o usuário decidiu)', res[3] == 'discogs' and res[7] == [cand] and res[0] == 'X (2)')

capitulos = [{'title': f'Faixa {i}', 'start_time': i * 100, 'end_time': (i + 1) * 100} for i in range(5)]
g, logs = app()
res = g._resolver_sem_discogs({'title': 'X - Disco', 'duration': 500, 'chapters': capitulos}, 'X', 'Disco', '1999')
t('2º: capítulos do vídeo (com artista/álbum do título, não "Unknown")',
  res[3] == 'youtube_chapters' and len(res[4]) == 5 and res[6]['artists'] == ['X'] and res[6]['title'] == 'Disco')

g, logs = app()
res = g._resolver_sem_discogs({'title': 'X - Disco', 'duration': 600, 'description': '00:00 Um\n03:20 Dois\n07:00 Três'},
                              'X', 'Disco', '')
t('3º: tracklist com tempos na descrição', res[3] == 'description' and [x['duration'] for x in res[4]] == ['3:20', '3:40', '3:00'])

mb = {'tracks': [{'title': 'Um', 'duration': 200, 'duration_exact': 200.4}, {'title': 'Dois', 'duration': 180,
      'duration_exact': 179.6}], 'source': 'MusicBrainz', 'title': 'Outro Nome'}
g, logs = app(mb=mb)
res = g._resolver_sem_discogs({'title': 'X - Disco', 'duration': 380}, 'X', 'Disco', '')
t('4º: MusicBrainz, com a duração exata', res[3] == 'musicbrainz' and res[4][0]['duration_seconds'] == 200.4
  and res[1] == 'Disco')

g, logs = app()
res = g._resolver_sem_discogs({'title': 'X - Disco', 'duration': 380}, 'X', 'Disco', '')
t('por fim: só os silêncios', res[3] == 'silence_only' and res[4] == [] and res[6]['artists'] == ['X'])
t('...e o motivo do MusicBrainz no log', any('MusicBrainz: álbum não encontrado' in l for l in logs))

# a pendência chama o caminho simples e baixa pelo resultado
g, logs = app()
chamada = {}
g.downloader = types.SimpleNamespace(get_video_info=lambda u: {'title': 'X - Disco', 'duration': 500, 'chapters': capitulos})
g._download_and_process = lambda *a, **k: chamada.update(args=a, **k) or True
ok = g._process_pending_video_item({'url': 'u', 'video_title': 'X - Disco', 'kind': 'nao_encontrado',
                                    'title_artist': 'X', 'title_album': 'Disco', 'year': ''})
t('pendência "não encontrado" usa o caminho simples', ok and chamada['args'][5] == 'youtube_chapters'
  and chamada.get('from_pending') is True)

# ------------------------------------------------------------------ pasta de saída e capa
n = saida.nome_da_pasta('Simone (3)', 'Pedaço: De Mim?', 1980)
t(f'nome da pasta ({n})', n == 'Simone - Pedaço De Mim (1980)')
n = saida.nome_da_pasta('A' * 50, 'B' * 300, 1999)
t(f'nome da pasta cabe no limite ({len(n)})', len(n) <= saida.LIMITE_NOME_PASTA and n.endswith('(1999)'))

pasta = tmp('simples', 'capa', 'x')[:-2]; shutil.rmtree(pasta, ignore_errors=True); os.makedirs(pasta)
mp3 = os.path.join(pasta, '01 - A.mp3'); capa = os.path.join(pasta, 'cover.jpg')
subprocess.run([FFMPEG, '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=d=3', '-c:a', 'libmp3lame', mp3], check=True)
subprocess.run([FFMPEG, '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=64x64', '-frames:v', '1', capa],
               check=True)
saida.embutir_capa(pasta, __import__('pathlib').Path(capa))
from mutagen.id3 import ID3
t('capa embutida no MP3 (a gravação em .tmp precisava do formato explícito)',
  any(k.startswith('APIC') for k in ID3(mp3).keys()) and not os.path.exists(mp3 + '.tmp'))

# tags do corte de álbum: todos os campos, sem o " (N)" do Discogs
shutil.copy(mp3, os.path.join(pasta, '02 - Bê.mp3'))
ac = main.AlbumCutter('Nico (2)', 'Disco', 'nada.wav', {'year': '1981', 'genre': 'Jazz; Fusion',
                      'album_artist': 'Nico (2)'}, pasta, log_func=lambda *a: None)
ac.cuts = [{'track': 2, 'title': 'Bê', 'start': 0, 'end': None}]
tg = ID3(os.path.join(pasta, '02 - Bê.mp3'))
ok_tags = ac.add_tags(); tg = ID3(os.path.join(pasta, '02 - Bê.mp3'))
t(f"tags do álbum ({[str(tg.get(k)) for k in ('TIT2', 'TPE1', 'TPE2', 'TALB', 'TRCK', 'TDRC', 'TCON')]})",
  ok_tags and [str(tg.get(k)) for k in ('TIT2', 'TPE1', 'TPE2', 'TALB', 'TRCK', 'TDRC', 'TCON')]
  == ['Bê', 'Nico', 'Nico', 'Disco', '2/1', '1981', 'Jazz; Fusion'])

# ------------------------------------------------------------------ playlist: identificação e fila
out = tmp('simples', 'SOM', 'x')[:-2]; shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
g, logs = app(discogs=None)
g.config = config_falsa(out); g._ensure_acervo_and_queue = lambda: True
g.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 80
pend = []; g.pending_queue = types.SimpleNamespace(add=lambda **k: pend.append(k))
videos = [{'title': f'Faixa {i}', 'url': f'v{i}', 'duration': 200} for i in range(4)]
g.downloader = types.SimpleNamespace(get_playlist_videos=lambda u, log=None: {'title': 'X - Disco', 'videos': videos})
g.catalogo.discogs = lambda *a, **k: dict(cand, confidence_pct=40)
g.process_playlist('https://www.youtube.com/playlist?list=PL1')
t('playlist com nota baixa vai pra "Precisam de você"', pend and pend[-1]['kind'] == 'baixa_confianca'
  and pend[-1]['source_type'] == 'playlist' and 'Confiança 40%' in pend[-1]['reason'])
g.catalogo.discogs = lambda *a, **k: dict(cand, tracks=[{'title': 'a', 'duration': 1}] * 9, confidence_pct=95)
g.process_playlist('https://www.youtube.com/playlist?list=PL1')
t('playlist com nº de faixas muito diferente também', 'Nº de faixas não bate' in pend[-1]['reason'])

feitas = []
g.catalogo.discogs = lambda *a, **k: dict(cand, tracks=[{'title': f'Faixa {i}', 'duration': 200} for i in range(4)],
                                          confidence_pct=95)
g.acervo_index = types.SimpleNamespace(has=lambda k: False)
g.process_playlist_song = lambda url, *a, **k: (feitas.append(url), (url != 'v2', None))[1]
pend.clear()
g.process_playlist('https://www.youtube.com/playlist?list=PL1')
t('uma faixa que falha recusa a playlist (e para ali)', feitas == ['v0', 'v1', 'v2'] and pend
  and pend[-1]['kind'] == 'falha_download' and "Faixa 'Faixa 2'" in pend[-1]['reason'])

# trabalhador: o tipo do ITEM decide; erro numa playlist é falha, não "feito"
g._fila_item_ok = True
chamou = []
g.process_playlist = lambda u: chamou.append(('playlist', u))
g.process_single_video = lambda u: chamou.append(('album', u))
g._processar_item_da_fila({'tipo': 'playlist', 'url': 'p'})
g._processar_item_da_fila({'tipo': 'canal', 'url': 'c'})
t('fila: playlist e canal vão pro processador certo', chamou == [('playlist', 'p'), ('album', 'c')])
def explode(u):
    raise RuntimeError('rede caiu')
g.process_playlist = explode
try:
    g._processar_item_da_fila({'tipo': 'playlist', 'url': 'p'}); subiu = False
except RuntimeError:
    subiu = True
t('erro dentro da playlist chega ao trabalhador (vira falha com o local)', subiu)
fim()

"""
12.4 - nomes: faixas de playlist (Simone), número do artista no Discogs, álbum lido
da descrição. E as regressões: Steely Dan (Aja) continua certo.
"""
import os, sys, types, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
import nomes as N
import main
from falso_discogs import FalsoDiscogs, config_falsa

# ------------------------------------------------------------------ 9) número do artista
casos = {'Simone (3)': 'Simone', 'Jay White (3)': 'Jay White', 'Marina Sena (2)': 'Marina Sena',
         'Marina*': 'Marina', 'Paulo Braga*': 'Paulo Braga', 'Jay White (3), Paulo Braga*': 'Jay White, Paulo Braga',
         'Earth, Wind & Fire': 'Earth, Wind & Fire', "Sérgio Mendes & Brasil '66": "Sérgio Mendes & Brasil '66",
         'Blink-182': 'Blink-182', 'Simone (3) & Ivan Lins': 'Simone & Ivan Lins', '10cc': '10cc'}
for a, e in casos.items():
    t(f'nome de exibição: {a!r} -> {e!r}', N.nome_artista_exibicao(a) == e)

# candidato do Discogs: nome limpo pra fora, completo por dentro
import pontuacao as MHV
from catalogo import Catalogo
fd = FalsoDiscogs()
fd.release(101, 'Simone (3)', 'Pedaço De Mim', 1980, [('Começar De Novo', '3:20'), ('Pedaço De Mim', '4:01')], master=55)
mh = Catalogo({'discogs_token': 'x'})
fd.ligar(mh)
r = mh.discogs('Simone', 'Pedaço de Mim', log_func=lambda *a: None)
t(f"Discogs: 'artists' sai limpo ({r and r.get('artists')}) e o completo fica em 'artists_discogs' ({r and r.get('artists_discogs')})",
  r and r['artists'] == ['Simone'] and r['artists_discogs'] == ['Simone (3)'] and r['master_id'] == 55)
todos = mh.discogs('Simone', 'Pedaço de Mim', log_func=lambda *a: None, return_all_candidates=True)
t('o mesmo na lista de candidatos', todos and todos[0]['artists'] == ['Simone'] and todos[0]['artists_discogs'] == ['Simone (3)'])

# pasta e tags de faixa de playlist com "Simone (3)"
from pathlib import Path
out = tmp('nomes', 'SOM', 'x')[:-2]; shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
g.log = lambda m: logs.append(str(m)); g._reg = lambda *a: None
g.config = config_falsa(out)
fonte = tmp('pc', 'fonte.webm')
def baixar(url, pasta, cb=None):
    d = os.path.join(pasta, 'v.webm'); shutil.copy(fonte, d); return d
g.downloader = types.SimpleNamespace(download_audio=baixar, download_thumbnail=lambda *a, **k: None, last_error=None)
g.stats = {'discogs_covers': 0, 'youtube_covers': 0, 'albums_skipped': 0, 'albums_processed': 0}
g.metadata_manager = types.SimpleNamespace(add_metadata=lambda *a, **k: True, add_discogs_ids=lambda *a, **k: True)
g._ensure_acervo_and_queue = lambda: False
meta = {'tracks': [{'title': 'Começar De Novo', 'duration': 200}], 'artist': 'Simone (3)',
        'album_artist': 'Simone (3)', 'album': 'Pedaço De Mim', 'year': '1980'}
ok, pasta = g.process_playlist_song('u', 'SIMONE COMEÇAR DE NOVO (Audio)', 'Simone - Pedaço De Mim', 1, 1, playlist_metadata=meta)
mp3 = list(Path(out).rglob('*.mp3'))
t(f'pasta sem o número ({[p.parent.name for p in mp3]})', ok and mp3 and mp3[0].parent.name == 'Simone - Pedaço De Mim (1980)')
from mutagen.id3 import ID3
tags = ID3(str(mp3[0])) if mp3 else {}
t(f"tags sem o número (TPE1={tags.get('TPE1')}, TPE2={tags.get('TPE2')})",
  mp3 and str(tags.get('TPE1')) == 'Simone' and str(tags.get('TPE2')) == 'Simone')
t(f'arquivo com o nome oficial ({mp3[0].name if mp3 else None})', mp3 and mp3[0].name == '01 - Começar De Novo.mp3')

# corte de álbum (as tags são gravadas pelo AlbumCutter, via ffmpeg) também
pasta_alb = tmp('nomes', 'alb', 'x')[:-2]; shutil.rmtree(pasta_alb, ignore_errors=True); os.makedirs(pasta_alb)
shutil.copy(str(mp3[0]), os.path.join(pasta_alb, '01 - Faixa.mp3'))
ac = main.AlbumCutter('Jay White (3)', 'X', 'nada.wav', {'album_artist': 'Marina Sena (2)'}, pasta_alb, log_func=lambda *a: None)
ac.cuts = [{'track': 1, 'title': 'Faixa', 'start': 0, 'end': None}]
ac.add_tags()
tg = ID3(os.path.join(pasta_alb, '01 - Faixa.mp3'))
t(f"corte de álbum: TPE1={tg.get('TPE1')}, TPE2={tg.get('TPE2')}", str(tg.get('TPE1')) == 'Jay White' and str(tg.get('TPE2')) == 'Marina Sena')

# ------------------------------------------------------------------ 5) Simone: nomes de faixa da playlist
oficiais = ['Começar De Novo', 'Para Lennon Y McCartney = Para Lennon E McCartney', 'Pedaço De Mim',
            'Sob Medida', 'Encontros E Despedidas', 'Tô Que Tô', 'Atrevida', 'Gota D\'Água',
            'Cigarra', 'Iolanda']
videos = ['SIMONE COMEÇAR DE NOVO', 'SIMONE PARA LENNON & McCARTNEY', 'Simone - Pedaço de Mim (Audio)',
          'SIMONE SOB MEDIDA', 'Simone • Encontros & Despedidas', 'SIMONE TÔ QUE TÔ', 'Simone - Atrevida (Áudio Oficial)',
          "SIMONE GOTA D'ÁGUA", 'Simone - Cigarra [Audio]', 'SIMONE IOLANDA']
pm = {'artist': 'Simone', 'tracks': [{'title': o, 'duration': 0} for o in oficiais]}
logs.clear()
achados = [g._match_playlist_track(v, i + 1, pm) for i, v in enumerate(videos)]
certos = sum(1 for i, (tit, num, ok) in enumerate(achados) if ok and tit == oficiais[i] and num == i + 1)
t(f'Simone: {certos}/10 faixas com o nome oficial', certos == 10)
antigo = sum(1 for i, v in enumerate(videos) if MHV.titles_similar(v, oficiais[i]))
t(f'(reprodução: a comparação antiga casava {antigo}/10)', antigo < 10)

# sufixos de vídeo no nome do arquivo quando não casa
for v, e in [('Will You Still Love Me Tomorrow (Audio)', 'Will You Still Love Me Tomorrow'),
             ('Back To Black (Official Music Video)', 'Back To Black'), ('Rehab [HD]', 'Rehab'),
             ('Tears Dry On Their Own - Lyric Video', 'Tears Dry On Their Own'),
             ('Love Is A Losing Game (Remastered 2020)', 'Love Is A Losing Game (Remastered 2020)'),
             ('Me & Mr Jones (Live)', 'Me & Mr Jones (Live)')]:
    t(f'sufixo: {v!r} -> {N.limpar_titulo_de_video(v, "Amy Winehouse")!r}', N.limpar_titulo_de_video(v, 'Amy Winehouse') == e)
shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
meta2 = {'tracks': [{'title': 'Outra Coisa', 'duration': 200}], 'artist': 'Amy Winehouse', 'album': 'Frank', 'year': '2003'}
g.process_playlist_song('u', 'Will You Still Love Me Tomorrow (Audio)', 'Amy - Frank', 5, 13, playlist_metadata=meta2)
mp3 = [p.name for p in Path(out).rglob('*.mp3')]
t(f'sem casamento: arquivo sem "(Audio)" ({mp3})', mp3 == ['05 - Will You Still Love Me Tomorrow.mp3'])

# ------------------------------------------------------------------ regressão: Steely Dan (Aja)
aja = [('Black Cow', 310), ('Aja', 477), ('Deacon Blues', 457), ('Peg', 237), ('Home At Last', 334),
       ('I Got The News', 306), ('Josie', 273)]
pa = {'artist': 'Steely Dan', 'tracks': [{'title': n, 'duration': d} for n, d in aja]}
acertos = 0
for i, (n, d) in enumerate(aja):
    tit, num, ok = g._match_playlist_track(f'Steely Dan ~ {n} ~ Aja (Official Remaster)', i + 1, pa, audio_duration=d + 1)
    acertos += (ok and tit == n and num == i + 1)
t(f'Steely Dan (Aja): {acertos}/7 continuam certas', acertos == 7)

# ------------------------------------------------------------------ álbum lido da descrição
t('"Wes Montgomery (Jazz)" é título sem álbum', N.titulo_sem_album('Wes Montgomery (Jazz)', 'Wes Montgomery (Jazz)'))
t('"Wes Montgomery - Full House" tem álbum', not N.titulo_sem_album('Wes Montgomery', 'Full House'))
t('artista sem o "(Jazz)"', N.tirar_parenteses_genericos('Wes Montgomery (Jazz)') == 'Wes Montgomery')
descs = [
    ('Wes Montgomery - Full House (1962)\n\nTracklist:\n1. Full House 9:12', 'Full House'),
    ('Álbum: The Incredible Jazz Guitar of Wes Montgomery\nGravadora: Riverside', 'The Incredible Jazz Guitar of Wes Montgomery'),
    ('Taken from the album "Boss Guitar" (1963). Enjoy!', 'Boss Guitar'),
    ('Do álbum "Movin\' Along", gravado em 1960', "Movin' Along"),
    ('"Smokin\' at the Half Note" (1965)\nWes Montgomery, guitar', "Smokin' at the Half Note"),
    ('Subscribe! http://youtube.com/x\n#jazz #guitar', None),
    ('1. Four on Six 6:13\n2. West Coast Blues 7:23', None),
    ('Wes Montgomery - Jazz\nmore jazz', None),
]
for d, e in descs:
    a = N.album_da_descricao(d, 'Wes Montgomery')
    t(f'descrição -> {a!r} (esperado {e!r})', a == e)

# no fluxo: o álbum da descrição vai pra busca no Discogs
G2 = main.FullTracksDownloaderGUI; h = G2.__new__(G2); hlog = []
h.log = lambda m: hlog.append(str(m)); h._reg = lambda *a: hlog.append('REG ' + ' '.join(map(str, a)))
h.config = config_falsa(out)
h._ensure_acervo_and_queue = lambda: None
h.downloader = types.SimpleNamespace(get_video_info=lambda u: {'title': 'Wes Montgomery (Jazz)', 'duration': 2400,
    'description': 'Wes Montgomery - Full House (1962)\nRecorded live at Tsubo'})
buscas = []
h.catalogo = types.SimpleNamespace(last_error=None,
    discogs=lambda art, alb, **k: (buscas.append((art, alb)), [])[1])
h.pending_queue = types.SimpleNamespace(add=lambda **k: None)
h.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 80
h.stats = {'albums_skipped': 0}
h.process_single_video('https://youtu.be/wes')
t(f'busca no Discogs com o álbum da descrição ({buscas})', buscas == [('Wes Montgomery', 'Full House')])
t('log diz de onde veio o álbum', any('achei na descrição' in l for l in hlog) and any('álbum lido da descrição' in l for l in hlog))
# título que já traz o álbum: nada muda
buscas.clear()
h.downloader = types.SimpleNamespace(get_video_info=lambda u: {'title': 'Wes Montgomery - Boss Guitar (1963)', 'duration': 2400,
    'description': 'Wes Montgomery - Full House (1962)'})
h.process_single_video('https://youtu.be/wes2')
t(f'título com álbum: a descrição não interfere ({buscas})', buscas == [('Wes Montgomery', 'Boss Guitar')])
fim()

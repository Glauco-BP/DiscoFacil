import os
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'teste_pc.py')).read().split('# faixa de playlist de ponta a ponta')[0])
import shutil, types, os
from pathlib import Path
out=tmp('pc','SOM2','x')[:-2]; shutil.rmtree(out,ignore_errors=True); os.makedirs(out)
open(tmp('pc','ruim.webm'),'wb').write(os.urandom(50000))
G=main.FullTracksDownloaderGUI; g=G.__new__(G); logs=[]; g.log=lambda m: logs.append(str(m))
g.config=types.SimpleNamespace(get_output_directory=lambda: out, get=lambda *a,**k: '')
def baixar(url,pasta,cb=None):
    d=os.path.join(pasta,'x.webm'); shutil.copy(tmp('pc','ruim.webm'),d); return d
g.downloader=types.SimpleNamespace(download_audio=baixar, download_thumbnail=lambda *a,**k: None, last_error=None)
g.stats={'discogs_covers':0,'youtube_covers':0,'albums_skipped':0,'albums_processed':0}
g.metadata_manager=types.SimpleNamespace(add_metadata=lambda *a,**k: True, add_discogs_ids=lambda *a,**k: True)
g._ensure_acervo_and_queue=lambda: False
ok,_=g.process_playlist_song('u','Crença','Seu Jorge - The Other Side',1,1,playlist_metadata={'tracks':[{'title':'Crença','duration':200}],'artist':'Seu Jorge','album':'The Other Side','year':'2026'})
t('arquivo corrompido: falha limpa (sem exceção)', ok is False)
t('nenhum .mp3 falso deixado', not list(Path(out).rglob('*.mp3')))
t('temporário não fica preso', not list(Path(out).rglob('x.webm')))
print([l for l in logs if '✗' in l])
fim()

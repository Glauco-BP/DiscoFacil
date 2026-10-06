# Simula o .exe num computador SEM ffmpeg no PATH: sys.frozen + _MEIPASS com o ffmpeg do programa
import sys, os, shutil, types
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
BIN=os.path.join(TMP,'pc','bin')
sys.frozen=True; sys._MEIPASS=BIN
os.environ['PATH']='/nao/existe'          # nenhum ffmpeg no sistema
import main
from pathlib import Path
t(f'ffmpeg do programa encontrado ({main.FFMPEG_PATH})', main.FFMPEG_PATH==os.path.join(BIN,'ffmpeg.exe'))
t('pasta do ffmpeg entrou no PATH', os.environ['PATH'].startswith(BIN))
from pydub import AudioSegment
t('pydub aponta pro ffmpeg do programa', AudioSegment.converter==main.FFMPEG_PATH)
a=AudioSegment.from_file(tmp('pc','fonte.webm')); t(f'pydub lê o áudio sem ffmpeg no sistema ({len(a)/1000:.0f}s)', abs(len(a)/1000-200)<1)
t('ffprobe do programa mede', abs((main.duracao_do_arquivo(tmp('pc','fonte.webm')) or 0)-200)<1)
# faixa de playlist de ponta a ponta
out=tmp('pc','SOM','x')[:-2]; shutil.rmtree(out,ignore_errors=True); os.makedirs(out)
G=main.FullTracksDownloaderGUI; g=G.__new__(G)
logs=[]; g.log=lambda m: logs.append(str(m))
g.config=types.SimpleNamespace(get_output_directory=lambda: out, get=lambda *a,**k: '')
def baixar(url, pasta, cb=None):
    d=os.path.join(pasta,'Uhed46Bwfl4.webm'); shutil.copy(tmp('pc','fonte.webm'), d); return d
g.downloader=types.SimpleNamespace(download_audio=baixar, download_thumbnail=lambda *a,**k: None, last_error=None)
g.stats={'discogs_covers':0,'youtube_covers':0,'albums_skipped':0,'albums_processed':0}
g.metadata_manager=types.SimpleNamespace(add_metadata=lambda *a,**k: True, add_discogs_ids=lambda *a,**k: True)
g._ensure_acervo_and_queue=lambda: False
meta={'tracks':[{'title':'Crença','duration':200}],'artist':'Seu Jorge','album':'The Other Side','year':'2026'}
try:
    ok,pasta=g.process_playlist_song('https://youtu.be/x','Crença','Seu Jorge - The Other Side',1,1,playlist_metadata=meta)
except Exception as e:
    ok=False; print('EXCEÇÃO', e)
mp3=list(Path(out).rglob('*.mp3'))
t(f'faixa convertida sem ffmpeg no sistema ({[m.name for m in mp3]})', ok and len(mp3)==1)
if mp3:
    import subprocess
    info=subprocess.run([main.FFPROBE_PATH,'-v','error','-show_entries','stream=codec_name:format=duration','-of','csv=p=0',str(mp3[0])],capture_output=True,text=True).stdout.split()
    t(f'é MP3 de verdade e com a duração certa ({info})', info[0]=='mp3' and abs(float(info[-1])-200)<1)
t('temporário apagado', not (Path(out)/'.temp').exists())
print('\n'.join(l for l in logs if 'MP3' in l or 'Salvo' in l or 'Erro' in l or '✗' in l))
fim()

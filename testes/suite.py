import sys, os, subprocess, tempfile, shutil, time, glob
from comum import *
os.chdir(PROJ)
import numpy as np
from sint import *
# 1) compila tudo
bad=[f for f in glob.glob('*.py') if subprocess.run([sys.executable,'-m','py_compile',f]).returncode]
t('todos os .py compilam', not bad)
import main, downloader, dependencias, fila_unica, acervo_index, pending_queue, catalogo, pontuacao, versao
t('imports', True)
t('versão '+versao.APP_VERSION, main.APP_TITULO=='DiscoFácil '+versao.APP_VERSION)
# 2) regras básicas
t('corte no fim do silêncio', abs(main.posicao_de_corte_no_silencio(100.0,105.0)-104.5)<0.01)
t('taxa MP3 acompanha a fonte', main.taxa_mp3_para(53)==56 and main.taxa_mp3_para(129)==128 and main.taxa_mp3_para(None)==192)
t('duração do silêncio lida certo', main.duracao_do_silencio({'gaps':[{'duration':2.0}],'position':191.5,'end':192.0})==2.0)
# 3) alinhamento por intervalos (regressão do Julie Wilson)
dj=[151,159,173,147,141,190,192,151,175,128,164,170]
mj={'tracks':[{'number':i+1,'title':f'F{i+1}','duration':d} for i,d in enumerate(dj)]}
certos=[153.3,312.3,488.3,637.6,781.2,975.0,1171.0,1326.7,1504.5,1634.9,1802.9]
cj=main.SmartCutter(mj,{},tmp('fake.mp3'),log_func=lambda x:None)
cj._get_total_audio_duration=lambda:1980.0; cj._get_initial_silence_offset=lambda:1.2
cj.cluster_gaps=lambda tolerance=3.0:[{'position':p,'end':p,'votes':3,'gaps':[{'duration':4.0}]} for p in sorted(set(certos)|{1298.7,1483.3,1639.0,1784.8})]
t('alinhamento global (11/11)', sum(1 for i,x in enumerate(cj.cut_by_interval_alignment()[:-1]) if abs(x['end']-certos[i])<1.0)==11)
# 4) RMS mínimo com amostras float32
arq=salvar(np.concatenate([musica(9.5),silencio(1.0),musica(80)]),'rms.wav')
s=main.SmartCutter({'tracks':[]},{},arq,log_func=lambda *a,**k:None)
r=s._find_rms_minimum(10.0,8.0); t(f'RMS mínimo acha o silêncio ({r:.1f}s)', r and 9.4<=r<=10.6)
# 5) ajuste pelo início real: os 10 casos
def cort(a):
    c=main.SmartCutter.__new__(main.SmartCutter); c.audio_file=a; c._rms_audio_cache=None; c._env_cache=None; c._log=lambda *a,**k:None; return c
T=90.0
casos={'silêncio limpo':(np.concatenate([musica(T-3),fade(musica(1)),silencio(2),musica(60)]),T-0.5,None),
 'Gloria (recua)':(np.concatenate([musica(T-1),fade(musica(0.5)),silencio(0.5),musica(3.3,amp=0.006),musica(60)]),T+2.8,T),
 'intro que cresce (recua)':(np.concatenate([musica(T-1),fade(musica(0.5)),silencio(0.5),fade(musica(4,amp=0.02),entra=True),musica(60)]),T+3.5,T),
 'acorde final protegido':(np.concatenate([musica(T-5),silencio(0.5),fade(musica(2.5)),ruido(2),musica(60)]),T-0.5,None),
 'corte no fade':(np.concatenate([musica(T-4),fade(musica(2)),silencio(2),musica(60)]),T-3.0,None),
 'meio do silêncio (avança)':(np.concatenate([musica(T-3),fade(musica(1)),silencio(2),musica(60)]),T-1.6,T-0.5),
 'emendadas':(np.concatenate([musica(T),musica(60)]),T,None),
 'vinil, intro no chiado':(np.concatenate([musica(T-2),ruido(2),musica(3,amp=0.009),musica(60)]),T+2.5,None),
 'vinil limpo':(np.concatenate([musica(T-3),ruido(3),musica(60)]),T-0.5,None),
 'silêncio de 5s':(np.concatenate([musica(T-5),silencio(5),musica(60)]),T-0.5,None)}
for nome,(x,pos,esp) in casos.items():
    novo,mot=cort(salvar(x,'c.wav'))._inicio_real_da_proxima(pos,pos-80,pos+50)
    t(f'ajuste: {nome}', (mot is None) if esp is None else abs(novo-esp)<=0.6)
# 6) corte real de .webm + conferência
d=tempfile.mkdtemp(); src=os.path.join(d,'a.251.webm')
subprocess.run(['ffmpeg','-loglevel','error','-f','lavfi','-i','anoisesrc=d=180:c=pink','-c:a','libopus','-b:a','138k','-y',src],check=True)
ac=main.AlbumCutter.__new__(main.AlbumCutter); ac.audio_file=src; ac.output_dir=d; ac._log=lambda *a,**k:None
ac.cuts=[{'track':1,'title':'Um','start':0,'end':60},{'track':2,'title':'Dois','start':60,'end':135},{'track':3,'title':'Tres','start':135,'end':None}]
okc=ac.cut_tracks(); du=[main.duracao_do_arquivo(os.path.join(d,f)) for f in sorted(os.listdir(d)) if f.endswith('.mp3')]
t('corte real do .webm (60/75/45s)', okc and abs(du[0]-60)<1 and abs(du[1]-75)<1 and abs(du[2]-45)<1)
import corte_album
real=corte_album.duracao_do_arquivo; corte_album.duracao_do_arquivo=lambda p:180.0
ac.cuts=[{'track':1,'title':'Um','start':0,'end':60},{'track':2,'title':'Dois','start':60,'end':None}]
t('conferência barra faixa errada', ac.cut_tracks() is False); corte_album.duracao_do_arquivo=real
shutil.rmtree(d)
fim()

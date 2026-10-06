import sys
from comum import *
import numpy as np, main
from sint import *
def cort(a, durs, total):
    c=main.SmartCutter.__new__(main.SmartCutter); c.audio_file=a; c._rms_audio_cache=None; c._env_cache=None
    c._log=lambda *a,**k:None; c.metadata={'tracks':[{'duration':d} for d in durs]}
    c._get_total_audio_duration=lambda: total; return c
A=90.0
def disco(intro_amp=0.012, intro=4.5, chiado=0.003, extra=None):
    partes=[musica(A-1), fade(musica(1)), ruido(1.0,chiado)]        # faixa 1 + silêncio de fita
    if extra is not None: partes.append(extra)
    partes += [musica(intro,amp=intro_amp)+ruido(intro,chiado), musica(60), ruido(1.0,chiado), musica(50)]
    return np.concatenate(partes)
inicio_real = A + 1.0                     # onde a introdução da faixa 2 começa
def rodar(x, pos, durs, nome_arq='f.wav'):
    arq=salvar(x,nome_arq); total=len(x)/SR
    c=cort(arq,durs,total)
    fim2=inicio_real+4.5+60+0.5
    cuts=[{'start':0,'end':pos},{'start':pos,'end':fim2},{'start':fim2,'end':None}]
    antes,_=c._inicio_real_da_proxima(pos,20,fim2-20)
    c._env_cache=None
    c.ajustar_ao_inicio_da_proxima(cuts)
    return antes, cuts[0]['end']
# Caso Gloria faixa 7: corte 4s dentro da introdução baixinha; faixa 2 informada com 65s
pos=inicio_real+4.0
d2=4.5+60+0.5
x=disco()
antes,depois=rodar(x,pos,[A,d2,50])
t(f'reproduz: ajuste normal não mexia (ficou {antes:.1f})', abs(antes-pos)<0.01)
t(f'nova busca recua pro começo real ({depois:.1f}, real {inicio_real:.1f})', abs(depois-(inicio_real-0.5))<=0.7)
# mesmo áudio, mas a duração informada bate com o intervalo (sem falta) -> não mexe
_,dep=rodar(x,pos,[A,d2-4.0,50]); t(f'sem falta na faixa seguinte: não mexe ({dep:.1f})', abs(dep-pos)<0.01)
# falta pequena (1s) -> não mexe
_,dep=rodar(x,pos,[A,d2-3.0,50]); t(f'falta de só 1s: não mexe ({dep:.1f})', abs(dep-pos)<0.01)
# falta existe mas há um acorde alto entre o silêncio e o corte -> protege o fim da faixa 1
y=np.concatenate([musica(A-1), fade(musica(1)), ruido(1.0,0.003), fade(musica(2.0)), musica(2.5,amp=0.012)+ruido(2.5,0.003), musica(60), ruido(1.0), musica(50)])
_,dep=rodar(y,inicio_real+4.0,[A,d2,50]); t(f'acorde alto no meio: não mexe ({dep:.1f})', abs(dep-(inicio_real+4.0))<0.01)
# falta existe mas não há silêncio nenhum (faixas emendadas) -> não mexe
z=np.concatenate([musica(A+5.5), musica(60), musica(51)])
_,dep=rodar(z,pos,[A,d2,50]); t(f'emendadas sem silêncio: não mexe ({dep:.1f})', abs(dep-pos)<0.01)
# recuo nunca passa da falta + folga: falta de 2.5s mas intro de 4s -> fica no máximo 4s atrás
_,dep=rodar(x,pos,[A,d2-1.5,50]); t(f'recuo limitado pela falta ({pos-dep:.1f}s <= 4.0s)', 0<=pos-dep<=4.0+0.01)
# --- caso real Gloria 7->8 (silêncio digital longo + começo da faixa não tão suave) ---
def so(x):
    c=main.SmartCutter.__new__(main.SmartCutter); c.audio_file=salvar(x,'g.wav'); c._rms_audio_cache=None; c._env_cache=None; c._log=lambda *a,**k:None; return c
B=90.0
x=np.concatenate([musica(B-3,amp=0.1), fade(musica(1.5,amp=0.1)), silencio(2.5), musica(0.8,amp=0.05), musica(60,amp=0.1)])
ini=B-3+1.5+2.5; p=ini+0.6
n,m=so(x)._inicio_real_da_proxima(p,p-80,p+50)
t(f'réplica Gloria 7->8: recua pra antes do som ({p:.1f} -> {n:.1f}, som em {ini:.1f})', m is not None and ini-0.8<=n<ini)
# acorde final isolado depois de pausa longa: não pode ir pra faixa seguinte
y=np.concatenate([musica(B-4,amp=0.1), silencio(2.0), fade(musica(1.0,amp=0.2)), ruido(3.0,0.002), musica(60,amp=0.1)])
p=B-4+2.0+1.3
n,m=so(y)._inicio_real_da_proxima(p,p-80,p+50)
t(f'acorde final após pausa longa: não recua ({p:.1f} -> {n:.1f})', n>=p-0.01)
# 12.2: uma única amostra de valor mínimo no meio do silêncio digital (sobra do decodificador)
# não pode partir o silêncio em dois - mesmo resultado da réplica sem a amostra
x=np.concatenate([musica(B-3,amp=0.1), fade(musica(1.5,amp=0.1)), silencio(2.5), musica(0.8,amp=0.05), musica(60,amp=0.1)])
k=int((B-3+1.5+1.2)*SR); x[k]=1.0/32767
ini=B-3+1.5+2.5; p=ini+0.6
n,m=so(x)._inicio_real_da_proxima(p,p-80,p+50)
t(f'silêncio digital com 1 amostra perdida: recua igual ({p:.1f} -> {n:.1f}, som em {ini:.1f})', m is not None and ini-0.8<=n<ini)
fim()

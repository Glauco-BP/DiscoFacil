import numpy as np
from sint import *
def album_lp(seed=3):
    """8 faixas; 4 intervalos limpos, 3 curtos com chiado (como LP), 1 de 1,5s com chiado forte."""
    r=np.random.default_rng(seed)
    duracoes=[190,230,170,260,205,180,240,215]
    tipos=['limpo','curto','limpo','curto','forte','limpo','curto']
    partes=[]; fronteiras=[]; t=0.0
    for i,d in enumerate(duracoes):
        partes.append(fade(musica(d-1.5),entra=False) if False else musica(d-1.0)); partes.append(fade(musica(1.0)))
        t+=d
        if i<len(tipos):
            tp=tipos[i]
            if tp=='limpo': g=silencio(2.0)
            elif tp=='curto': g=ruido(0.7,0.004)
            else: g=ruido(1.5,0.02)
            partes.append(g); t+=len(g)/SR
            fronteiras.append(t)       # começo real da faixa seguinte
    return np.concatenate(partes), fronteiras, tipos

def album_limpo():
    duracoes=[180,200,150,240,210,190]
    partes=[]; fr=[]; t=0.0
    for i,d in enumerate(duracoes):
        partes.append(musica(d-1)); partes.append(fade(musica(1))); t+=d
        if i<len(duracoes)-1:
            partes.append(silencio(2)); t+=2; fr.append(t)
    return np.concatenate(partes), fr

def album_jazz_longo():
    """faixas longas (9-12 min) com pausas moderadas dentro (-12dB, não são fronteiras)"""
    duracoes=[560,720,610]
    partes=[]; fr=[]; t=0.0
    for i,d in enumerate(duracoes):
        bloco=[]
        for k in range(int(d//70)):
            bloco.append(musica(69.5)); bloco.append(musica(0.5,amp=0.08))   # pausa -12dB
        resto=d-70*int(d//70)
        if resto>0: bloco.append(musica(resto))
        partes.append(np.concatenate(bloco)); t+=d
        if i<len(duracoes)-1:
            partes.append(silencio(2)); t+=2; fr.append(t)
    return np.concatenate(partes), fr

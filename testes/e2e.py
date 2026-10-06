"""Ponta a ponta do corte: discos limpo, vinil e tipo Gloria (8 faixas, Discogs com erro de até 2s).
Confere cada corte contra o começo real da faixa e contra os cortes de referência
(referencia_e2e.json, gravada com --gravar). Cortes diferentes da referência = mudança no corte."""
import sys, os, json
from comum import *
import numpy as np, main
from sint import *
rng2=np.random.default_rng(11)
def album(tipo):
    dur=[164,178,243,205,210,248,177,244]
    partes=[]; fr=[]; t=0.0
    for i,d in enumerate(dur):
        if tipo=='gloria' and i==1:     # faixa 2 começa com introdução suave de 3,3s
            partes.append(musica(3.3,amp=0.006)); partes.append(musica(d-3.3-1))
        else:
            partes.append(musica(d-1))
        partes.append(fade(musica(1))); t+=d
        if i<len(dur)-1:
            g=silencio(2.0) if tipo!='vinil' else ruido(2.0,0.003)
            partes.append(g); t+=2.0; fr.append(t)
    # Discogs: durações arredondadas com erro de até ±2s
    disc=[{'title':f'Faixa {i+1}','duration':int(round(d+2+rng2.uniform(-2,2)))} for i,d in enumerate(dur)]
    return np.concatenate(partes), fr, disc
res={}
for tipo in ['limpo','vinil','gloria']:
    x,fr,disc=album(tipo); arq=salvar(x,f'e2e_{tipo}.wav')
    meta={'tracks':disc,'title':'X','artists':['Y']}
    ac=main.AlbumCutter('Y','X',arq,meta,TMP,log_func=lambda *a,**k:None)
    ok=ac.smart_cut(ac.detect_gaps())
    res[tipo]={'fronteiras':fr,'cortes':[c['end'] for c in ac.cuts[:-1]] if ok else None}
REF=os.path.join(TESTES,'referencia_e2e.json')
if '--gravar' in sys.argv:
    json.dump(res,open(REF,'w'),indent=1); print('referência gravada')
ref=json.load(open(REF)) if os.path.exists(REF) else None
for tipo,r in res.items():
    c=r['cortes']
    t(f'{tipo}: corte aceito', c is not None)
    if not c: continue
    t(f'{tipo}: {len(c)} cortes, todos perto do começo real', len(c)==len(r['fronteiras']) and all(-2.0<=f-a<=1.5 for a,f in zip(c,r['fronteiras'])))
    if ref:
        dif=max(abs(a-b) for a,b in zip(c,ref[tipo]['cortes'])) if ref[tipo]['cortes'] and len(ref[tipo]['cortes'])==len(c) else 99
        t(f'{tipo}: cortes idênticos à referência (maior diferença {dif:.2f}s)', dif<=0.05)
fim()

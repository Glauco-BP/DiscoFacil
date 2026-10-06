import sys
from comum import *
import main
from sint import *; from album_lp import *
def rodar(x, meta):
    arq=salvar(x,'alb.wav'); logs=[]
    ac=main.AlbumCutter('A','B',arq,meta,TMP,log_func=lambda m='',*a,**k: logs.append(str(m)))
    s=main.SmartCutter(meta,ac.detect_gaps(),arq,log_func=lambda m='',*a,**k: logs.append(str(m)))
    cuts=s.cut_by_cross_validation()
    if cuts: cuts=s.ajustar_ao_inicio_da_proxima(cuts)
    return cuts, logs
def conferir(nome, cuts, fr, logs):
    if not cuts:
        print(f"ERRO {nome}: rejeitado"); print('   '+'\n   '.join(logs[-3:])); return False
    ach=[c['end'] for c in cuts[:-1]]
    ok = len(ach)==len(fr) and all(-2.0 <= f-a <= 1.5 for a,f in zip(ach,fr))
    print(f"{'OK ' if ok else 'ERRO'} {nome}: {len(cuts)} faixas (esperado {len(fr)+1})")
    print('     reais :', [round(f,1) for f in fr]); print('     cortes:', [round(a,1) for a in ach])
    return ok
tudo=True
x,fr,_=album_lp()
cuts,logs=rodar(x,{'tracks':[]}); tudo&=conferir('LP com chiado, sem Discogs', cuts, fr, logs)
cuts,logs=rodar(x,{'tracks':[{'title':f'T{i}','duration':0} for i in range(8)]}); tudo&=conferir('LP com chiado, Discogs sem durações (8 faixas)', cuts, fr, logs)
x,fr=album_limpo(); cuts,logs=rodar(x,{'tracks':[]}); tudo&=conferir('disco com silêncios limpos (não muda)', cuts, fr, logs)
ok=not any('queda de volume' in l for l in logs); print(f"{'OK ' if ok else 'ERRO'}   ...e sem nenhuma fronteira inventada"); tudo&=ok
x,fr=album_jazz_longo(); cuts,logs=rodar(x,{'tracks':[]})
ok = not any('queda de volume' in l for l in logs)
print(f"{'OK ' if ok else 'ERRO'} jazz com faixas de 9-12 min e pausas moderadas: nenhuma divisão falsa"); tudo&=ok
t('discos sem Discogs (todos acima)', tudo)
fim()

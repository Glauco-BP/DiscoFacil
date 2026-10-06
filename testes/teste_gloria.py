import sys, types
from comum import *
import main
G = main.FullTracksDownloaderGUI
logs=[]
durs=[165,190,201,150,178,222,185,160,199,210,171,188]
def fmt(d): return f"{d//60}:{d%60:02d}"
def dados(): return {'tracks':[{'number':i+1,'title':f'Song {i+1}','duration':fmt(d)} for i,d in enumerate(durs)]}
real=sum(durs)+14.0   # Discogs erra 14s
class MH:
    ultimo_motivo_mb=None
    def __init__(s,modo): s.modo=modo
    def musicbrainz(s,a,b,n_faixas=None):
        if s.modo=='explode': raise RuntimeError('rede')
        if s.modo=='nada': s.ultimo_motivo_mb='nenhum lançamento'; return None
        extra = 14.0/12 if s.modo=='melhor' else 0.2
        return {'tracks':[{'title':f'Song {i+1}','duration_exact':d+extra} for i,d in enumerate(durs)]}
def fake(modo):
    o=types.SimpleNamespace(log=logs.append, catalogo=MH(modo), _medir_duracao_audio=lambda f: real)
    return o
def ok(c,msg): t(msg,c)
for modo in ['melhor','igual','nada','explode']:
    logs.clear(); d=dados(); fin=d['tracks']
    try:
        r=G._refine_durations_with_musicbrainz(fake(modo), d,'Gloria Lynne','Album','x.mp3')
    except Exception as e:
        r=None; ok(False,f'{modo}: exceção {e}'); continue
    ok(r is d, f'{modo}: devolve os dados, sem exceção')
    ok(all(isinstance(t['duration'],str) for t in fin), f'{modo}: duration continua texto')
    if modo=='melhor':
        ok(all('duration_seconds' in t for t in fin), 'melhor: duration_seconds gravado')
        ok(abs(sum(main.segundos_da_faixa(t) for t in fin)-real)<0.5, 'melhor: soma bate com o áudio')
        ok(any('Usando as durações do MusicBrainz' in l for l in logs), 'melhor: log de adoção')
    else:
        ok(not any('duration_seconds' in t for t in fin), f'{modo}: não mexeu')
    print('   log:', ' | '.join(l.strip() for l in logs))
# conversor
for f,e in [({'duration':'3:22'},202),({'duration':'1:02:03'},3723),({'duration':202},202),({'duration':'0:00'},0),
            ({'duration':'abc'},0),({'duration':None},0),({'duration_seconds':201.6,'duration':'3:22'},201.6),({},0),(None,0)]:
    ok(abs(main.segundos_da_faixa(f)-e)<1e-6, f'segundos_da_faixa({f}) = {e}')
# reenfileirar
d=dados(); d['tracks'][0]['duration_seconds']=166.4
raw=G._discogs_data_to_raw_shape(None,d)
ok(raw['tracks'][0]['duration']==166 and all(isinstance(t['duration'],int) for t in raw['tracks']),'formato bruto: inteiros')
# chapters com durações texto
caps=[{'title':f'Song {i+1}','start_seconds':sum(durs[:i]),'duration_seconds':durs[i]} for i in range(12)]
o=types.SimpleNamespace(log=logs.append)
try:
    r=G._merge_chapters_with_discogs(o,caps,dados()); ok(r is not None,'chapters + Discogs texto: junta sem erro')
except Exception as e: ok(False,f'chapters: exceção {e}')
# erro com local
try: 1+'a'
except Exception as e: print('   onde_quebrou:', main.onde_quebrou(e))
fim()

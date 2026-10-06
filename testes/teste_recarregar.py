import sys, os, shutil, tempfile, types
from comum import *
preparar()
import yt_dlp, downloader as D
FONTE=tmp('rec','bom.webm')
RUIM=tmp('rec','ruim.webm')
chamadas=[]
class FakeYDL:
    modo='normal'
    def __init__(s,o): s.o=o
    def __enter__(s): return s
    def __exit__(s,*a): return False
    def _checa(s):
        cook='cookiesfrombrowser' in s.o
        pcs=((s.o.get('extractor_args') or {}).get('youtube') or {}).get('player_client') or []
        chamadas.append((cook, tuple(pcs)))
        m=FakeYDL.modo
        erro=yt_dlp.utils.DownloadError('ERROR: [youtube] EG9Nbn0jILo: The page needs to be reloaded.')
        if m=='sempre': raise erro
        if m=='cookies' and cook: raise erro
        if m=='tv' and cook and '-tv_downgraded' not in pcs: raise erro
        idade=yt_dlp.utils.DownloadError("ERROR: [youtube] aObWsQd1Xgg: Sign in to confirm your age. Use --cookies-from-browser or --cookies for the authentication.")
        if m=='frank':
            if cook and '-tv_downgraded' not in pcs: raise erro
            if not cook and 'android' not in pcs: raise yt_dlp.utils.DownloadError('ERROR: [youtube] TwV5xUxBDxE: Requested format is not available')
            return
        if m=='idade':
            if not cook: raise idade
            if '-tv_downgraded' not in pcs: raise erro
            return
        if m in ('simone','simone_ruim') and cook:
            if '-tv_downgraded' in pcs:
                raise yt_dlp.utils.DownloadError('ERROR: [youtube] eY3Rkim7dmw: Requested format is not available. Use --list-formats for a list of available formats')
            raise erro
    def _grava(s):
        pcs=((s.o.get('extractor_args') or {}).get('youtube') or {}).get('player_client') or []
        ruim = (FakeYDL.modo=='simone_ruim' and 'cookiesfrombrowser' not in s.o) or (FakeYDL.modo=='frank' and 'android' in pcs)
        # como o yt-dlp real: o código do formato vai no nome (250 = opus baixo, 251 = opus alto)
        pasta=os.path.dirname(s.o['outtmpl']); d=os.path.join(pasta,'EG9Nbn0jILo.%s.webm' % ('250' if ruim else '251'))
        shutil.copy(RUIM if ruim else FONTE,d); return d
    def download(s,urls): s._checa(); s._grava()
    def extract_info(s,url,download=True):
        s._checa(); d=s._grava(); os.rename(d, d.replace('.251','').replace('.250','')); return {'id':'EG9Nbn0jILo','ext':'webm','abr':128,'acodec':'opus'}
yt_dlp.YoutubeDL=FakeYDL
def novo():
    cfg=types.SimpleNamespace(get=lambda k,d=None: {'settings.min_bitrate_kbps':80,'settings.cookies_browser':'firefox'}.get(k,d))
    dl=D.YouTubeDownloader.__new__(D.YouTubeDownloader); dl.config=cfg
    dl.last_error=None; dl.last_error_retryable=True
    dl._melhor_audio_disponivel=lambda url: 130
    dl._meets_min_bitrate=lambda *a,**k: True
    return dl
def baixa(dl):
    pasta=tempfile.mkdtemp(); logs=[]
    arq=dl.download_audio('https://youtu.be/EG9Nbn0jILo', pasta, logs.append)
    return arq, logs
# 1) como no computador do usuário: com cookies sempre falha
FakeYDL.modo='cookies'; dl=novo(); chamadas.clear()
arq,logs=baixa(dl)
t(f'erro com cookies: baixa sem cookies ({os.path.basename(arq or "")})', bool(arq) and os.path.exists(arq))
print('   '+'\n   '.join(l for l in logs if '↻' in l or '✓ Funcionou' in l or '🎧' in l))
chamadas.clear(); arq2,logs2=baixa(dl)
t(f'próxima faixa vai direto, sem erro ({len(chamadas)} chamada(s), cookies={chamadas[0][0]})', bool(arq2) and len(chamadas)==1 and not chamadas[0][0])
# 2) erro só com o cliente tv_downgraded: mantém os cookies
FakeYDL.modo='tv'; dl=novo(); chamadas.clear()
arq,logs=baixa(dl)
t('erro do cliente tv: resolve mantendo os cookies', bool(arq) and chamadas[-1][0] and '-tv_downgraded' in chamadas[-1][1])
chamadas.clear(); baixa(dl)
t(f'próxima faixa: direto, com cookies e sem o cliente tv ({chamadas[0]})', len(chamadas)==1 and chamadas[0][0] and '-tv_downgraded' in chamadas[0][1])
# 2b) caso real da Simone: degrau 1 dá "formato não disponível", degrau 2 (sem cookies) funciona
FakeYDL.modo='simone'; dl=novo(); chamadas.clear()
arq,logs=baixa(dl)
t(f'caso Simone: chega ao degrau sem cookies e baixa ({[c for c in chamadas][:4]})', bool(arq) and chamadas[-1][0] is False)
chamadas.clear(); arq2,_=baixa(dl)
t(f'caso Simone: faixa seguinte vai direto sem cookies ({chamadas})', bool(arq2) and len(chamadas)==1 and chamadas[0][0] is False)
# 2c) sem cookies o YouTube só libera áudio ruim: NÃO salva
FakeYDL.modo='simone_ruim'; dl=novo(); pasta=tempfile.mkdtemp(); logs=[]
arq=dl.download_audio('https://youtu.be/EG9Nbn0jILo', pasta, logs.append)
t(f'sem cookies e áudio ruim: descarta ({dl.last_error})', arq is None and 'não salvei' in (dl.last_error or '') and dl.last_error_retryable is False)
t(f'nenhum arquivo ruim deixado na pasta ({os.listdir(pasta)})', not [f for f in os.listdir(pasta) if f.endswith('.webm')])
# 2d) sem cookies e áudio bom: aceita
FakeYDL.modo='simone'; dl=novo(); arq,logs=baixa(dl)
t(f'sem cookies e áudio bom: aceita ({dl._medir_kbps(arq):.0f}kbps, alvo 130)', bool(arq))
# 2e) com cookies (sem contorno) a trava nova não se aplica
FakeYDL.modo='normal'; dl=novo(); arq,_=baixa(dl)
t('com cookies: trava nova não interfere', bool(arq) and not getattr(dl,'_sem_cookies_na_sessao',False))
# 2f) caso "Frank": sem cookies só o android (ruim) funciona -> tenta com a conta e fica com o bom
FakeYDL.modo='cookies'; dl=novo(); baixa(dl)            # ativa o contorno "sem cookies" na sessão
FakeYDL.modo='frank'; chamadas.clear(); arq,logs=baixa(dl)
kb=dl._medir_kbps(arq) if arq else 0
t(f'caso Frank: não aceita 48kbps, tenta com a conta e salva bom ({kb:.0f}kbps)', bool(arq) and kb>100)
print('   '+'\n   '.join(l for l in logs if '↻' in l or '🎧' in l or 'Ficando' in l))
# 2g) restrição de idade com contorno ativo: usa a conta só pra esse vídeo
FakeYDL.modo='cookies'; dl=novo(); baixa(dl)
FakeYDL.modo='idade'; chamadas.clear(); arq,logs=baixa(dl)
t(f'restrição de idade: baixa com a conta ({[c for c in chamadas if c[0]][:1]})', bool(arq) and any(c[0] and '-tv_downgraded' in c[1] for c in chamadas))
t('restrição de idade: não repete "Usando cookies"/"não consegui ler"', not any('Não consegui ler' in l for l in logs))
FakeYDL.modo='cookies'; chamadas.clear(); arq,_=baixa(dl)
t('depois do vídeo com idade, volta pro caminho sem cookies', bool(arq) and chamadas and chamadas[0][0] is False)
# 2h) classificador
P=D.YouTubeDownloader._parece_problema_de_cookies
t('dica do YouTube ("--cookies-from-browser") não é falha de leitura', not P('ERROR: [youtube] x: Sign in to confirm your age. Use --cookies-from-browser or --cookies for the authentication'))
t('falhas reais de leitura continuam reconhecidas', P('Could not copy Chrome cookie database') and P('Failed to decrypt with DPAPI') and P('failed to load cookies'))
# 3) falha em tudo: não trava, devolve None com o motivo
FakeYDL.modo='sempre'; dl=novo(); chamadas.clear()
arq,logs=baixa(dl)
t(f'falha total: devolve None sem exceção (motivo: {str(dl.last_error)[:60]})', arq is None and 'reloaded' in str(dl.last_error))
# 4) computador principal (sem erro): nada muda - nenhum cliente forçado, com cookies
FakeYDL.modo='normal'; dl=novo(); chamadas.clear()
arq,logs=baixa(dl)
t(f'sem erro: comportamento idêntico ao de antes ({chamadas})', bool(arq) and chamadas==[(True,())])
fim()

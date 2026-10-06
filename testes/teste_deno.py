import sys, os, io, zipfile, ssl, urllib.request, urllib.error, tempfile
from comum import *
os.environ['XDG_DATA_HOME']=tempfile.mkdtemp()
import dependencias as D
D.shutil.which=lambda n: None
buf=io.BytesIO()
with zipfile.ZipFile(buf,'w') as z: z.writestr('deno','#!/bin/sh\n')
dados=buf.getvalue()
class Resp(io.BytesIO):
    headers={'Content-Length':str(len(dados))}
    def geturl(s): return 'x'
    def __enter__(s): return s
    def __exit__(s,*a): return False
real=urllib.request.urlopen
def limpar():
    p=D.executavel_deno_local()
    if p.exists(): p.unlink()
# 1) certificado falha sem contexto, funciona com certifi
chamadas=[]
def urlopen_cert(req, timeout=None, context=None):
    chamadas.append(context)
    if context is None:
        raise urllib.error.URLError(ssl.SSLCertVerificationError('[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate'))
    return Resp(dados)
urllib.request.urlopen=urlopen_cert; limpar()
r=D.garantir_deno(); t(f'Windows novo (certificado): instala usando certifi ({r})', r=='instalado' and chamadas[-1] is not None)
# 2) sem internet de verdade: não mascara, devolve sem_rede com motivo
def urlopen_off(req, timeout=None, context=None): raise urllib.error.URLError(OSError('getaddrinfo failed'))
urllib.request.urlopen=urlopen_off; limpar()
r=D.garantir_deno(); t(f'sem internet: sem_rede com motivo ({D.ULTIMO_ERRO["deno"]})', r=='sem_rede' and 'getaddrinfo' in D.ULTIMO_ERRO['deno'])
# 3) duas falhas passageiras e depois funciona -> instala na MESMA abertura
n={'k':0}
def urlopen_instavel(req, timeout=None, context=None):
    if 'deno' in req.full_url:
        n['k']+=1
        if n['k']<=2: raise urllib.error.URLError(OSError('timed out'))
        return Resp(dados)
    raise urllib.error.URLError(OSError('sem yt-dlp aqui'))
urllib.request.urlopen=urlopen_instavel; limpar()
D.time.sleep=lambda s: None
logs=[]; ger=D.GerenciadorDeDependencias(log=logs.append); ger._verificar(False)
t('falhas passageiras: instala na 3ª tentativa, na mesma abertura', D.executavel_deno_local().exists() and any('Deno instalado' in l for l in logs))
print('   '+'\n   '.join(l for l in logs if 'Deno' in l or 'Falhou' in l))
# 4) falha nas 3 -> mensagem final com motivo
urllib.request.urlopen=urlopen_off; limpar()
logs=[]; ger=D.GerenciadorDeDependencias(log=logs.append); ger._verificar(False)
t('3 falhas: avisa, com o motivo, e libera a fila', ger._pronto.is_set() and sum('Falhou: URLError' in l for l in logs)==3 and any('próxima abertura' in l for l in logs))
urllib.request.urlopen=real
fim()

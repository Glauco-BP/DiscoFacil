"""
12.6 - baixar o próximo álbum enquanto o atual é cortado.
"""
import os, sys, subprocess, time, threading, shutil, glob, types
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1280x900x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
from pre_download import PreDownload

# ------------------------------------------------------------------ unidade
saida = tmp('ante', 'SOM', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
eventos = []
trava = threading.Lock()


def baixar_falso(url, pasta, cb=None, demora=0.6, falha=False):
    with trava:
        eventos.append(('ini', url, time.time()))
        time.sleep(demora)
        eventos.append(('fim', url, time.time()))
        if falha or 'falha' in url:
            return None
        p = os.path.join(pasta, url.rsplit('/', 1)[-1] + '.webm')
        open(p, 'wb').write(b'x' * 200000)
        return p


logs = []
os.makedirs(os.path.join(saida, '.temp', 'proximo', 'velho'), exist_ok=True)
pd = PreDownload(baixar_falso, lambda: saida, log=logs.append)
t('sobras de uma abertura anterior são apagadas', not os.path.exists(os.path.join(saida, '.temp', 'proximo')))
t('playlist não é antecipada', pd.iniciar({'tipo': 'playlist', 'url': 'u/pl', 'id': 'p'}) is False)
t('pendência não é antecipada', pd.iniciar({'tipo': 'pendencia', 'url': 'u/pd', 'id': 'q'}) is False)
t('disco único é antecipado', pd.iniciar({'tipo': 'disco_unico', 'url': 'u/a1', 'id': 'a1', 'titulo': 'Álbum 1'}))
t('pedir de novo o mesmo não baixa duas vezes', pd.iniciar({'tipo': 'disco_unico', 'url': 'u/a1', 'id': 'a1'}) is False)
destino = tmp('ante', '_temp', 'x')[:-2]
arq = pd.pegar('u/a1', mover_para=destino)
t(f'na vez dele: espera terminar e usa o arquivo ({os.path.basename(arq or "")})', arq and os.path.dirname(arq) == destino and os.path.exists(arq))
t('...e não sobra nada em .temp/proximo', not glob.glob(os.path.join(saida, '.temp', 'proximo', '*', '*')))
t('pegar um que não foi antecipado: None', pd.pegar('u/outro') is None)
# descartar enquanto baixa: apaga quando terminar
pd.iniciar({'tipo': 'canal', 'url': 'u/a2', 'id': 'a2', 'titulo': 'Álbum 2'}); time.sleep(0.1)
pd.descartar('teste')
time.sleep(0.9)
t('descartado durante o download: apagado quando termina', not glob.glob(os.path.join(saida, '.temp', 'proximo', '*', '*')) and pd.atual is None)
t('descartado não é usado', pd.pegar('u/a2') is None)
# falha no antecipado: None, baixa na vez dele
pd.iniciar({'tipo': 'disco_unico', 'url': 'u/falha', 'id': 'f'})
t('antecipado que falhou: None (baixa na vez dele)', pd.pegar('u/falha') is None)
# trocar de próximo: o anterior é descartado
pd.iniciar({'tipo': 'disco_unico', 'url': 'u/b1', 'id': 'b1'}); pd.iniciar({'tipo': 'disco_unico', 'url': 'u/b2', 'id': 'b2'})
time.sleep(1.5)
t('fila mudou: só o novo próximo fica', pd.atual and pd.atual['url'] == 'u/b2' and len(glob.glob(os.path.join(saida, '.temp', 'proximo', '*', '*'))) == 1)
pd.descartar('fim')

# ------------------------------------------------------------------ com o trabalhador da fila de verdade
import janela
root, app, main = janela.abrir()
eventos.clear()
real_baixar = lambda url, pasta, cb=None: baixar_falso(url, pasta, cb, demora=1.0)
with_lock = app._trava_download


def baixar_com_trava(*a, **k):
    with with_lock:
        return real_baixar(*a, **k)
app.downloader.download_audio = baixar_com_trava
app.pre_download._baixar = baixar_com_trava
cortes = []


def separar(audio, fonte, *a, **k):
    cortes.append(('ini', audio, time.time()))
    time.sleep(1.2)                       # "cortando"
    cortes.append(('fim', audio, time.time()))
    return True
app._process_separation_by_source = separar
app._refine_durations_with_musicbrainz = lambda d, *a, **k: d
pend = []


def processar(url):
    if 'pendente' in url:                 # identificação baixa: nada é baixado
        app.pending_queue.add(kind='baixa_confianca', url=url, video_title=url, reason='teste')
        return
    dd = {'found': True, 'title': 'X', 'artists': ['Y'], 'tracks': [{'title': 'a', 'duration': '3:00'}],
          'discogs_master_id': None, 'discogs_release_id': None, 'cover_image': None}
    app._download_and_process(url, {'title': url, 'duration': 180}, 'Y', url.rsplit('/', 1)[-1], '',
                              'discogs', dd['tracks'], True, dd)
app.process_single_video = processar
f = app._garantir_fila()
for n in ['d1', 'd2', 'pendente3', 'd4']:
    f.adicionar('canal', f'https://youtu.be/{n}', n)
app.dependencias._pronto.set()
app.trabalhador_ativo = True
t0 = time.time()
app._trabalhador_da_fila()
dt = time.time() - t0
for _ in range(20):
    root.update(); time.sleep(0.02)
baixados = [e[1] for e in eventos if e[0] == 'ini']
t(f'cada disco baixado uma vez só ({[b.rsplit("/", 1)[-1] for b in baixados]})',
  sorted(baixados) == sorted(['https://youtu.be/d1', 'https://youtu.be/d2', 'https://youtu.be/pendente3', 'https://youtu.be/d4'])
  or sorted(baixados) == sorted(['https://youtu.be/d1', 'https://youtu.be/d2', 'https://youtu.be/d4']))
ini_d2 = next(e[2] for e in eventos if e[0] == 'ini' and e[1].endswith('d2'))
corte_d1 = [c[2] for c in cortes[:2]]
t(f'o d2 começou a baixar durante o corte do d1 ({ini_d2 - corte_d1[0]:.1f}s depois do início do corte)',
  corte_d1[0] - 0.5 <= ini_d2 <= corte_d1[1])
t(f'os 3 discos levaram {dt:.1f}s (em sequência seriam ~{3 * 2.2 + 1:.1f}s)', dt < 3 * 2.2 + 0.5)
t('downloads nunca ao mesmo tempo', all(eventos[i][0] == 'ini' and eventos[i + 1][0] == 'fim' for i in range(0, len(eventos), 2)))
t('o antecipado do disco que foi pra "Precisam de você" foi apagado', not glob.glob(os.path.join(janela.SAIDA_MUSICAS, '.temp', 'proximo', '*', '*')))
log = app.progress_text.get('1.0', 'end') if True else ''
app._descarregar_log(); log = app.progress_text.get('1.0', 'end')
t('log diz quando baixa em segundo plano e quando usa', 'Baixando o próximo em segundo plano' in log and 'já tinha sido baixado em segundo plano' in log)
c = f.contagens()
t(f"fila: {c['feito']} feitos, {c['rejeitado']} recusado", c['feito'] == 3 and c['rejeitado'] == 1)
root.destroy()
fim()

"""
12.2 - arquivo de log por rodada: o que precisa estar lá pra diagnóstico.
"""
import os, sys, subprocess, glob, time
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1280x900x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import registro, types

# ---------------------------------------------------------------- unidade
cfg = types.SimpleNamespace(
    config={'api_keys': {'discogs_token': 'abcdefTOKEN123', 'groq': 'gsk_SEGREDO999',
                         'google_custom_search': {'api_key': 'AIzaCHAVE777'}}},
    get=lambda k, d=None: {'api_keys': {'discogs_token': 'abcdefTOKEN123', 'groq': 'gsk_SEGREDO999',
                                        'google_custom_search': {'api_key': 'AIzaCHAVE777'}},
                           'api_keys.discogs_token': 'abcdefTOKEN123', 'api_keys.groq': 'gsk_SEGREDO999',
                           'api_keys.google_custom_search': {'api_key': 'AIzaCHAVE777'},
                           'settings.min_bitrate_kbps': 96}.get(k, d),
    get_output_directory=lambda: '/x/SOM')
linhas = registro.resumo_configuracoes(cfg, 'DiscoFácil 9.9', confianca_minima=70, navegador_cookies='firefox')
txt = '\n'.join(linhas)
t('resumo: versão, pasta, bitrate, confiança, cookies', all(x in txt for x in ('DiscoFácil 9.9', '/x/SOM', '96 kbps', '70%', 'firefox')))
t('resumo: as 3 chaves só como "configurada"', txt.count('configurada') == 3 and not any(s in txt for s in ('TOKEN123', 'SEGREDO', 'CHAVE777')))
pasta = tmp('reg', 'x')[:-2]
import shutil; shutil.rmtree(pasta, ignore_errors=True)
r = registro.RegistroDaRodada('9.9', cfg)
r.linha('antes de haver pasta: gsk_SEGREDO999')
caminho = r.abrir(pasta)
r.linha('depois de abrir', 'DISCO')
try:
    int('x')
except Exception as e:
    onde = r.erro(e, 'convertendo')
r.fechar()
c = open(caminho, encoding='utf-8').read()
t(f'arquivo em <saída>/logs/DiscoFacil_<data-hora>.log ({os.path.relpath(caminho, pasta)})',
  os.path.dirname(caminho) == os.path.join(pasta, 'logs') and os.path.basename(caminho).startswith('DiscoFacil_'))
t('linhas de antes de abrir não se perdem (e saem mascaradas)', 'antes de haver pasta: ***' in c and 'SEGREDO' not in c)
t('etiqueta e hora em cada linha', any(l[2] == ':' and '[DISCO] depois de abrir' in l for l in c.splitlines()))
t(f'erro com arquivo:linha ({onde}) e traceback', '[ERRO] convertendo: ValueError' in c and 'teste_registro.py:' in c and 'Traceback' in c)

# ---------------------------------------------------------------- trabalhador de verdade
import janela
root, app, main = janela.abrir()
f = app._garantir_fila()
f.adicionar('disco_unico', 'https://youtu.be/ok', 'Disco que dá certo')
f.adicionar('disco_unico', 'https://youtu.be/pend', 'Disco sem Discogs')
f.adicionar('disco_unico', 'https://youtu.be/quebra', 'Disco que quebra')


def processar(item):
    if 'ok' in item['url']:
        app._reg('FONTE', app._descrever_fonte({'release_id': 1, 'master_id': 2, 'artists': ['A'], 'title': 'B',
                                                'tracks': [{'duration': 100}, {'duration': 0}],
                                                'confidence_pct': 95, 'score': 150}, 4))
        return True
    if 'pend' in item['url']:
        app.pending_queue.add(kind='nao_encontrado', url=item['url'], video_title=item['titulo'],
                              title_artist='A', title_album='B', year='', confidence_pct=0,
                              reason='Álbum não encontrado no Discogs')
        return bool(app._fila_item_ok)
    raise KeyError('title_artist')


app._processar_item_da_fila = lambda item: (setattr(app, '_fila_item_ok', True), processar(item))[1]
app.dependencias._pronto.set()
app._trabalhador_da_fila()
for _ in range(10):
    root.update(); time.sleep(0.03)
arq = glob.glob(os.path.join(janela.SAIDA_MUSICAS, 'logs', '*.log'))[0]
c = open(arq, encoding='utf-8').read()
linhas = c.splitlines()


def tem(et, *partes):
    return any(f'[{et}]' in l and all(p in l for p in partes) for l in linhas)


t('[DISCO] no começo de cada disco (título e link)', tem('DISCO', 'Disco que dá certo', 'youtu.be/ok') and tem('DISCO', 'Disco que quebra'))
t('[FONTE] com release, master, confiança, faixas com duração', tem('FONTE', 'release 1', 'master 2', 'confiança 95%', '2 faixas, 1 com duração', '4 edição'))
t('[PRONTO] no disco que deu certo', tem('PRONTO', 'Disco que dá certo'))
t('[PENDENTE] com o motivo', tem('PENDENTE', 'nao_encontrado', 'Álbum não encontrado no Discogs', 'Disco sem Discogs'))
t('[ERRO] com local (arquivo:linha) do erro no disco que quebra', tem('ERRO', 'KeyError', 'teste_registro.py:'))
t('[REJEITADO] com o motivo, quando a fila desiste', tem('REJEITADO', 'title_artist') or tem('FILA', 'title_artist'))
print('\n'.join(l for l in linhas if any(f'[{e}]' in l for e in ('DISCO', 'FONTE', 'PRONTO', 'PENDENTE', 'REJEITADO', 'FILA')))[:1500])
root.destroy()
fim()

"""
12.22 - "Modo leve" (ligado de fábrica): o ffmpeg com prioridade baixa e uma medição de cada vez, pra
não esquentar o notebook a ponto de o Windows cair (tela azul de 17/10/2026, com o editor aberto
durante a rodada). Os cortes são os mesmos nos dois modos.
"""
import os, sys, subprocess, time, threading, shutil, types
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1400x1000x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import numpy as np
from sint import musica, silencio, fade, salvar
import audio_util as AU
import edicao_cortes as EC
import corte_album

# ------------------------------------------------------------------ prioridade baixa (Windows)
AU.MODO_LEVE = True
k = AU._subprocess_no_window_kwargs('win32')
t(f'modo leve no Windows: ffmpeg sem janela e com prioridade baixa (flags {k.get("creationflags", 0):#x})',
  k.get('creationflags', 0) & AU.PRIORIDADE_BAIXA_WIN and k['creationflags'] & 0x08000000)
AU.MODO_LEVE = False
k = AU._subprocess_no_window_kwargs('win32')
t('...desligado: sem janela, prioridade normal', not k.get('creationflags', 0) & AU.PRIORIDADE_BAIXA_WIN
  and k['creationflags'] & 0x08000000)
t('...fora do Windows: nada muda', AU._subprocess_no_window_kwargs('linux') == {})

# ------------------------------------------------------------------ uma coisa de cada vez
partes = []
for d in (150, 128, 165, 140, 172):
    partes += [musica(d - 1), fade(musica(1)), silencio(2.5)]
disco = salvar(np.concatenate(partes), 'leve_disco.wav')

_run = subprocess.run
ao_mesmo_tempo = {'agora': 0, 'max': 0}
trava = threading.Lock()


def run_contando(cmd, *a, **k):
    """Conta quantos silencedetect rodam juntos (cada um demora um pouco de propósito)."""
    conta = any('silencedetect' in str(x) for x in cmd)
    if conta:
        with trava:
            ao_mesmo_tempo['agora'] += 1
            ao_mesmo_tempo['max'] = max(ao_mesmo_tempo['max'], ao_mesmo_tempo['agora'])
        time.sleep(0.3)
    try:
        return _run(cmd, *a, **k)
    finally:
        if conta:
            with trava:
                ao_mesmo_tempo['agora'] -= 1


def abrir(leve):
    AU.MODO_LEVE = leve
    onde = []
    _medir = EC.medir_audio
    EC.medir_audio = lambda arq: (onde.append(threading.current_thread() is threading.main_thread()), _medir(arq))[1]
    ao_mesmo_tempo.update(agora=0, max=0)
    subprocess.run = run_contando
    try:
        ed = EC.Edicao(disco, [], titulo='x').carregar()
    finally:
        subprocess.run = _run
        EC.medir_audio = _medir
    return ed, onde, ao_mesmo_tempo['max']


ed_l, onde_l, max_l = abrir(True)
ed_r, onde_r, max_r = abrir(False)
t(f'modo leve: o editor mede o volume antes dos silêncios, sem outra thread ({onde_l})', onde_l == [True])
t(f'...e os 3 limiares de silêncio vão um de cada vez (no máximo {max_l} ao mesmo tempo)', max_l == 1)
t(f'desligado: em paralelo, como na 12.21 (volume noutra thread, {max_r} limiares juntos)',
  onde_r == [False] and max_r == 3)
t(f'os cortes e os silêncios são os mesmos nos dois modos ({[round(m["pos"], 1) for m in ed_l.marcas]})',
  [m['pos'] for m in ed_l.marcas] == [m['pos'] for m in ed_r.marcas] and ed_l.silencios == ed_r.silencios
  and len(ed_l.marcas) == 4 and len(ed_l.envelope) == len(ed_r.envelope))
AU.MODO_LEVE = True

# ------------------------------------------------------------------ Configurações
import janela
root, app, main = janela.abrir()
import registro
t('vem ligado de fábrica (sem nada no config.json)', app.config.get('settings.modo_leve', None) in (None, True)
  and AU.MODO_LEVE is True)
from janela_config import SettingsWindow
import tkinter.messagebox as MB
_info = MB.showinfo; MB.showinfo = lambda *a, **k: None


def esperar(seg=0.3):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


sw = SettingsWindow(root, app.config, app); esperar()
t('Configurações: caixa "Modo leve (recomendado para notebook)", marcada', sw.modo_leve_var.get() is True)
sw.modo_leve_var.set(False)
sw.save_settings(); esperar()
t('...desmarcar e salvar: vale na hora e fica gravado', AU.MODO_LEVE is False
  and app.config.get('settings.modo_leve') is False)
t('...e o log da rodada diz como está', any('Modo leve: desligado' in l
                                            for l in registro.resumo_configuracoes(app.config, '12.22')))
app.config.set('settings.modo_leve', True)
app._carregar_modo_leve()
t('ao abrir o programa, lê das Configurações', AU.MODO_LEVE is True)
MB.showinfo = _info
root.destroy()
fim()

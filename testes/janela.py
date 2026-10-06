"""
Abre a janela do DiscoFácil de verdade (precisa de tela; aqui usamos o Xvfb)
e tira fotos, pra conferir a interface sem depender de olho humano.

    xvfb-run -s "-screen 0 1280x900x24" python testes/janela.py SAIDA.png [roteiro]

Roteiros: 'inicio' (padrão). Cada roteiro é uma função abaixo que mexe na
janela e tira fotos com foto('nome').

A pasta de saída e o config.json usados são temporários (testes/.tmp/janela),
nunca os do usuário. Nada vai pra internet: a verificação de componentes e a
busca de cookies são desligadas.
"""
import os, sys, json, shutil, subprocess, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *

BASE = tmp('janela', 'x')[:-2]
SAIDA_MUSICAS = os.path.join(BASE, 'SOM')


def preparar_config(extra=None):
    os.makedirs(SAIDA_MUSICAS, exist_ok=True)
    cfg = {"output_directory": SAIDA_MUSICAS,
           "api_keys": {"groq": "", "discogs_token": "TOKEN-SECRETO-DE-TESTE"},
           "settings": {"min_bitrate_kbps": 80}}
    if extra:
        for k, v in extra.items():
            cfg.setdefault('settings', {})[k] = v
    with open(os.path.join(BASE, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump(cfg, f)


def abrir(extra_cfg=None, limpar=True):
    """Cria a janela com config temporária. Devolve (root, app, main)."""
    if limpar:
        shutil.rmtree(BASE, ignore_errors=True)
    if limpar or not os.path.exists(os.path.join(BASE, 'config.json')):
        preparar_config(extra_cfg)
    os.chdir(BASE)
    import main
    import dependencias
    # sem rede: nada de baixar Deno/yt-dlp nem procurar cookies
    dependencias.GerenciadorDeDependencias.verificar_ao_abrir = lambda self: self._pronto.set()
    # nem depois de uma falha (o trabalhador da fila chama isto): teste não baixa nada da internet
    dependencias.GerenciadorDeDependencias.verificar_apos_falha = lambda self, *a, **k: None
    main.YouTubeDownloader._opcoes_de_cookies = lambda self, *a, **k: None
    root = main.tk.Tk()
    app = main.FullTracksDownloaderGUI(root)
    for _ in range(5):
        root.update(); time.sleep(0.05)
    return root, app, main


def foto(root, caminho):
    root.update(); time.sleep(0.3); root.update()
    subprocess.run(['import', '-window', 'root', caminho], check=True)
    return caminho


if __name__ == '__main__':
    destino = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else tmp('janela.png'))
    root, app, main = abrir()
    foto(root, destino)
    print('foto:', destino)
    root.destroy()

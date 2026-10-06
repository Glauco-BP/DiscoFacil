"""
Caminhos e preparação comuns a todos os testes.

- PROJ: a pasta do programa (a que contém main.py), um nível acima de testes/.
- TMP:  pasta de trabalho dos testes (testes/.tmp, apagável a qualquer hora).
        Pode ser trocada pela variável de ambiente DF_TESTE_TMP.
- preparar(): gera os arquivos de áudio que alguns testes usam (só se faltarem).
"""
import os, sys, shutil, subprocess

TESTES = os.path.dirname(os.path.abspath(__file__))
# DF_PROJ: roda os testes contra outra cópia do programa (ex.: a versão anterior, pra comparar)
PROJ = os.environ.get('DF_PROJ') or os.path.dirname(TESTES)
DADOS = os.path.join(TESTES, 'dados')
TMP = os.environ.get('DF_TESTE_TMP') or os.path.join(TESTES, '.tmp')
os.makedirs(TMP, exist_ok=True)

for p in (TESTES, PROJ):
    if p not in sys.path:
        sys.path.insert(0, p)

# Os testes rodam DENTRO de uma pasta descartável: se algum caminho relativo
# vazio escapar (Path('') é a pasta atual), o estrago fica em testes/.tmp.
CAIXA_DE_AREIA = os.path.join(TMP, 'pasta_atual')
os.makedirs(CAIXA_DE_AREIA, exist_ok=True)
os.chdir(CAIXA_DE_AREIA)


def tmp(*partes):
    """Caminho dentro da pasta de trabalho dos testes (cria as subpastas)."""
    p = os.path.join(TMP, *partes)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


FFMPEG = shutil.which('ffmpeg') or 'ffmpeg'
FFPROBE = shutil.which('ffprobe') or 'ffprobe'


def _ff(*args):
    subprocess.run([FFMPEG, '-loglevel', 'error', '-y', *args], check=True)


def preparar():
    """Arquivos de apoio. Gerados uma vez; apagar testes/.tmp força refazer."""
    # teste_pc / teste_corrompido: um "programa empacotado" com ffmpeg.exe e ffprobe.exe
    pc_bin = tmp('pc', 'bin', 'x')[:-2]
    for nome, real in (('ffmpeg.exe', FFMPEG), ('ffprobe.exe', FFPROBE)):
        d = os.path.join(pc_bin, nome)
        if not os.path.exists(d):
            shutil.copy(real, d)
            os.chmod(d, 0o755)
        # No Windows, "ffprobe" no PATH acha o ffprobe.exe (PATHEXT); aqui (Linux)
        # é preciso o nome sem .exe também, senão a pydub não acha o programa.
        sem_ext = os.path.join(pc_bin, nome[:-4])
        if os.name != 'nt' and not os.path.exists(sem_ext):
            os.symlink(d, sem_ext)
    fonte = tmp('pc', 'fonte.webm')
    if not os.path.exists(fonte):
        _ff('-f', 'lavfi', '-i', 'anoisesrc=d=200:c=pink:a=0.3', '-c:a', 'libopus', '-b:a', '128k', fonte)
    # teste_recarregar: um áudio bom (~138kbps) e um ruim (~45kbps)
    for nome, taxa in (('bom.webm', '138k'), ('ruim.webm', '45k')):
        d = tmp('rec', nome)
        if not os.path.exists(d):
            _ff('-f', 'lavfi', '-i', 'anoisesrc=d=30:c=white:a=0.5', '-c:a', 'libopus', '-b:a', taxa, d)
    # teste_gloria_real: as faixas 7 e 8 reais emendadas, como no álbum
    junto = tmp('junto.wav')
    if not os.path.exists(junto) and tem_faixas_reais():
        lista = tmp('junto.txt')
        with open(lista, 'w') as f:
            for n in ('gloria_07_I_Should_Care.mp3', 'gloria_08_My_Devotion.mp3'):
                f.write("file '%s'\n" % os.path.join(DADOS, n).replace("'", "'\\''"))
        _ff('-f', 'concat', '-safe', '0', '-i', lista, junto)
    return True


FAIXAS_REAIS = ('gloria_07_I_Should_Care.mp3', 'gloria_08_My_Devotion.mp3')


def tem_faixas_reais():
    """As duas faixas reais do teste_gloria_real (música com direitos autorais: ficam só no computador de
    quem desenvolve, não vão pro GitHub)."""
    return all(os.path.exists(os.path.join(DADOS, n)) for n in FAIXAS_REAIS)


# Registro dos resultados, igual em todos os testes
res = []


def t(nome, ok):
    res.append((nome, bool(ok)))
    print(('OK  ' if ok else 'FALHA ') + nome)


def fim():
    """Última linha padronizada: o executor (rodar_todos.py) lê esta linha."""
    ruins = [n for n, o in res if not o]
    if ruins:
        print('\nFALHARAM: ' + ', '.join(ruins))
        sys.exit(1)
    print('\nTODOS OS %d TESTES OK' % len(res))

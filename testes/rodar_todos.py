"""
Roda todos os testes do DiscoFácil, cada um num processo separado.

    python testes/rodar_todos.py            # todos
    python testes/rodar_todos.py suite e2e  # só alguns (nome sem .py)
    python testes/rodar_todos.py -v         # mostra a saída de todos, não só dos que falharem

Precisa de: ffmpeg/ffprobe no PATH e as bibliotecas do requirements.txt.
Arquivos de trabalho vão para testes/.tmp (pode apagar).
"""
import os, sys, subprocess, time, glob

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import comum

# fora da lista: geradores e auxiliares, que não são testes
AUXILIARES = {'comum', 'sint', 'album_lp', 'rodar_todos', 'janela', 'gerar_tutorial'}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    verboso = '-v' in sys.argv
    todos = sorted(os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(AQUI, '*.py')))
    # testes: teste_*.py, suite.py e e2e.py; o resto é auxiliar
    nomes = [n for n in todos if (n.startswith('teste_') or n in ('suite', 'e2e')) and n not in AUXILIARES]
    if args:
        nomes = [n for n in nomes if n in args]
    comum.preparar()
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONDONTWRITEBYTECODE='1')
    resultado = []
    for n in nomes:
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(AQUI, n + '.py')], cwd=comum.CAIXA_DE_AREIA, env=env,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        saida = (r.stdout or '') + (r.stderr or '')
        linhas = [l for l in saida.strip().splitlines() if l.strip()]
        ultima = linhas[-1] if linhas else ''
        ok = r.returncode == 0 and ultima.startswith('TODOS OS')
        resultado.append((n, ok, time.time() - t0, ultima))
        if verboso or not ok:
            print('-' * 70 + '\n' + n + '\n' + '-' * 70 + '\n' + saida)
    print('=' * 70)
    for n, ok, dt, ult in resultado:
        print(f"{'OK   ' if ok else 'FALHA'} {n:<22} {dt:6.1f}s  {ult[:60]}")
    falhas = [n for n, ok, _, _ in resultado if not ok]
    print('=' * 70)
    print('TUDO PASSOU (%d arquivos de teste)' % len(resultado) if not falhas else 'FALHARAM: ' + ', '.join(falhas))
    sys.exit(1 if falhas else 0)


if __name__ == '__main__':
    main()

"""
Conferência dos cortes: corta 10 discos de teste (sintéticos, menos um real) e
compara a posição EXATA de cada corte com testes/referencia_cortes.json (os
cortes da versão 12.8, que continuam iguais até a 12.18).

Uso (≈1 min):
    python testes/conferir_cortes.py              # compara com a referência
    python testes/conferir_cortes.py --gravar X   # grava os cortes de agora em X (pra nova referência)

Serve pra saber se um ajuste nos cortes mudou o resultado de discos que já
saíam certos. Mudou de propósito? Grave a nova referência e diga no MUDANCAS.md.
O caso "gloria_real" usa as faixas reais de testes/dados (não vão pro GitHub):
sem elas, ele é pulado.
"""
import sys, os, json, time
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
os.environ.setdefault('DF_TESTE_TMP', os.path.join(AQUI, '.tmp', 'conferir_cortes'))
from comum import *
preparar()
import numpy as np, main
from sint import *
from album_lp import album_lp, album_limpo, album_jazz_longo
rng2 = np.random.default_rng(11)
casos = {}
def album(tipo, dur):
    partes = []
    for i, d in enumerate(dur):
        if tipo == 'gloria' and i == 1:
            partes.append(musica(3.3, amp=0.006)); partes.append(musica(d - 3.3 - 1))
        else:
            partes.append(musica(d - 1))
        partes.append(fade(musica(1)))
        if i < len(dur) - 1:
            partes.append(silencio(2.0) if tipo != 'vinil' else ruido(2.0, 0.003))
    disc = [{'title': f'Faixa {i+1}', 'duration': int(round(d + 2 + rng2.uniform(-2, 2)))} for i, d in enumerate(dur)]
    return np.concatenate(partes), disc
dur = [164, 178, 243, 205, 210, 248, 177, 244]
for tipo in ['limpo', 'vinil', 'gloria']:
    x, disc = album(tipo, dur); casos[tipo] = (salvar(x, f'd_{tipo}.wav'), disc, False)
x, disc = album('limpo', [190, 230, 150, 260, 200, 175])
disc2 = [dict(d, duration=d['duration'] + (25 if i == 2 else 0)) for i, d in enumerate(disc)]
casos['discogs_errado'] = (salvar(x, 'd_err.wav'), disc2, False)
casos['discogs_errado_cv'] = (casos['discogs_errado'][0], disc2, True)
x, fr, _ = album_lp(); casos['lp_sem'] = (salvar(x, 'd_lp.wav'), [], True)
casos['lp_semdur'] = (casos['lp_sem'][0], [{'title': f'T{i}', 'duration': 0} for i in range(8)], True)
x, fr = album_limpo(); casos['limpo_sem'] = (salvar(x, 'd_limpo.wav'), [], True)
x, fr = album_jazz_longo(); casos['jazz_sem'] = (salvar(x, 'd_jazz.wav'), [], True)
casos['gloria_real'] = (tmp('junto.wav'), [{'title': 'I Should Care', 'duration': 0}, {'title': 'My Devotion', 'duration': 0}], True)
import subprocess, shutil
FORMATO = os.environ.get('DIG_FMT')
if FORMATO:
    for nome, (arq, faixas, cv) in list(casos.items()):
        dest = arq.rsplit('.', 1)[0] + '.' + FORMATO
        if not os.path.exists(dest):
            cod = {'opus': ['-c:a', 'libopus', '-b:a', '128k'], 'm4a': ['-c:a', 'aac', '-b:a', '160k'], 'mp3': ['-c:a', 'libmp3lame', '-b:a', '192k']}[FORMATO]
            subprocess.run([shutil.which('ffmpeg'), '-loglevel', 'error', '-y', '-i', arq] + cod + [dest], check=True)
        casos[nome] = (dest, faixas, cv)
if not tem_faixas_reais():
    casos.pop('gloria_real', None)
saida = {}
for nome, (arq, faixas, cv) in casos.items():
    meta = {'tracks': [dict(f, number=i + 1) for i, f in enumerate(faixas)], 'title': 'X', 'artists': ['Y']}
    a = time.time()
    ac = main.AlbumCutter('Y', 'X', arq, meta, TMP, log_func=lambda *a, **k: None)
    ok = ac.smart_cut(ac.detect_gaps(), allow_cross_validation=cv)
    saida[nome] = {'ok': bool(ok), 'seg': round(time.time() - a, 2),
                   'cortes': [[round(c['start'], 6), None if c.get('end') is None else round(c['end'], 6), c['title']]
                              for c in ac.cuts] if ok else None}

if '--gravar' in sys.argv:
    destino = sys.argv[sys.argv.index('--gravar') + 1]
    json.dump(saida, open(destino, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    print('gravado em', destino)
    sys.exit(0)
ref = json.load(open(os.path.join(AQUI, 'referencia_cortes.json'), encoding='utf-8'))
diferentes = []
for nome, r in saida.items():
    esperado = ref.get(nome) or {}
    igual = r['ok'] == esperado.get('ok') and r['cortes'] == esperado.get('cortes')
    print(f"{'IGUAL    ' if igual else 'DIFERENTE'} {nome:<18} {r['seg']:5.1f}s")
    if not igual:
        diferentes.append(nome)
print('=' * 50)
print('CORTES IGUAIS À REFERÊNCIA' if not diferentes else 'MUDARAM: ' + ', '.join(diferentes))
sys.exit(1 if diferentes else 0)

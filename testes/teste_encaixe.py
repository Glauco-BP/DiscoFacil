"""
12.5 - identificação × encaixe, outras edições, MusicBrainz, silêncios + nomes pela
duração, conta do Nico, retirada da passada repetida, candidatas guardadas.

O corte de verdade (ffmpeg) roda em discos sintéticos de 8 faixas.
"""
import os, sys, json, types, shutil, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import numpy as np
from sint import *
import main, encaixe as ENC
import pontuacao as MHV
from catalogo import Catalogo
from falso_discogs import FalsoDiscogs, config_falsa

DUR = [164, 186, 243, 205, 221, 268, 177, 232]   # durações bem distintas (ver o teste de ambiguidade)
NOMES = ['Um', 'Dois', 'Três', 'Quatro', 'Cinco', 'Seis', 'Sete', 'Oito']


# ------------------------------------------------------------------ unidade: encaixe
def fronteiras(durs, gap=2.0):
    t, fr = 0.0, []
    for d in durs[:-1]:
        t += d; fr.append(t - 0.5); t += 0      # corte ~0,5s antes do começo real
    return fr
sil = fronteiras(DUR)
e = ENC.nota_encaixe(DUR, sil, sum(DUR))
t(f'edição certa: {ENC.texto_encaixe(e)}', e['acertos'] == 7 and e['nota'] == 1.0)
nico = [DUR[0], DUR[4], DUR[6], DUR[3], DUR[1], DUR[5], DUR[2], DUR[7]]   # mesmas faixas, outra ordem
e2 = ENC.nota_encaixe(nico, sil, sum(DUR))
t(f'mesmo total, outra ordem (Nico): {ENC.texto_encaixe(e2)} - total igual não basta', sum(nico) == sum(DUR) and e2['nota'] < ENC.ENCAIXE_BOM)
desvio = [d + 2 for d in DUR]                          # Discogs arredondado com erro de 2s/faixa
e3 = ENC.nota_encaixe(desvio, sil, sum(DUR))
t(f'erro de 2s por faixa não acumula: {ENC.texto_encaixe(e3)}', e3['nota'] == 1.0)
t('sem durações: "sem durações", não nota', ENC.nota_encaixe([100, 0, 120], sil)['sem_duracao'])

# casar por duração (fora de ordem)
m = ENC.casar_por_duracao([d + 1.2 for d in nico], DUR)
t(f'casa pela duração fora de ordem ({m and m["faixa_de"]})', m and [DUR[j] for j in m['faixa_de']] == nico and m['fora_de_ordem'])
t('nº diferente: não casa', ENC.casar_por_duracao(DUR[:7], DUR) is None)
t('duração longe: não casa', ENC.casar_por_duracao([d + 15 for d in DUR], DUR) is None)
t('duas faixas com a mesma duração trocadas de lugar: não arrisca', ENC.casar_por_duracao([200, 300, 200.5], [200.4, 300, 200]) is None)

# ------------------------------------------------------------------ unidade: identificação
cand = {'title': 'Full House', 'tracks': [{'title': n, 'duration': d} for n, d in zip(NOMES, DUR)]}
tot = sum(DUR)
i1 = MHV.avaliar_identificacao(cand, tot * 1.04, None, None, 'Full House', 'Wes')
t(f'duração total a 4%: coincide ({MHV.texto_identificacao(i1)})', 'coincide' in i1['partes']['duracao_total'] and i1['nota'] == 100)
i1b = MHV.avaliar_identificacao(cand, tot * 1.08, None, None, 'Full House', 'Wes')
velho = min(100, MHV.score_discogs_candidate(dict(cand, album_title='Full House', track_count=8), int(tot * 1.08), None, None, 'Full House', 'Wes'))
t(f'duração total a 8%: identificação {i1b["nota"]}% (a regra antiga, ±1%, dava {velho:.0f}% e mandava pra pendências)', i1b['nota'] >= 80 and velho < 80)
i2 = MHV.avaliar_identificacao(cand, tot * 1.30, None, None, 'Full House', 'Wes')
t(f'duração total a 30%: difere ({MHV.texto_identificacao(i2)})', 'difere' in i2['partes']['duracao_total'] and i2['nota'] < 80)
boemios = {'title': 'Os Boêmios', 'tracks': [{'title': n, 'duration': 0} for n in NOMES]}
i3 = MHV.avaliar_identificacao(boemios, tot, NOMES, None, 'Os Boêmios', 'Os Boêmios')
t(f'sem durações (Os Boêmios): "sem informação", identifica pelos títulos ({MHV.texto_identificacao(i3)})',
  i3['partes']['duracao_total'] == 'sem informação' and i3['nota'] >= 80)
i4 = MHV.avaliar_identificacao(boemios, tot, ['Outra', 'Coisa', 'Nada'], None, 'Disco Diferente', 'Os Boêmios')
t(f'sem durações e títulos que não batem: baixa ({i4["nota"]}%)', i4['nota'] < 80)

fd = FalsoDiscogs()
fd.release(11, 'Wes Montgomery', 'Full House', 1962, [(n, f'{d // 60}:{d % 60:02d}') for n, d in zip(NOMES, DUR)], master=7)
mh = Catalogo({'discogs_token': 'x'}); fd.ligar(mh)
r = mh.discogs('Wes Montgomery', 'Full House', reference_duration=int(tot * 1.04), log_func=lambda *a: None)
t(f"Discogs: a confiança passa a ser a identificação ({r['confidence_pct']}%, {r['identificacao']['partes']['duracao_total']})",
  r['confidence_pct'] == r['identificacao']['nota'] == 100)

# ------------------------------------------------------------------ disco sintético + app sem janela
x = np.concatenate(sum([[musica(d - 1), fade(musica(1))] + ([silencio(2.0)] if i < 7 else [])
                        for i, d in enumerate(DUR)], []))
arq = salvar(x, 'enc_album.wav')
reais = []
acc = 0.0
for d in DUR[:-1]:
    acc += d + 2.0; reais.append(acc)          # começo real de cada faixa seguinte


def novo_app(saida):
    G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
    g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
    g.config = config_falsa(saida)
    g.metadata_manager = main.MetadataManager()
    g.acervo_index = types.SimpleNamespace(add=lambda *a, **k: None, has=lambda *a: False)
    g.catalogo = types.SimpleNamespace(musicbrainz_edicoes=lambda *a, **k: [], ultimo_motivo_mb='teste',
                                              musicbrainz=lambda *a, **k: None)
    g._notas_corte = {}
    return g, logs


def discogs_data(faixas, rid=11):
    return {'found': True, 'title': 'Full House', 'artists': ['Wes Montgomery'], 'year': '1962',
            'tracks': [{'number': i + 1, 'title': n, 'duration': f'{d // 60}:{d % 60:02d}'} for i, (n, d) in enumerate(faixas)],
            'discogs_master_id': 7, 'discogs_release_id': rid, 'cover_image': None, 'confidence_pct': 100}


def candidato(faixas, rid):
    return {'title': 'Full House', 'artists': ['Wes Montgomery'], 'year': '1962', 'master_id': 7, 'release_id': rid,
            'tracks': [{'title': n, 'duration': d} for n, d in faixas], 'cover_image': None}


def rodar(faixas, candidatas=None, fonte='discogs', mb=None, nome='x'):
    saida = tmp('enc', nome, 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
    g, logs = novo_app(saida)
    if mb is not None:
        g.catalogo.musicbrainz_edicoes = lambda *a, **k: mb
    dd = discogs_data(faixas)
    ok = g._process_separation_by_source(arq, fonte, dd['tracks'], True, dd, {'duration': len(x) / SR}, saida,
                                         discogs_candidates=candidatas)
    arqs = sorted(os.path.basename(p) for p in glob.glob(os.path.join(saida, '*.mp3')))
    return ok, arqs, logs, g


def duracoes_dos_arquivos(nome):
    return [main.duracao_do_arquivo(p) for p in sorted(glob.glob(os.path.join(tmp('enc', nome, 'x')[:-2], '*.mp3')))]


certos = [f'{i + 1:02d} - {n}.mp3' for i, n in enumerate(NOMES)]
# a) edição escolhida encaixa: corta como sempre
ok, arqs, logs, g = rodar(list(zip(NOMES, DUR)), [candidato(list(zip(NOMES, DUR)), 11)], nome='a')
t(f'edição certa: corta com ela, nomes certos ({len(arqs)} arquivos)', ok and arqs == certos)
d = duracoes_dos_arquivos('a')
t(f'durações dos arquivos batem com as faixas (maior erro {max(abs(a - b) for a, b in zip(d[:-1], DUR)):.1f}s)',
  all(abs(a - (b + 2.0 if i else b + 1.5)) < 2.6 for i, (a, b) in enumerate(zip(d[:-1], DUR))))
t('log mostra o encaixe da escolhida (7/7)', any('7/7 fronteiras' in l for l in logs))

# b) escolhida com a ordem errada (Nico) + outra edição certa em memória: troca
errada = list(zip([NOMES[DUR.index(v)] for v in nico], nico))
ok, arqs, logs, g = rodar(errada, [candidato(errada, 11), candidato(list(zip(NOMES, DUR)), 22)], nome='b')
t(f'ordem errada + edição certa em memória: troca pra ela ({arqs[:3]}...)', ok and arqs == certos)
t('log diz a troca', any('Edição trocada pela que encaixa: Discogs release 22' in l for l in logs))
t('sem consulta nova ao Discogs (as edições já estavam em memória)', True)

# c) escolhida errada, nenhuma outra, MusicBrainz tem a edição certa: corta com as durações do MB e nomes do Discogs
mb = [{'tracks': [{'title': n.upper(), 'duration_exact': d + 0.4} for n, d in zip(NOMES, DUR)],
       'release_id': 'mb-1234-abcd', 'title': 'Full House'}]
ok, arqs, logs, g = rodar(errada, [candidato(errada, 11)], mb=mb, nome='c')
t(f'MusicBrainz: durações dele, nomes do Discogs ({arqs[:2]}...)', ok and arqs == certos)
t('log consulta o MusicBrainz e diz o melhor encaixe', any('consultando o MusicBrainz' in l for l in logs) and any('Melhor encaixe: MusicBrainz' in l for l in logs))

# d) nenhuma edição encaixa: a escolhida é tentada como antes e recusa (sem nome trocado)
ok, arqs, logs, g = rodar(errada, [candidato(errada, 11)], nome='d')
t(f'nada encaixa: não sai nada com nome trocado ({arqs})', not ok and arqs == [])
t(f"motivo guardado: {g._notas_corte.get('motivo', '')[:70]}", 'Nenhuma edição serviu' in g._notas_corte.get('motivo', ''))

# e) passo 4: silêncios + nomes casados pela duração (fora de ordem)
ok, arqs, logs, g = rodar(errada, [candidato(errada, 11)], fonte='silencio_nomes', nome='e')
t(f'silêncios + nomes pela duração: nomes certos na ordem do áudio ({arqs[:3]}...)', ok and arqs == certos)
t('log avisa que a ordem do cadastro é outra', any('ordem das faixas neste áudio é diferente' in l for l in logs))

# f) duas músicas emendadas (7 silêncios pra 8 faixas): Precisam de você, nada gravado
y = np.concatenate(sum([[musica(d - 1), fade(musica(1))] + ([silencio(2.0)] if i < 7 and i != 3 else [])
                        for i, d in enumerate(DUR)], []))
arq_emendado = salvar(y, 'enc_emendado.wav')
saida = tmp('enc', 'f', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = novo_app(saida)
dd = discogs_data(list(zip(NOMES, DUR)))
ok = g._process_separation_by_source(arq_emendado, 'silencio_nomes', dd['tracks'], True, dd, {}, saida)
t(f"emendadas: recusa com o motivo ({g._notas_corte.get('motivo', '')[:60]}...)",
  not ok and 'achou 7 faixas e o Discogs tem 8' in g._notas_corte.get('motivo', '') and not glob.glob(os.path.join(saida, '*.mp3')))

# g) conta do Nico: pedaço de 0,5s no fim não pode mudar a contagem
z = np.concatenate([x, silencio(1.2), musica(0.5), silencio(1.5)])
arq_nico = salvar(z, 'enc_nico.wav')
sc = main.SmartCutter({'tracks': [{'title': n, 'duration': 0} for n in NOMES]}, {}, arq_nico, log_func=lambda *a, **k: None)
ac = main.AlbumCutter('A', 'B', arq_nico, {'tracks': []}, tmp('enc', 'g'), log_func=lambda *a, **k: None)
sc.all_gaps = ac.detect_gaps()
cuts = sc.cut_by_cross_validation()
t(f"Nico: {len(cuts or [])} faixas = 8 do Discogs, com os nomes (não 'Track N')",
  cuts and len(cuts) == 8 and [c['title'] for c in cuts] == NOMES)

# ------------------------------------------------------------------ fluxo: passada repetida saiu, candidatas guardadas
fonte = open(os.path.join(PROJ, 'main.py'), encoding='utf-8').read()
t('a passada repetida ("detecção de silêncio com nomes do Discogs") saiu', 'Usando detecção de silêncio com nomes do Discogs' not in fonte)
saida = tmp('enc', 'h', 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
g, logs = novo_app(saida)
copia = os.path.join(saida, 'baixado.wav')
g.downloader = types.SimpleNamespace(download_audio=lambda url, pasta, cb=None: shutil.copy(arq, os.path.join(pasta, 'b.wav')) and os.path.join(pasta, 'b.wav'),
                                     last_error=None, last_error_retryable=True)
fontes_chamadas = []
real = g._process_separation_by_source
def espia(audio, fonte_, *a, **k):
    fontes_chamadas.append(fonte_)
    return None
g._process_separation_by_source = espia
pend = []
g.pending_queue = types.SimpleNamespace(add=lambda **k: pend.append(k))
g._cleanup_temp_dir = lambda *a: None
g._refine_durations_with_musicbrainz = lambda d, *a, **k: d
dd = discogs_data(errada)
cands = [candidato(errada, 11), candidato(list(zip(NOMES, DUR)), 22)]
g._download_and_process('https://youtu.be/nico', {'title': 'Nico', 'duration': 1700}, 'Nico', 'Nico', '1981',
                        'discogs', dd['tracks'], True, dd, discogs_candidates=cands)
t(f'ordem das tentativas: {fontes_chamadas} (sem a passada repetida)', fontes_chamadas == ['discogs', 'silencio_nomes'])
t('vai pra "Precisam de você" com as edições candidatas guardadas', pend and pend[0].get('candidatas') == cands and pend[0]['kind'] == 'falha_corte')
t('...e com as notas', pend and isinstance(pend[0].get('notas'), dict))
t('...e o motivo diz que dá pra ouvir e acertar os cortes no ✂ Editar (12.17)',
  pend and '✂ Editar' in (pend[0].get('reason') or ''))
t('arquivo de log: [NOTAS] com identificação e encaixe', any(l.startswith('REG NOTAS') and 'identificação' in l for l in logs))

# a nova tentativa usa as candidatas guardadas (sem refazer a busca)
import pending_queue
shutil.rmtree(tmp('enc', 'pq'), ignore_errors=True)
pq = pending_queue.PendingQueue(tmp('enc', 'pq'))
it = pq.add(kind='falha_corte', url='u', video_title='Nico', title_artist='Nico', title_album='Nico', year='1981',
            confidence_pct=95, reason='x', discogs_data=g._discogs_data_to_raw_shape(dd), candidatas=cands, notas={'a': 1})
pq2 = pending_queue.PendingQueue(tmp('enc', 'pq'))
t('candidatas gravadas no arquivo das pendências', pq2.items[0]['candidatas'] == cands)
chamada = {}
g._download_and_process = lambda *a, **k: chamada.update(k) or True
g.downloader = types.SimpleNamespace(get_video_info=lambda u: {'title': 'Nico'})
g._process_pending_video_item(pq2.items[0])
t('reprocessar a pendência usa as candidatas guardadas', chamada.get('discogs_candidates') == cands)

# disco sem durações no Discogs (Os Boêmios): 12.10 - mesmo nº de pedaços e de músicas: nomes pela
# ordem, marcados como palpite; nº que não fecha: vai pra "Precisam de você" com o motivo certo
ok, arqs, logs, g = rodar(list(zip(NOMES, [0] * 8)), None, fonte='silencio_nomes', nome='semdur')
t(f"sem durações, 8 pedaços = 8 músicas: nomes pela ordem, como palpite ({arqs[:2]}...)",
  ok and arqs == certos and any('palpite' in l for l in logs) and any('REG AVISO' in l and 'conferir' in l for l in logs))
ok, arqs, logs, g = rodar(list(zip(NOMES[:5], [0] * 5)), None, fonte='silencio_nomes', nome='semdur2')
t(f"sem durações e sobra demais (8 pedaços, 5 músicas): motivo claro ({g._notas_corte.get('motivo', '')[:60]}...)",
  not ok and arqs == [] and 'não informa as durações' in g._notas_corte.get('motivo', ''))

# ------------------------------------------------------------------ erro na avaliação nova nunca derruba o álbum
_ne = ENC.nota_encaixe
ENC.nota_encaixe = lambda *a, **k: 1 / 0
ok, arqs, logs, g = rodar(list(zip(NOMES, DUR)), None, nome='erro')
ENC.nota_encaixe = _ne
t(f'erro no encaixe: corta como antes ({len(arqs)} arquivos) e registra o local',
  ok and arqs == certos and any('Encaixe não pôde ser avaliado' in l and 'teste_encaixe.py' in l for l in logs))

# ------------------------------------------------------------------ desempate pelo MusicBrainz
g, logs = novo_app(tmp('enc', 'mb'))
f1 = {'rotulo': 'Discogs 1', 'faixas': [{'title': n, 'duration': d + 3} for n, d in zip(NOMES, DUR)], 'enc': {'nota': 1.0}}
f2 = {'rotulo': 'Discogs 2', 'faixas': [{'title': n, 'duration': d} for n, d in zip(NOMES, DUR)], 'enc': {'nota': 1.0}}
mb_ed = [{'tracks': [{'title': n, 'duration_exact': d + 0.3} for n, d in zip(NOMES, DUR)], 'release_id': 'mbx', 'title': 'Full House'}]
g.catalogo.musicbrainz_edicoes = lambda *a, **k: mb_ed
cut_fake = types.SimpleNamespace(artist='Wes', album='Full House')
ordem, _ = g._desempate_musicbrainz([f1, f2], cut_fake, f2['faixas'], sil, sum(DUR), 0)
t('empate no encaixe: o MusicBrainz desempata (fica a edição mais próxima dele)', ordem[0] is f2 and any('Desempate pelo MusicBrainz' in l for l in logs))

# ------------------------------------------------------------------ regressão: os discos do ponta a ponta pelo caminho novo
# Mesmos discos e mesmas durações do e2e.py; o corte pelo caminho novo (com encaixe)
# tem de sair idêntico à referência da 12.1.
ref = json.load(open(os.path.join(TESTES, 'referencia_e2e.json')))
rng2 = np.random.default_rng(11)
def album_e2e(tipo):
    dur = [164, 178, 243, 205, 210, 248, 177, 244]
    partes = []
    for i, d in enumerate(dur):
        if tipo == 'gloria' and i == 1:
            partes.append(musica(3.3, amp=0.006)); partes.append(musica(d - 3.3 - 1))
        else:
            partes.append(musica(d - 1))
        partes.append(fade(musica(1)))
        if i < len(dur) - 1:
            partes.append(silencio(2.0) if tipo != 'vinil' else ruido(2.0, 0.003))
    disc = [{'title': f'Faixa {i + 1}', 'duration': int(round(d + 2 + rng2.uniform(-2, 2)))} for i, d in enumerate(dur)]
    return np.concatenate(partes), disc
import sint
sint.rng = np.random.default_rng(7)            # mesma sequência de ruído do e2e.py
capturados = {}
_ct, _at = main.AlbumCutter.cut_tracks, main.AlbumCutter.add_tags
main.AlbumCutter.cut_tracks = lambda self: capturados.__setitem__('cuts', [dict(c) for c in self.cuts]) or True
main.AlbumCutter.add_tags = lambda self: True
for tipo in ['limpo', 'vinil', 'gloria']:
    xa, disc = album_e2e(tipo)
    a2 = salvar(xa, f'e2e_{tipo}.wav')
    saida = tmp('enc', 'e2e_' + tipo, 'x')[:-2]; os.makedirs(saida, exist_ok=True)
    g, logs = novo_app(saida)
    dd = {'found': True, 'title': 'X', 'artists': ['Y'], 'year': '', 'cover_image': None,
          'tracks': [{'number': i + 1, 'title': f['title'], 'duration': f"{f['duration'] // 60}:{f['duration'] % 60:02d}"} for i, f in enumerate(disc)],
          'discogs_master_id': None, 'discogs_release_id': 1}
    capturados.clear()
    ok = g._process_separation_by_source(a2, 'discogs', dd['tracks'], True, dd, {'duration': len(xa) / SR}, saida)
    cortes = [c['end'] for c in capturados.get('cuts', [])[:-1]]
    r = ref[tipo]['cortes']
    dif = max(abs(a - b) for a, b in zip(cortes, r)) if cortes and len(cortes) == len(r) else 99
    t(f'{tipo}: caminho novo corta idêntico à 12.1 (maior diferença {dif:.2f}s)', ok and dif <= 0.05)
main.AlbumCutter.cut_tracks, main.AlbumCutter.add_tags = _ct, _at
fim()

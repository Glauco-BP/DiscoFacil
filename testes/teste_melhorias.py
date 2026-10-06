"""
12.9 - Corrigir busca em "Precisam de você", pendências do limite do Discogs de
volta à fila, tempos com hora na descrição, medidas do áudio uma vez por álbum,
tags num lugar só (ID3 v2.3, capa), config.json antigo convertido, bitrate
inválido = 80, cabeçalho. Nada aqui usa a rede.
"""
import os, sys, subprocess, time, json, shutil, types
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1400x1000x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
preparar()
import numpy as np
from sint import *
from pathlib import Path


def esperar(root, seg=0.35):
    fim_ = time.time() + seg
    while time.time() < fim_:
        root.update(); time.sleep(0.02)


# ------------------------------------------------------------------ config.json antigo
import config as CFG
pasta = tmp('melhorias', 'cfg', 'x')[:-2]; shutil.rmtree(pasta, ignore_errors=True); os.makedirs(pasta)
arq = os.path.join(pasta, 'config.json')
antigo = {"settings": {"output_directory": "C:/SOM", "min_bitrate_kbps": 100, "auto_process_min_confidence_pct": 20,
                       "audio_quality": "best"},
          "apis": {"discogs_token": "TOKEN-VELHO", "groq_api_key": "GROQ-VELHO", "youtube_api_key": "YT-VELHO",
                   "lastfm_api_key": "LASTFM"},
          "output_directory": "C:/SOM",
          "api_keys": {"groq": "GROQ-NOVO", "discogs_token": "", "google_custom_search": {"api_key": ""}}}
json.dump(antigo, open(arq, 'w'))
c = CFG.ConfigManager(arq)
salvo = json.load(open(arq))
t('formato antigo convertido: bloco "apis" e pasta repetida saem',
  'apis' not in salvo and 'output_directory' not in salvo['settings'] and salvo['output_directory'] == 'C:/SOM')
t('chave vazia no formato novo é preenchida com a antiga; a que já existia fica',
  c.get('api_keys.discogs_token') == 'TOKEN-VELHO' and c.get('api_keys.groq') == 'GROQ-NOVO'
  and c.get('api_keys.google_custom_search.api_key') == 'YT-VELHO')
t('ajustes do usuário mantidos; o sem uso sai',
  c.get('settings.min_bitrate_kbps') == 100 and c.get('settings.auto_process_min_confidence_pct') == 20
  and 'audio_quality' not in salvo['settings'])
t('original guardado em config.json.antigo', json.load(open(arq + '.antigo')) == antigo)
t('a lista do que mudou não mostra nenhuma chave', c.migracao and not any(
  v in ' '.join(c.migracao) for v in ('TOKEN-VELHO', 'GROQ', 'YT-VELHO', 'LASTFM')))
c2 = CFG.ConfigManager(arq)
t('abrir de novo não converte nada', c2.migracao == [])

# ------------------------------------------------------------------ tempos com hora na descrição
from catalogo import pistas_do_video
import processo_album as PA
p = pistas_do_video({'description': '00:00 Um\n58:10 - Dois\n1:02:15 Três\n1:10:00 | Quatro'})
t(f"descrição com hora ({[x['duration'] for x in p['tracks']]})",
  [x['duration'] for x in p['tracks']] == [0, 3490, 3735, 4200] and [x['title'] for x in p['tracks']] == ['Um', 'Dois', 'Três', 'Quatro'])
f = PA.faixas_com_tempo_da_descricao(p, 4500)
t('...vira durações até o fim do vídeo', f and [x['duration'] for x in f] == [3490, 245, 465, 300])

# ------------------------------------------------------------------ medidas do áudio uma vez por álbum
import main, corte_audio, types
x = np.concatenate([musica(60), silencio(2), musica(70), silencio(2), musica(50)])
wav = salvar(x, 'melhorias_medidas.wav')
decodificacoes = []
_dec = corte_audio.AnaliseDeAudio._decodificar_mono
corte_audio.AnaliseDeAudio._decodificar_mono = lambda self: (decodificacoes.append(1), _dec(self))[1]
meta = {'tracks': [{'number': i + 1, 'title': f'F{i}', 'duration': d} for i, d in enumerate([61, 72, 51])]}
cortes = []
for _ in range(2):          # duas tentativas de corte do mesmo álbum (ex.: capítulos, depois o normal)
    ac = main.AlbumCutter('A', 'B', wav, meta, TMP, log_func=lambda *a, **k: None)
    ok = ac.smart_cut(ac.detect_gaps())
    cortes.append([round(c['start'], 6) for c in ac.cuts])
t(f'áudio decodificado uma vez só em duas tentativas ({len(decodificacoes)}x), mesmos cortes',
  len(decodificacoes) == 1 and cortes[0] == cortes[1] and len(cortes[0]) == 3)
corte_audio.esquecer_medidas()
ac = main.AlbumCutter('A', 'B', wav, meta, TMP, log_func=lambda *a, **k: None); ac.smart_cut(ac.detect_gaps())
t('depois do álbum, a memória é liberada (o próximo decodifica de novo)', len(decodificacoes) == 2)
corte_audio.AnaliseDeAudio._decodificar_mono = _dec

# ------------------------------------------------------------------ tags num lugar só
from mutagen.id3 import ID3
import metadata_manager as MM, saida
d = tmp('melhorias', 'tags', 'x')[:-2]; shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
mp3 = os.path.join(d, '01 - A.mp3'); capa = os.path.join(d, 'cover.jpg')
subprocess.run([FFMPEG, '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'sine=d=2', '-c:a', 'libmp3lame', mp3], check=True)
subprocess.run([FFMPEG, '-loglevel', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=32x32', '-frames:v', '1', capa], check=True)
MM.gravar_tags(mp3, 'A', 'Jay White (3)', 'Disco', 1, 9, ano='1981', artista_album='Marina Sena (2)', genero='Jazz')
saida.embutir_capa(d, Path(capa))
MM.MetadataManager().add_discogs_ids(mp3, master_id=55, release_id=101)
tg = ID3(mp3)
t(f'ID3 v2.3 em todas as etapas (v2.{tg.version[1]})', tg.version[1] == 3)
t('tags, capa e IDs juntos no mesmo arquivo',
  str(tg.get('TPE1')) == 'Jay White' and str(tg.get('TPE2')) == 'Marina Sena' and str(tg.get('TRCK')) == '1/9'
  and str(tg.get('TCON')) == 'Jazz' and len(tg.getall('APIC')) == 1
  and MM.MetadataManager().read_discogs_ids(mp3) == {'master_id': '55', 'release_id': '101'})
saida.embutir_capa(d, Path(capa))
t('embutir a capa de novo não duplica', len(ID3(mp3).getall('APIC')) == 1)

# ------------------------------------------------------------------ 12.10: disco sem durações (Luiz Loy, 1962)
# 12 músicas, nenhuma duração no Discogs nem no MusicBrainz. Duas músicas têm uma
# pausa curta no meio, e os silêncios dão 14 pedaços: a 1ª (pausa aos 72s) e a 9ª
# (pausa curta aos 36s, silêncio mais fraco). Esperado: juntar e nomear pela ordem.
import glob
from falso_discogs import config_falsa
LL = ['Delilah Jones', 'Fala Amor', 'Tu Sabes', 'Sinfonia nº 3', 'Fechei a Porta', 'Escândalo',
      'Aquellos Ojos Verdes', 'Mack The Knife', 'Samba de Uma Nota Só', 'Moonglow', 'Trianon Cha Cha Cha',
      'Você Passou']
DLL = [205, 130, 110, 140, 170, 165, 115, 150, 140, 155, 160, 175]
partes = []
for i, d in enumerate(DLL):
    if i == 0:
        partes += [musica(71), silencio(1.7), musica(d - 72.7 - 1), fade(musica(1))]
    elif i == 8:
        partes += [musica(35), silencio(1.15), musica(d - 36.15 - 1), fade(musica(1))]
    else:
        partes += [musica(d - 1), fade(musica(1))]
    if i < len(DLL) - 1:
        partes.append(silencio(2.0))
ll = salvar(np.concatenate(partes), 'melhorias_luizloy.wav')


def app_sem_janela(saida):
    G = main.FullTracksDownloaderGUI; g = G.__new__(G); logs = []
    g.log = lambda m='': logs.append(str(m)); g._reg = lambda *a: logs.append('REG ' + ' | '.join(map(str, a)))
    g.config = config_falsa(saida); g.metadata_manager = main.MetadataManager()
    g.acervo_index = types.SimpleNamespace(add=lambda *a, **k: None, has=lambda *a: False)
    g.catalogo = types.SimpleNamespace(musicbrainz_edicoes=lambda *a, **k: [], ultimo_motivo_mb='álbum não encontrado',
                                       musicbrainz=lambda *a, **k: None)
    g._notas_corte = {}
    return g, logs


dd_ll = {'title': 'Luiz Loy e Sua Juventude Musical', 'artists': ['Luiz Loy'], 'year': '1962', 'cover_image': None,
         'tracks': [{'number': i + 1, 'title': n, 'duration': '0:00'} for i, n in enumerate(LL)],
         'discogs_master_id': 2734499, 'discogs_release_id': 12837006}
for nome, fonte, cv in (('automático', 'silencio_nomes', False), ('pendência "processar mesmo assim"', 'discogs', True)):
    saida_ll = tmp('melhorias', 'll_' + fonte, 'x')[:-2]; shutil.rmtree(saida_ll, ignore_errors=True); os.makedirs(saida_ll)
    g, logs = app_sem_janela(saida_ll)
    ok = g._process_separation_by_source(ll, fonte, dd_ll['tracks'], True, dd_ll, {'duration': sum(DLL) + 22}, saida_ll,
                                         allow_cross_validation=cv)
    arqs = sorted(glob.glob(os.path.join(saida_ll, '*.mp3')))
    nomes_ok = [os.path.basename(p) for p in arqs] == [f'{i + 1:02d} - {n}.mp3' for i, n in enumerate(LL)]
    durs = [main.duracao_do_arquivo(p) for p in arqs]
    t(f'Luiz Loy ({nome}): 14 pedaços → as 12 músicas, nomes certos pela ordem', ok and nomes_ok)
    t(f'...a 1ª e a 9ª inteiras ({durs[0] and round(durs[0])}s e {durs[8] and round(durs[8])}s)',
      len(durs) == 12 and abs(durs[0] - DLL[0]) < 4 and abs(durs[8] - DLL[8]) < 4)
    t('...marcado como palpite: log, arquivo da rodada e tag', any('palpite' in l for l in logs)
      and any(l.startswith('REG AVISO') and '1+2=Delilah Jones' in l for l in logs)
      and arqs and 'conferir' in str(ID3(arqs[0]).get('TXXX:DISCOFACIL_NOTA')))
    # 12.14: a pausa de 35s dentro do "Samba de Uma Nota Só" já sai no consenso
    # (pedaço < 60s com o nº de músicas conhecido); antes era juntada no palpite
    t('...a pausa de 35s na 9ª sai antes, pela regra dos 60s',
      any('pausa dentro de uma música' in l for l in logs)
      and not any(l.startswith('REG AVISO') and '10+11' in l for l in logs))

# o que NÃO é juntado: pedaço que sobra mas não é curto (pode ser uma faixa de verdade)
import encaixe as ENC
f13 = [{'votos': 3, 'silencio': 2.0}] * 12
t('pedaço sobrando com duração normal: não junta (fica "Track N")',
  ENC.juntar_pedacos_curtos([150] * 13, f13, 12) is None)
t('sobra demais (mais de 1/4 das músicas): não junta', ENC.juntar_pedacos_curtos([150, 20, 150, 20, 150, 20], [{'votos': 3, 'silencio': 2}] * 5, 3) is None)
t('menos pedaços que músicas (duas emendadas): não inventa', ENC.juntar_pedacos_curtos([150] * 10, [{}] * 9, 12) is None)

# ------------------------------------------------------------------ 12.11: Ray Charles "Forever" (2013)
import pontuacao as P
dur14 = [{'title': f'F{i}', 'duration': 210} for i in range(14)]
exato = {'tracks': dur14, 'track_count': 14, 'album_title': 'Forever', 'year': 2013, 'is_compilation': True}
gold = {'tracks': dur14, 'track_count': 14, 'album_title': 'Forever Gold', 'year': 1999, 'is_compilation': True}
det = []
s_ex = P.score_discogs_candidate(exato, 2940, None, 2013, 'Forever', 'Ray Charles')
s_go = P.score_discogs_candidate(gold, 2940, None, 2013, 'Forever', 'Ray Charles', log_func=det.append)
t(f'"Forever" × "Forever Gold": a palavra a mais pesa ({s_ex:.0f} × {s_go:.0f})',
  s_ex > s_go + 20 and 'palavras a mais no título (gold)' in det[0] and 'coletânea de outro ano' in det[0])
t('edição entre parênteses não conta como palavra a mais ("Kind Of Blue (Legacy Edition)")',
  P.palavras_a_mais('Kind of Blue', 'Kind Of Blue (Legacy Edition)', 'Miles Davis') == (1.0, []))
ig = P.avaliar_identificacao(dict(gold), 2940, None, 2013, 'Forever', 'Ray Charles')
t(f"identificação mostra a palavra a mais ({P.texto_identificacao(ig)})", 'a mais no Discogs: gold' in P.texto_identificacao(ig))
t('disco que não é coletânea: ano diferente não pesa (reedição traz o ano original)',
  P.score_discogs_candidate(dict(gold, is_compilation=False, album_title='Forever'), 2940, None, 2013, 'Forever')
  == P.score_discogs_candidate(dict(gold, is_compilation=False, album_title='Forever', year=2013), 2940, None, 2013, 'Forever') - 8)

# a "queda de volume" 30s depois de um silêncio de verdade não vira faixa (o "Track 7" de 34s)
DRC = [190, 175, 200, 185, 170, 195]
pr = []
for i, d in enumerate(DRC):
    if i == 3:
        pr += [musica(30), ruido(0.8, 0.0005), musica(d - 30.8 - 1), fade(musica(1))]   # pausa curta e funda
    else:
        pr += [musica(d - 1), fade(musica(1))]
    if i < len(DRC) - 1:
        pr.append(silencio(2.0))
rc = salvar(np.concatenate(pr), 'melhorias_raycharles.wav')
for rot, faixas in (('cadastro errado COM durações (7 faixas)', [{'title': f'X{i}', 'duration': 160} for i in range(7)]),
                    ('cadastro SEM durações com 7 faixas', [{'title': f'X{i}', 'duration': 0} for i in range(7)])):
    corte_audio.esquecer_medidas()
    ac = main.AlbumCutter('Ray Charles', 'Forever', rc, {'tracks': [dict(f, number=i + 1) for i, f in enumerate(faixas)]},
                          TMP, log_func=lambda *a, **k: None)
    sc = main.SmartCutter(ac.metadata, ac.detect_gaps(), rc, log_func=lambda *a, **k: None)
    cuts = sc.cut_by_cross_validation() or []
    pedacos = [((c['end'] or sum(DRC) + 10) - c['start']) for c in cuts]
    t(f'{rot}: {len(cuts)} pedaços, nenhum de ~30s', len(cuts) == 6 and min(pedacos) > 100)

# pendência: "provavelmente outro disco" quando a maioria das trocas de faixa não cai em silêncio
import processo_album as PA2
for acertos, esperado in ((4, 'outro_disco'), (8, 'falha_corte')):
    g, logs = app_sem_janela(tmp('melhorias', 'outro', 'x')[:-2])
    os.makedirs(tmp('melhorias', 'outro', 'x')[:-2], exist_ok=True)
    pend = []
    g.pending_queue = types.SimpleNamespace(add=lambda **k: pend.append(k))
    g.downloader = types.SimpleNamespace(download_audio=lambda url, pasta, cb=None: shutil.copy(rc, os.path.join(pasta, 'a.wav')) and os.path.join(pasta, 'a.wav'),
                                         last_error=None, last_error_retryable=True)
    g._antecipar_proximo = lambda *a: None
    g._refine_durations_with_musicbrainz = lambda d, *a, **k: d

    def falha(*a, _ac=acertos, **k):
        g._notas_corte = {'encaixe_medido': (_ac, 13)}
        return None
    g._process_separation_by_source = falha
    dd = {'title': 'Forever Gold', 'artists': ['Ray Charles'], 'tracks': [{'number': 1, 'title': 'x', 'duration': '3:00'}],
          'confidence_pct': 100}
    g._download_and_process('https://youtu.be/rc', {'title': 'Ray Charles - Forever - 2013', 'duration': 1200},
                            'Ray Charles', 'Forever Gold', '1999', 'discogs', dd['tracks'], True, dd)
    t(f'{acertos}/13 trocas num silêncio → pendência "{esperado}"', pend and pend[-1]['kind'] == esperado
      and (esperado != 'outro_disco' or 'Corrigir busca' in pend[-1]['reason']))
# a edição certa estava na busca: o áudio a reconhece (Ray Charles "Forever" 2013, sem a última faixa no vídeo)
DF = [256, 222, 191, 222, 254, 249, 248, 305, 269, 297, 243, 215]          # "Forever" (2013), faixas 1-12
ff = []
for i, d in enumerate(DF):
    ff += [musica(d - 1), fade(musica(1))]
    if i < len(DF) - 1:
        ff.append(silencio(2.0))
rcf = salvar(np.concatenate(ff), 'melhorias_forever.wav')
tot_f = sum(DF) + 2 * 11
NF = [f'Forever {i + 1}' for i in range(13)]
forever = {'title': 'Forever', 'artists': ['Ray Charles'], 'year': 2013, 'master_id': 999381, 'release_id': 5906803,
           'cover_image': None, 'tracks': [{'title': n, 'duration': d + 2} for n, d in zip(NF, DF + [293])]}
dg = [261, 377, 158, 174, 165, 159, 168, 157, 147, 138, 138, 152, 307, 252]
gold = {'title': 'Forever Gold', 'artists': ['Ray Charles'], 'year': 1999, 'master_id': 1607085, 'release_id': 14141085,
        'cover_image': None, 'tracks': [{'title': f'Gold {i + 1}', 'duration': d} for i, d in enumerate(dg)]}
for rot, cv in (('automático', False), ('"processar mesmo assim"', True)):
    base_rc = tmp('melhorias', 'rcf_' + str(cv), 'x')[:-2]; shutil.rmtree(base_rc, ignore_errors=True); os.makedirs(base_rc)
    g, logs = app_sem_janela(base_rc)
    pend = []
    g.pending_queue = types.SimpleNamespace(add=lambda **k: pend.append(k))
    g.downloader = types.SimpleNamespace(download_audio=lambda url, pasta, cb=None: shutil.copy(rcf, os.path.join(pasta, 'a.wav')) and os.path.join(pasta, 'a.wav'),
                                         last_error=None, last_error_retryable=True)
    g._antecipar_proximo = lambda *a: None
    g._refine_durations_with_musicbrainz = lambda d, *a, **k: d
    dd = PA2.dados_para_corte(gold, 'Ray Charles', 'Forever', '2013', titulo_buscado='Forever')
    ok = g._download_and_process('https://youtu.be/rcf', {'title': 'Ray Charles - Forever - 2013', 'duration': tot_f},
                                 'Ray Charles', 'Forever Gold', 1999, 'discogs', dd['tracks'], True, dd,
                                 discogs_candidates=[gold, forever], from_pending=cv, allow_cross_validation=cv)
    pastas = [os.path.basename(x) for x in glob.glob(os.path.join(base_rc, 'Ray Charles*'))]
    arqs = sorted(os.path.basename(x) for x in glob.glob(os.path.join(base_rc, 'Ray Charles - Forever (2013)', '*.mp3')))
    t(f'{rot}: reconhece "Forever" (2013) pelo áudio ({pastas})', ok and pastas == ['Ray Charles - Forever (2013)'] and not pend)
    t(f'...12 faixas com os nomes certos ({arqs[:2]}...)', arqs == [f'{i + 1:02d} - {NF[i]}.mp3' for i in range(12)])
    t('...e o log diz que o vídeo não tem a última faixa', any('não tem a(s) última(s) faixa(s) do cadastro: Forever 13' in l for l in logs))
# 12.13: os números de verdade do log (pedaços medidos × "Forever" 2013), com faixas de mesma duração
reais_rc = [254.9, 221.0, 188.5, 220.3, 252.2, 246.7, 245.9, 301.5, 268.1, 293.8, 243.1, 216.0]
cad_rc = [256, 222, 191, 222, 254, 249, 248, 305, 269, 297, 243, 215]
m_rc = ENC.casar_por_duracao(reais_rc, cad_rc)
t(f"faixas de mesma duração (3:42 e 3:42): casa na ordem do disco ({m_rc and m_rc['faixa_de'][:4]})",
  m_rc and m_rc['faixa_de'] == list(range(12)) and not m_rc['fora_de_ordem'])
m_troca = ENC.casar_por_duracao([300, 180, 240], [180, 300, 240])
t('fora de ordem de verdade continua casando pela duração', m_troca and m_troca['faixa_de'] == [1, 0, 2])
import janela_pendentes as JPx
t('"Talvez outro disco" na coluna Motivo', JPx.rotulo_motivo({'kind': 'outro_disco'}) == 'Talvez outro disco')

# ------------------------------------------------------------------ janela: corrigir busca, limite do Discogs, bitrate, cabeçalho
import janela
root, app, main = janela.abrir()
iniciou = []
app._iniciar_trabalhador = lambda: iniciou.append(1)     # o trabalhador de verdade não roda aqui (sem rede)
pq = app.pending_queue
pq.add(kind='baixa_confianca', url='https://youtu.be/m1', video_title='Mauricio Einhorn E Sebastião Tapajós - 1984',
       title_artist='Mauricio Einhorn E Sebastião Tapajós', title_album='Mauricio Einhorn E Sebastião Tapajós',
       confidence_pct=40, reason='Confiança 40%', discogs_data={'tracks': [], 'title': 'Outro'}, candidatas=[{'x': 1}])
pq.add(kind='erro_discogs', url='https://youtu.be/m2', video_title='Disco que pegou o limite', reason='limite')
app.open_pending_queue_manually(); esperar(root, 0.8)
J = app._janela_pendentes
J.tree.selection_set(pq.items[0]['id']); esperar(root)
t('botão "Corrigir busca" com 1 selecionado', str(J.b_corrigir.cget('state')) == 'normal')
cx = J.corrigir_busca(); esperar(root)
t('caixinha abre com os nomes atuais', cx._campos['Artista:'].get() == 'Mauricio Einhorn E Sebastião Tapajós')
janela.foto(root, tmp('melhorias', 'corrigir.png')) if os.environ.get('DF_FOTOS') else None
cx._campos['Artista:'].delete(0, 'end'); cx._campos['Artista:'].insert(0, 'Mauricio Einhorn')
cx._campos['Álbum:'].delete(0, 'end'); cx._campos['Álbum:'].insert(0, 'Mauricio Einhorn & Sebastião Tapajós')
cx._ok(); esperar(root)
it = pq.get(pq.items[0]['id'])
t('nomes novos gravados, o que tinha sido achado antes sai',
  it['title_artist'] == 'Mauricio Einhorn' and it['busca_corrigida'] and it['discogs_data'] is None and 'candidatas' not in it)
fi = app.fila.por_url('https://youtu.be/m1')
t('...e o item foi pra fila com os nomes novos (e a fila é iniciada, como no Enfileirar)', iniciou and fi and fi['tipo'] == 'pendencia'
  and fi['pendencia_item']['title_album'] == 'Mauricio Einhorn & Sebastião Tapajós')
t('vazio não é aceito', J.corrigir_busca('', 'X') is None)

# processar a pendência corrigida: busca refeita com os nomes novos
buscas = []
app.downloader.get_video_info = lambda u: {'title': 'Mauricio Einhorn E Sebastião Tapajós - 1984', 'duration': 2400}
app.catalogo.discogs = lambda art, alb, **k: (buscas.append((art, alb)), [])[1]
app.catalogo.musicbrainz = lambda *a, **k: None
chamada = {}
app._download_and_process = lambda *a, **k: chamada.update(args=a) or True
app._process_pending_video_item(fi['pendencia_item'])
t(f'pendência corrigida busca com os nomes digitados ({buscas})',
  buscas == [('Mauricio Einhorn', 'Mauricio Einhorn & Sebastião Tapajós')] and chamada['args'][3] == 'Mauricio Einhorn & Sebastião Tapajós')

# limite do Discogs: volta sozinho pra fila depois de 10 minutos, até 3 vezes
import fila_trabalho as FT
it2 = pq.items[1]
t('recém-chegado: ainda não volta', app._tentar_de_novo_limite_discogs(reagendar=False) == 0)
it2['added_at'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time() - 700))
iniciou.clear()
n = app._tentar_de_novo_limite_discogs(reagendar=False)
fi2 = app.fila.por_url('https://youtu.be/m2')
t('depois de 10 min volta pra fila (como nova tentativa, antes do canal)', n == 1 and fi2['tipo'] == 'nova_tentativa'
  and fi2['prioridade'] < app.fila.PRIORIDADES['canal'])
t('...sem iniciar a fila sozinho', not iniciou)
t('já na fila: não duplica', app._tentar_de_novo_limite_discogs(reagendar=False) == 0)
fi2['estado'] = 'rejeitado'
app._retentativas_discogs['https://youtu.be/m2'] = (1, time.time() - 700)
t('2ª tentativa depois de mais 10 min', app._tentar_de_novo_limite_discogs(reagendar=False) == 1)
app.fila.por_url('https://youtu.be/m2')['estado'] = 'rejeitado'
app._retentativas_discogs['https://youtu.be/m2'] = (FT.LIMITE_DISCOGS_TENTATIVAS, 0)
t('no máximo 3 vezes por abertura', app._tentar_de_novo_limite_discogs(reagendar=False) == 0)
# o resultado novo substitui a pendência do limite
pq.add(kind='baixa_confianca', url='https://youtu.be/m2', video_title='Disco que pegou o limite',
       confidence_pct=55, reason='Confiança 55%')
t('quando o Discogs responde, a pendência fica com o motivo certo',
  len([i for i in pq.items if i['url'] == 'https://youtu.be/m2']) == 1
  and pq.items[1]['kind'] == 'baixa_confianca' and pq.items[1]['confidence_pct'] == 55)
J.fechar()

# bitrate inválido nas Configurações = 80 (o padrão anunciado)
from janela_config import SettingsWindow
sw = SettingsWindow(root, app.config, app); esperar(root)
sw.min_bitrate_var.set('abc')
import tkinter.messagebox as MB
_info = MB.showinfo; MB.showinfo = lambda *a, **k: None
try:
    sw.save_settings()
finally:
    MB.showinfo = _info
t('bitrate inválido vira o padrão de 80 kbps', app.config.get('settings.min_bitrate_kbps') == 80)

# cabeçalho: na largura mínima, o botão Configurações aparece inteiro
root.geometry('820x650'); esperar(root, 0.6)
dentro = []
for w in root.winfo_children()[0].winfo_children():
    for b in w.winfo_children():
        if 'Configura' in str(b.cget('text') if 'text' in b.keys() else ''):
            dentro.append(b.winfo_rootx() + b.winfo_width() <= root.winfo_rootx() + root.winfo_width()
                          and b.winfo_width() >= b.winfo_reqwidth())
t('cabeçalho: "Configurações" inteiro mesmo na largura mínima', dentro == [True])
fim()

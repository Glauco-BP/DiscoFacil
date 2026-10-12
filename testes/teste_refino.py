"""
12.19 - Refinamento com as correções do editor (casos reais das 43 edições de 05-06/10/2026):
  - "falta 1 faixa": a pausa do fim do vídeo ocupava a vaga de uma fronteira na hora de
    completar com as quedas de volume (Os Cobras, Juarez Araújo, Os Seis em Ponto); e a queda só
    completa um corte dentro de um pedaço comprido demais (Ed Lincoln: pausa no meio de uma música);
  - nome da pasta: uma lista de faixas colada no campo do artista virou um nome de pasta de 400
    letras (WinError 123) e o disco do Antônio Adolfo se perdeu;
  - nomes no ✂ Editar: disco sem Discogs confirmado ficava "Track N" mesmo quando uma lista sugerida
    do próprio vídeo (capítulos, descrição, comentário) tinha o mesmo nº de músicas que os pedaços;
  - pendência que falha de novo (Corrigir busca que não acha, Enfileirar, cortes do editor) sumia
    de "Precisam de você" junto com o áudio guardado (Hermeto Pascoal - Hermeto, duas vezes);
  - a tela do editor abre no alto e cabe numa tela baixa (os botões de baixo ficavam pra fora).
"""
import os, sys, subprocess, time
if not os.environ.get('DISPLAY') and not os.environ.get('DF_SEM_XVFB'):
    os.environ['DF_SEM_XVFB'] = '1'
    r = subprocess.run(['xvfb-run', '-a', '-s', '-screen 0 1280x900x24', sys.executable] + sys.argv)
    sys.exit(r.returncode)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import numpy as np
from sint import *
import main
import saida
import edicao_cortes as EC
from janela_editor import JANELA_FOLGA_VERTICAL as EC_JANELA_FOLGA

quieto = lambda *a, **k: None

# ------------------------------------------------------------------ "falta 1 faixa" (Os Cobras)
# 11 faixas, Discogs com os 11 nomes e sem durações. 8 trocas com pausa de 2 s (o detector de
# silêncio vê), 2 com pausa curta de 0,6 s (só a queda de volume vê) e o vídeo terminando em
# silêncio (o detector acha um "corte" a meio segundo do fim).
NOMES_C = [f'Faixa {k}' for k in range(1, 12)]
DUR_C = [170, 180, 150, 165, 140, 175, 160, 185, 155, 170, 145]
CURTAS = {3, 7}                       # trocas (depois da faixa k, base 0) sem pausa longa
partes = []
for k, d in enumerate(DUR_C):
    partes.append(musica(d))
    if k < len(DUR_C) - 1:
        partes.append(silencio(0.6 if k in CURTAS else 2.0))
partes.append(silencio(1.6))          # fim do vídeo em silêncio
arq_c = salvar(np.concatenate(partes), 'refino_cobras.wav')
sc = main.SmartCutter({'tracks': [{'title': n, 'duration': 0} for n in NOMES_C]}, {}, arq_c, log_func=quieto)
ac = main.AlbumCutter('Os Cobras', 'Os Cobras', arq_c, {'tracks': []}, tmp('refino', 'c'), log_func=quieto)
sc.all_gaps = ac.detect_gaps()
cuts = sc.cut_by_cross_validation()
esperados, acc = [], 0.0
for k, d in enumerate(DUR_C[:-1]):
    acc += d + (0.6 if k in CURTAS else 2.0)
    esperados.append(acc)
achados = [c['end'] for c in (cuts or [])[:-1]]
t(f"Os Cobras: {len(cuts or [])} faixas = 11 do Discogs (a pausa do fim não ocupa a vaga de uma troca)",
  cuts and len(cuts) == 11)
t("...com os nomes do Discogs pela ordem (não 'Track N')", cuts and [c['title'] for c in cuts] == NOMES_C)
t(f"...e cada corte a menos de 3 s da troca de verdade",
  len(achados) == 10 and all(abs(a - e) < 3.0 for a, e in zip(achados, esperados)))

# Ed Lincoln (medidas reais de 12/10): o vídeo tem 11 músicas e o Discogs 12. A queda de volume mais
# funda que sobrava era uma pausa de 0,4 s no meio da 1ª música (1:30) - completar com ela dava 12
# faixas com os nomes trocados dali pra frente. Só vale queda dentro de pedaço comprido demais.
DUR_E = [170, 133, 232, 160, 141, 104, 143, 106, 143, 141, 134]
partes = [musica(90), silencio(0.4), musica(80)]
for d in DUR_E[1:]:
    partes += [silencio(3.0), musica(d)]
partes.append(silencio(1.6))
arq_e = salvar(np.concatenate(partes), 'refino_edlincoln.wav')
sc = main.SmartCutter({'tracks': [{'title': f'Faixa {k}', 'duration': 0} for k in range(1, 13)]}, {}, arq_e,
                      log_func=quieto)
ac = main.AlbumCutter('Ed Lincoln', 'A Volta', arq_e, {'tracks': []}, tmp('refino', 'e'), log_func=quieto)
sc.all_gaps = ac.detect_gaps()
cuts = sc.cut_by_cross_validation()
t(f"Ed Lincoln: {len(cuts or [])} pedaços pra 12 do Discogs - a pausa no meio da 1ª música não vira corte "
  f"(fica 'Track N', em Precisam de você)",
  cuts and len(cuts) == 11 and cuts[0]['title'] != 'Faixa 1' and all(c['end'] is None or c['end'] > 160 for c in cuts[:1]))

# ------------------------------------------------------------------ nome da pasta (WinError 123)
LISTA = ('01 - Eu sei que vou te amar (Tom Jobim/Vinícius de Moraes)\n02 - Paca tatu, cotia não (Nico Assumpção)\n'
         '03 - Ce sa ce sons pas savas (Nico Assumpção/Nelson Faria)\n04 - Cor de Rosa (Nico Assumpção)\n'
         '05 - Los Turcos (Nelson Faria e Lincoln Cheib)\n06 - Sacopã (Nico Assumpção/Nelson Faria)\n'
         '07 - Juliana(Nelson Faria)\n08 - Vera Cruz (Milton Nascimento/Márcio Borges)')
n = saida.nome_da_pasta(LISTA, 'Nó Em Pingo Dágua - João Pernambuco', 1983)
t(f'artista enorme (lista colada): a pasta cabe no limite ({len(n)} letras) e guarda o álbum e o ano',
  len(n) <= saida.LIMITE_NOME_PASTA and '\n' not in n and n.endswith('Nó Em Pingo Dágua - João Pernambuco (1983)'))
n = saida.nome_da_pasta('Ana ' + 'x' * 95 + '.', 'Disco')
t(f'corte do artista não deixa ponto nem espaço antes do " - " (o Windows recusa nome terminado em ponto): {n[-20:]}',
  ' . -' not in n and '. -' not in n and n.endswith(' - Disco'))
t('nome normal não muda', saida.nome_da_pasta('Simone (3)', 'Pedaço: De Mim?', 1980) == 'Simone - Pedaço De Mim (1980)')

# ------------------------------------------------------------------ nomes no ✂ Editar (disco não confirmado)
def edicao_sem_audio(n_pecas, oficiais=None):
    ed = EC.Edicao('nada.wav', oficiais or [], titulo='X - Y')
    ed.duracao = 180.0 * n_pecas
    ed.marcas = [{'pos': 180.0 * k, 'tipo': 'silencio'} for k in range(1, n_pecas)]
    return ed


DESC = [f'Desc {k}' for k in range(1, 13)]
PALP = [f'Palpite {k}' for k in range(1, 13)]
ed = edicao_sem_audio(12)
ed.adicionar_candidatos('palpite do Discogs', PALP)
ed.adicionar_candidatos('descrição do vídeo', DESC)
ed.rotular()
t(f'12 pedaços e a descrição do vídeo com 12 músicas: os nomes vêm dela ({ed.nomes()[0]}, '
  f'fonte: {ed.fonte_dos_nomes()})', ed.nomes() == DESC and ed.fonte_dos_nomes() == 'descrição do vídeo')
ed = edicao_sem_audio(12)
ed.adicionar_candidatos('palpite do Discogs', PALP)
ed.rotular()
t('só o palpite do Discogs com 12: "Track N" (pode ser outro disco com o mesmo nº de músicas), ele fica no duplo clique',
  ed.nomes()[0] == 'Track 1' and ed.fonte_dos_nomes() is None
  and ('palpite do Discogs', 'Palpite 1') in ed.candidatos_da_faixa(0))
ed = edicao_sem_audio(10)
ed.adicionar_candidatos('descrição do vídeo', DESC)
ed.rotular()
t('10 pedaços pra 12 músicas: "Track N" (o nº não bate)', ed.nomes()[0] == 'Track 1' and ed.fonte_dos_nomes() is None)
ed.marcar(1660.0); ed.marcar(1730.0)
t(f'...você marca os 2 cortes que faltavam: os nomes aparecem sozinhos ({ed.nomes()[-1]})',
  len(ed.marcas) == 11 and ed.nomes() == DESC)
ed.marcar(60.0)
t(f'...e acompanham os cortes depois disso ({ed.nomes()[:2]})', ed.nomes()[:2] == ['Desc 1', 'Desc 1 (2)'])
ed = edicao_sem_audio(11, oficiais=[{'title': f'Of {k}', 'duration': 0} for k in range(12)])
ed.adicionar_candidatos('descrição do vídeo', [f'Desc {k}' for k in range(11)])
ed.rotular()
t('Discogs confirmado com 12 e 11 pedaços: a lista do vídeo não toma o lugar dele ("Track N")',
  ed.nomes()[0] == 'Track 1' and ed.fonte_dos_nomes() is None)
ed = edicao_sem_audio(12)
ed.adicionar_candidatos('colados', DESC)
ed.rotular()
t('lista "colados" não preenche sozinha (já vira nome quando você cola)', ed.nomes()[0] == 'Track 1')

# arquivo de correções: nomes comparados com o que aparecia ao salvar
ed = edicao_sem_audio(10)
ed.adicionar_candidatos('descrição do vídeo', DESC)
ed.rotular()
ed.marcar(1660.0); ed.marcar(1730.0)
ed.renomear(0, 'Outro nome')
r = EC.registro_de_correcoes(ed, {'url': 'u'})
t(f"correções: só o nome que você trocou conta como trocado ({[x['faixa'] for x in r['nomes_trocados']]})",
  [x['faixa'] for x in r['nomes_trocados']] == [1] and r['nomes_trocados'][0]['sugerido'] == 'Desc 1')
t(f"...com a fonte dos nomes e quantos nomes automáticos ficaram ({r['fonte_dos_nomes']}, "
  f"{r['nomes_automaticos_mantidos']})", r['fonte_dos_nomes'] == 'descrição do vídeo'
  and r['nomes_automaticos_mantidos'] == 11 and r['nomes_da_abertura'][0] == 'Track 1')

# ------------------------------------------------------------------ pendência que falha de novo volta pra lista
import janela
root, app, _m = janela.abrir()
app._iniciar_trabalhador = lambda: None
pq = app.pending_queue
base_app = app.config.get_output_directory()
url_h = 'https://www.youtube.com/watch?v=HermetoP197'
pq.add(kind='nao_encontrado', url=url_h, video_title='Hermeto Pascoal - Hermeto 1970 - Full Album',
       title_artist='Hermeto Pascoal', title_album='Hermeto', reason='Não encontrado no Discogs')
it_h = next(i for i in pq.items if i['url'] == url_h)
pq.corrigir_busca(it_h['id'], 'Hermeto Pascoal', '1970')
EC.guardar_audio(base_app, url_h, arq_c)


def processar_falhando(item):
    app._notas_corte = {'motivo': 'o disco tem as durações, e cortar só pelas pausas daria "Track N"'}
    return False


app._process_pending_video_item = processar_falhando
app._enfileirar_pendencias([next(i for i in pq.items if i['url'] == url_h)])
app.dependencias._pronto.set()
app.trabalhador_ativo = True
app._trabalhador_da_fila()
for _ in range(10):
    root.update(); time.sleep(0.02)
volta = next((i for i in pq.items if i['url'] == url_h), None)
t(f"Corrigir busca que não deu certo: continua em Precisam de você ({(volta or {}).get('reason', '')[:70]}...)",
  volta is not None and 'Tentou de novo' in volta['reason'] and 'Track N' in volta['reason']
  and volta.get('busca_corrigida') and volta['title_album'] == '1970')
t('...com o áudio guardado pro ✂ Editar', EC.audio_guardado(base_app, url_h) is not None)
app._descarregar_log()
t('...e o log diz que continua lá (nada de "rejeitado de vez")',
  'Continua em Precisam de você' in app.progress_text.get('1.0', 'end')
  and 'rejeitado de vez' not in app.progress_text.get('1.0', 'end'))
app._process_pending_video_item = lambda item: True
app._enfileirar_pendencias([volta])
app.trabalhador_ativo = True
app._trabalhador_da_fila()
t('enfileirada de novo e dessa vez deu certo: sai da lista', not any(i['url'] == url_h for i in pq.items))
# ------------------------------------------------------------------ tela do editor numa tela baixa
# 12.19: numa tela de notebook (768 de altura, com a barra de tarefas) o "Salvar" ficava pra fora
import tkinter as tk
from janela_editor import JanelaEditor
from tocador import TocadorFalso
_alt_real = tk.Misc.winfo_screenheight
tk.Misc.winfo_screenheight = lambda self: 720
ed_t = EC.Edicao(arq_e, [], titulo='Ed Lincoln - A Volta').carregar()
je_t = JanelaEditor(root, ed_t, lambda e: None, tocador=TocadorFalso())
for _ in range(20):
    root.update(); time.sleep(0.02)
tk.Misc.winfo_screenheight = _alt_real
fundo_salvar = je_t.b_salvar.winfo_rooty() + je_t.b_salvar.winfo_height() - je_t.win.winfo_rooty()
t(f'tela de 720 de altura: o editor abre no alto ({je_t.win.winfo_y()}) com {je_t.win.winfo_height()} de altura '
  f'e o "Salvar" dentro da janela ({fundo_salvar})',
  je_t.win.winfo_height() <= 720 - EC_JANELA_FOLGA and je_t.win.winfo_y() <= 40
  and 0 < fundo_salvar <= je_t.win.winfo_height())
je_t.fechar(perguntar=False)
root.destroy()

fim()

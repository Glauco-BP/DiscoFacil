"""
12.7 - Groq só como sugestão: álbum lido de título + descrição (o Discogs confirma),
nome de faixa difícil (a duração confirma), ordem das faixas na descrição (o encaixe
confirma). Limite do plano gratuito, cache, sem chave = nada.
"""
import os, sys, json, types, shutil, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comum import *
import numpy as np
from sint import *
import main, groq_ajuda as GA
from falso_discogs import config_falsa


class Resposta:
    def __init__(s, texto): s.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=texto))]


class GroqFalso:
    """Responde pelo tipo de pergunta; guarda as perguntas."""
    def __init__(s, respostas, erro=None):
        s.respostas = respostas; s.perguntas = []; s.erro = erro
        s.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=s._criar))

    def _criar(s, model, messages, temperature, max_tokens, **extra):
        p = messages[0]['content']; s.perguntas.append(p); s.modelos = getattr(s, 'modelos', []) + [(model, extra)]
        if s.erro:
            raise s.erro
        if model in getattr(s, 'fora_do_ar', ()):
            raise RuntimeError(f"Error code: 404 - {{'error': {{'message': 'The model `{model}` does not exist', "
                               f"'code': 'model_not_found'}}}}")
        for chave, resp in s.respostas.items():
            if chave in p:
                return Resposta(resp)
        return Resposta('{}')


def ajuda(respostas, chave='gsk_x', erro=None):
    falso = GroqFalso(respostas, erro)
    logs = []
    a = GA.AjudaGroq(lambda: chave, log=logs.append, reg=lambda *x: logs.append(' '.join(map(str, x))),
                     fabrica_cliente=lambda ch: falso)
    return a, falso, logs


# ------------------------------------------------------------------ modelo aposentado pelo Groq (12.9)
a, f, logs = ajuda({'ÁLBUM': '{"artist": "Mauricio Einhorn", "album": "Mauricio Einhorn E Sebastião Tapajós", "year": "1984"}'})
f.fora_do_ar = {GA.MODELOS[0]}
r = a.album_do_titulo_e_descricao('Mauricio Einhorn E Sebastião Tapajós - 1984 - Full Album', '')
t(f'modelo fora do ar (404): passa pro próximo na mesma pergunta ({[m for m, _ in f.modelos]})',
  r and r['year'] == '1984' and [m for m, _ in f.modelos] == GA.MODELOS[:2] and any('saiu do ar' in l for l in logs))
a.tracklist_da_descricao('x' * 50)
t('...e as próximas perguntas já vão direto pro que responde', f.modelos[-1][0] == GA.MODELOS[1])
t('gpt-oss: raciocínio curto e escondido (senão a resposta sai vazia)',
  all(e.get('extra_body', {}).get('reasoning_effort') == 'low' for m, e in f.modelos if m.startswith('openai/gpt-oss')))
f.fora_do_ar = set(GA.MODELOS)
a2, f2, logs2 = ajuda({}); f2.fora_do_ar = set(GA.MODELOS)
t('todos fora do ar: não responde, sem travar', a2.escolher_faixa('v', ['a']) is None and len(f2.modelos) == len(GA.MODELOS)
  and any('não respondeu' in l for l in logs2))

# o pedido de verdade (biblioteca groq), interceptado sem rede: modelo e parâmetros no corpo
try:
    import httpx, groq
    corpos = []
    def _responde(req):
        corpos.append(json.loads(req.content))
        return httpx.Response(200, json={'id': 'x', 'object': 'chat.completion', 'created': 0, 'model': 'm',
                                         'choices': [{'index': 0, 'finish_reason': 'stop',
                                                      'message': {'role': 'assistant', 'content': '{"faixa": 1}'}}]})
    real = GA.AjudaGroq(lambda: 'gsk_teste', fabrica_cliente=lambda ch: groq.Groq(
        api_key=ch, http_client=httpx.Client(transport=httpx.MockTransport(_responde))))
    n = real.escolher_faixa('Faixa', ['Faixa'])
    c = corpos[0] if corpos else {}
    t(f"biblioteca groq: pedido com {c.get('model')}, reasoning_effort={c.get('reasoning_effort')}, "
      f"include_reasoning={c.get('include_reasoning')}",
      n == 0 and c.get('model') == GA.MODELOS[0] and c.get('reasoning_effort') == 'low' and c.get('include_reasoning') is False)
except ImportError:
    t('biblioteca groq não instalada aqui (pulado)', True)

# ------------------------------------------------------------------ unidade
a, f, logs = ajuda({'ÁLBUM': '```json\n{"artist": "Wes Montgomery", "album": "Full House", "year": "1962"}\n```'})
r = a.album_do_titulo_e_descricao('Wes Montgomery (Jazz)', 'Gravado ao vivo no Tsubo em 1962, o disco Full House traz...')
t(f'álbum sugerido a partir de título + descrição ({r})', r == {'artist': 'Wes Montgomery', 'album': 'Full House', 'year': '1962'})
a.album_do_titulo_e_descricao('Wes Montgomery (Jazz)', 'Gravado ao vivo no Tsubo em 1962, o disco Full House traz...')
t('a mesma pergunta não é feita duas vezes', len(f.perguntas) == 1)
a, f, logs = ajuda({'ÁLBUM': '{"artist": "Wes Montgomery", "album": "Smokin at the Half Note", "year": ""}'})
t('álbum inventado (não está escrito no título nem na descrição): ignorado',
  a.album_do_titulo_e_descricao('Wes Montgomery (Jazz)', 'Um disco de jazz incrível.') is None)
a, f, logs = ajuda({'Qual faixa': '{"faixa": 2}'})
t('escolher faixa: índice', a.escolher_faixa('SIMONE PARA LENNON', ['Começar De Novo', 'Para Lennon Y McCartney'], 'Simone') == 1)
a, f, logs = ajuda({'Qual faixa': '{"faixa": 0}'})
t('escolher faixa: nenhuma', a.escolher_faixa('x', ['a', 'b']) is None)
a, f, logs = ajuda({'lista de faixas': '{"faixas": ["B", "A"]}'})
t('ordem da descrição', a.tracklist_da_descricao('Lado A: B (3:00), depois A (4:00). Gravado em 1981 no Rio.') == ['B', 'A'])
a, f, logs = ajuda({}, erro=RuntimeError('Error code: 429 - rate_limit_exceeded'))
t('limite do plano gratuito: devolve None', a.escolher_faixa('x', ['a']) is None)
t('...e fica 10 min sem perguntar (avisa uma vez)', not a.disponivel() and a.escolher_faixa('y', ['a']) is None
  and len(f.perguntas) == 1 and sum('limite do plano gratuito' in l for l in logs) == 1)
a, f, logs = ajuda({'ÁLBUM': '{"album": "X"}'}, chave='')
t('sem chave: não pergunta nada', not a.disponivel() and a.album_do_titulo_e_descricao('t', 'X') is None and not f.perguntas)

# ------------------------------------------------------------------ fluxo: álbum que o título não traz
G = main.FullTracksDownloaderGUI
h = G.__new__(G); hlog = []
h.log = lambda m='': hlog.append(str(m)); h._reg = lambda *x: hlog.append('REG ' + ' | '.join(map(str, x)))
out = tmp('groq', 'SOM', 'x')[:-2]; os.makedirs(out, exist_ok=True)
h.config = config_falsa(out); h._ensure_acervo_and_queue = lambda: None
h.downloader = types.SimpleNamespace(get_video_info=lambda u: {'title': 'Wes Montgomery (Jazz)', 'duration': 2400,
    'description': 'Gravado ao vivo no Tsubo, em Berkeley, Full House é um clássico da guitarra.'})
buscas = []
h.catalogo = types.SimpleNamespace(last_error=None,
    discogs=lambda art, alb, **k: (buscas.append((art, alb)), [])[1])
h.pending_queue = types.SimpleNamespace(add=lambda **k: None)
h.AUTO_PROCESS_MIN_CONFIDENCE_PCT = 80; h.stats = {'albums_skipped': 0}
h.groq, fg, _ = ajuda({'ÁLBUM': '{"artist": "Wes Montgomery", "album": "Full House", "year": "1962"}'})
h.process_single_video('https://youtu.be/wes')
t(f'a sugestão do Groq vai pra busca no Discogs ({buscas})', buscas == [('Wes Montgomery', 'Full House')])
t('log diz que é sugestão e que o Discogs confirma', any('Sugestão do Groq' in l and 'Discogs confirmar' in l for l in hlog))
buscas.clear(); hlog.clear()
h.groq = None
h.process_single_video('https://youtu.be/wes')
t(f'sem Groq: segue como antes ({buscas})', buscas == [('Wes Montgomery (Jazz)', 'Wes Montgomery (Jazz)')])

# ------------------------------------------------------------------ fluxo: nome de faixa difícil na playlist
g = G.__new__(G); glog = []
g.log = lambda m='': glog.append(str(m)); g._reg = lambda *x: glog.append('REG ' + ' | '.join(map(str, x)))
pm = {'artist': 'Simone', 'tracks': [{'title': 'Começar De Novo', 'duration': 200},
                                     {'title': 'Nossa Canção', 'duration': 245},
                                     {'title': 'Iolanda', 'duration': 230}]}
g.groq, fg, _ = ajuda({'Qual faixa': '{"faixa": 2}'})
tit, num, ok = g._match_playlist_track('SIMONE - OUR SONG (traducao)', 1, pm, duracao_video=247)
t(f'Groq + duração confirmando: nome oficial ({tit}, faixa {num})', ok and tit == 'Nossa Canção' and num == 2)
tit, num, ok = g._match_playlist_track('SIMONE - OUR SONG (traducao)', 1, pm, duracao_video=400)
t('Groq sugere mas a duração não confirma: fica o título do vídeo', not ok)
tit, num, ok = g._match_playlist_track('SIMONE - OUR SONG (traducao)', 1, pm, duracao_video=None)
t('sem a duração do vídeo: não aceita a sugestão', not ok)
n_antes = len(fg.perguntas)
tit, num, ok = g._match_playlist_track('SIMONE COMEÇAR DE NOVO', 1, pm, duracao_video=200)
t('nome que a comparação normal já casa: o Groq nem é perguntado', ok and tit == 'Começar De Novo' and len(fg.perguntas) == n_antes)

# ------------------------------------------------------------------ fluxo: ordem das faixas na descrição (encaixe confirma)
DUR = [164, 186, 243, 205, 221, 268, 177, 232]
NOMES = ['Um', 'Dois', 'Três', 'Quatro', 'Cinco', 'Seis', 'Sete', 'Oito']
ordem_audio = [0, 4, 6, 3, 1, 5, 2, 7]                      # o vídeo tem outra ordem
x = np.concatenate(sum([[musica(DUR[k] - 1), fade(musica(1))] + ([silencio(2.0)] if i < 7 else [])
                        for i, k in enumerate(ordem_audio)], []))
arq = salvar(x, 'groq_album.wav')


def rodar(ordem_do_video, groq=None, nome='o'):
    saida = tmp('groq', nome, 'x')[:-2]; shutil.rmtree(saida, ignore_errors=True); os.makedirs(saida)
    a = G.__new__(G); logs = []
    a.log = lambda m='': logs.append(str(m)); a._reg = lambda *x: None
    a.config = config_falsa(saida); a.metadata_manager = main.MetadataManager()
    a.acervo_index = types.SimpleNamespace(add=lambda *x, **k: None)
    a.catalogo = types.SimpleNamespace(musicbrainz_edicoes=lambda *x, **k: [], ultimo_motivo_mb='-')
    a.groq = groq; a._notas_corte = {}
    dd = {'found': True, 'title': 'X', 'artists': ['Y'], 'year': '', 'cover_image': None,
          'tracks': [{'number': i + 1, 'title': n, 'duration': f'{d // 60}:{d % 60:02d}'} for i, (n, d) in enumerate(zip(NOMES, DUR))],
          'discogs_master_id': None, 'discogs_release_id': 5, 'ordem_do_video': ordem_do_video,
          'descricao_video': 'Faixas: ' + ', '.join(NOMES[k] for k in ordem_audio)}
    ok = a._process_separation_by_source(arq, 'discogs', dd['tracks'], True, dd, {'duration': len(x) / SR}, saida)
    return ok, sorted(os.path.basename(p) for p in glob.glob(os.path.join(saida, '*.mp3'))), logs


certos = [f'{i + 1:02d} - {NOMES[k]}.mp3' for i, k in enumerate(ordem_audio)]
ok, arqs, logs = rodar([NOMES[k] for k in ordem_audio], nome='desc')
t(f'ordem da descrição (padrões): encaixa e corta com os nomes certos ({arqs[:3]}...)', ok and arqs == certos)
ga, fg2, _ = ajuda({'lista de faixas': json.dumps({'faixas': [NOMES[k] for k in ordem_audio]})})
ok, arqs, logs = rodar(None, groq=ga, nome='groq')
t(f'ordem lida pelo Groq: encaixe confirma, nomes certos ({arqs[:3]}...)', ok and arqs == certos and any('Groq leu 8 faixas' in l for l in logs))
gb, fg3, _ = ajuda({'lista de faixas': json.dumps({'faixas': NOMES[::-1]})})       # Groq "inventa" outra ordem
ok, arqs, logs = rodar(None, groq=gb, nome='errada')
t(f'ordem errada do Groq: o encaixe não confirma e nada sai com nome trocado ({arqs})', not ok and arqs == [])
fim()

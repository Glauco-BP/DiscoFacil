"""
Gravar sozinho o disco que o Discogs não confirmou (12.21: as propostas 1 e 2 do refinamento com
as correções do ✂ Editar).

O disco ia pra "Precisam de você" quando o Discogs não acha, acha com confiança baixa ou acha outro
disco. Antes disso, o programa prepara os cortes como o ✂ Editar prepararia (edicao_cortes) e só
grava sozinho quando passa em TODAS as travas (limites em ajustes.GravarSozinho):

  - todos os cortes sugeridos em pausa clara (silêncio de 1 s ou mais), nenhum estimado;
  - pelo menos 4 pedaços, nenhum com menos de 90 s e nenhum comprido demais (2 músicas juntas?);
  - o artista e o álbum saem do título do vídeo.

Proposta 1: o vídeo traz a lista das músicas (capítulos, descrição ou comentário) com o mesmo nº de
pedaços - e, se a lista tem tempos, cada tempo cai na pausa do seu corte. Grava com esses nomes,
marcados "conferir" nas tags. Proposta 2: o vídeo não traz lista nenhuma - grava com "Track N" e o
disco entra em "Gravados com Track N". O palpite do Discogs nunca dá nome (pode ser outro disco), e
uma lista do vídeo que não bate com os pedaços segura o disco em "Precisam de você".
"""
import re
from typing import Dict, List, Optional

from ajustes import GravarSozinho as A
from edicao_cortes import FONTE_DISCOGS_DAS_TAGS, FONTES_PREFERIDAS

LISTAS_DO_VIDEO = tuple(f for f in FONTES_PREFERIDAS if f != FONTE_DISCOGS_DAS_TAGS)
CAMPO_MAX = 150                    # artista/álbum maior que isso não é um nome
# o que vem no lugar do álbum e não é nome de disco ("Fulano - Full Album", "Fulano - LP"). Um gênero
# ("Bola Sete - Bossa Nova") vale: é o nome que o vídeo dá, e há discos com esses nomes
NAO_E_ALBUM = {'full album', 'album completo', 'completo', 'lp', 'full lp', 'vinyl', 'vinil', 'hq', 'hd',
               'disco completo', 'album', 'disco', 'unknown album', 'unknown artist', 'music', 'musica'}


def _limpo(nomes) -> List[str]:
    return [' '.join(str(n).split()) for n in nomes or [] if str(n or '').strip()]


def _generico(nome) -> bool:
    return not nome or re.fullmatch(r'(?i)(track|faixa)\s*\d+', nome) is not None


def _pausa_do_corte(ed, pos) -> Optional[tuple]:
    """O silêncio (início, fim) em que o corte está (o mais longo, se houver mais de um)."""
    perto = [(a, b) for a, b, _ in ed.silencios if a - A.PAUSA_FOLGA_SEC <= pos <= b + A.PAUSA_FOLGA_SEC]
    return max(perto, key=lambda s: s[1] - s[0]) if perto else None


def _nao(motivo) -> Dict:
    return {'decisao': None, 'motivo': motivo, 'nomes': None, 'fonte': None}


def avaliar_titulo(artista, album) -> Optional[str]:
    """Por que o artista/álbum (tirados do título do vídeo) não servem pra gravar sozinho, ou None."""
    import nomes as N
    artista, album = (artista or '').strip(), (album or '').strip()
    if not artista or not album or N.normalizar_para_comparar(album) in NAO_E_ALBUM \
            or N.normalizar_para_comparar(artista) in NAO_E_ALBUM:
        return "o título do vídeo não traz o artista e o álbum"
    if any(c in x for x in (artista, album) for c in '\r\n') or max(len(artista), len(album)) > CAMPO_MAX:
        return "o artista ou o álbum do título não parece um nome"
    return None


def avaliar(ed, fontes, artista, album) -> Dict:
    """
    `ed`: a edição preparada como no ✂ Editar (edicao_cortes.edicao_sem_discogs); `fontes`: as listas
    do vídeo [(fonte, nomes, tempos ou None)]. Devolve {'decisao': 'P1' | 'P2' | None, 'motivo',
    'nomes' (um por pedaço), 'fonte' (de onde vieram os nomes)}.
    """
    motivo = avaliar_titulo(artista, album)
    if motivo:
        return _nao(motivo)
    pecas = ed.pecas()
    n = len(pecas)
    if n < A.PECAS_MIN:
        return _nao(f"só {n} pedaço(s)")
    for k, m in enumerate(ed.marcas):
        if m['tipo'] != 'silencio':
            return _nao(f"o corte {k + 1}→{k + 2} ({m['pos'] / 60:.1f} min) não está num silêncio claro")
        p = _pausa_do_corte(ed, m['pos'])
        if p is None or p[1] - p[0] < A.PAUSA_CLARA_SEC:
            return _nao(f"o corte {k + 1}→{k + 2} ({m['pos'] / 60:.1f} min) está numa pausa curta")
    durs = [b - a for a, b in pecas]
    curto = min(range(n), key=lambda i: durs[i])
    if durs[curto] < A.PECA_MIN_SEC:
        return _nao(f"o pedaço {curto + 1} tem só {durs[curto]:.0f} s (pode ser um corte a mais)")
    mediana = sorted(durs)[n // 2]
    for i, d in enumerate(durs):
        if d > mediana * A.LONGO_X_MEDIANA and d > mediana + A.LONGO_MAIS_SEC:
            return _nao(f"o pedaço {i + 1} tem {d / 60:.1f} min (a mediana é {mediana / 60:.1f}): "
                        f"podem ser 2 músicas juntas")
    listas = [(f, _limpo(nm), t) for f, nm, t in fontes or []
              if f in LISTAS_DO_VIDEO and len(_limpo(nm)) >= A.LISTA_MIN_NOMES]
    if not listas:
        return {'decisao': 'P2', 'motivo': "cortes em pausas claras, e o vídeo não traz a lista das músicas",
                'nomes': [f'Track {i + 1}' for i in range(n)], 'fonte': None}
    # proposta 1: os nomes que o ✂ Editar mostraria, vindos de uma lista do vídeo
    automaticos = _limpo(ed.nomes_automaticos())
    lista = next(((f, nm, t) for f, nm, t in listas if nm == automaticos), None)
    if lista is None:
        tamanhos = sorted({len(nm) for _, nm, _ in listas})
        return _nao(f"a lista do vídeo tem {'/'.join(map(str, tamanhos))} músicas e há {n} pedaços")
    fonte, nomes_, tempos = lista
    if any(_generico(x) for x in nomes_):
        return _nao(f"a lista do vídeo ({fonte}) não tem os nomes de todas as músicas")
    if tempos:
        if len(tempos) != n:
            return _nao(f"os tempos da lista do vídeo ({fonte}) não são um por música")
        for k, (t, m) in enumerate(zip(list(tempos)[1:], ed.marcas)):
            a, b = _pausa_do_corte(ed, m['pos'])
            if not (a - A.TEMPO_FOLGA_SEC <= float(t) <= b + A.TEMPO_FOLGA_SEC):
                return _nao(f"o tempo da música {k + 2} na lista do vídeo ({float(t) / 60:.1f} min) não cai na "
                            f"pausa do corte ({m['pos'] / 60:.1f} min)")
    return {'decisao': 'P1', 'motivo': f"cortes em pausas claras e os nomes da lista do vídeo ({fonte})",
            'nomes': list(nomes_), 'fonte': fonte}


def texto_dos_cortes(ed, nomes) -> str:
    """Os cortes da edição com estes nomes, no formato #exato (o mesmo do ✂ Editar)."""
    for i, nome in enumerate(nomes):
        ed.nomes_editados[i] = nome
    return ed.texto_tempos()

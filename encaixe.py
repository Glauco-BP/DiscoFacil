"""
Encaixe: "as durações deste cadastro servem pra cortar ESTE áudio?"

Medido FAIXA A FAIXA, depois de detectar os silêncios: para cada fronteira
entre faixas, a duração do cadastro aponta pra um silêncio real a poucos
segundos? A posição esperada parte sempre do corte anterior já confirmado
(se houve), então um erro numa faixa não contamina as seguintes.

Total que bate não basta: no Nico Assumpção (1981) a soma das durações
estava a 1,4% do áudio, mas a ordem das faixas era outra - nenhuma fronteira
caía num silêncio.

Também aqui:
- casar_por_duracao: dado o áudio cortado pelos silêncios, casa cada pedaço
  com uma faixa do cadastro pela duração (mesmo fora de ordem), ou diz que
  não dá (nunca sai nome trocado);
- edicoes_do_mesmo_album: das candidatas que a busca no Discogs já trouxe,
  as que são o mesmo álbum (mesmo master, ou título parecido);
- juntar_pedacos_curtos: disco SEM durações em lugar nenhum - junta os
  pedaços que sobram (os mais curtos, pela fronteira mais fraca) até dar o
  nº de músicas, pra nomear pela ordem (palpite marcado "a conferir").
"""
from typing import Dict, List, Optional, Sequence

from pontuacao import mesmo_disco

JANELA_SEG = 5.0          # "a poucos segundos"
ENCAIXE_BOM = 0.75        # 3 de cada 4 fronteiras num silêncio real
DESEMPATE = 0.05          # diferença de encaixe que conta como empate


def segundos(faixa) -> float:
    """Duração de uma faixa em qualquer formato que circula no programa."""
    if not isinstance(faixa, dict):
        return 0.0
    for k in ('duration_exact', 'duration_seconds'):
        v = faixa.get(k)
        if isinstance(v, (int, float)) and v > 0:
            return float(v)
    v = faixa.get('duration')
    if isinstance(v, (int, float)):
        return float(v) if v > 0 else 0.0
    if isinstance(v, str) and ':' in v:
        try:
            p = [int(x) for x in v.strip().split(':')]
            return float(p[0] * 60 + p[1]) if len(p) == 2 else float(p[0] * 3600 + p[1] * 60 + p[2])
        except Exception:
            return 0.0
    return 0.0


def nota_encaixe(duracoes: Sequence[float], silencios: Sequence[float], total: float = 0.0,
                 inicio: float = 0.0, janela: float = JANELA_SEG) -> Dict:
    """
    duracoes: duração de cada faixa do cadastro (s); silencios: posições de
    corte possíveis (s); total: duração do áudio; inicio: silêncio inicial.

    Devolve {'nota': 0..1, 'acertos': k, 'fronteiras': n, 'sem_duracao': bool,
             'detalhe': [(faixa, esperado, achado|None, erro|None)]}.
    """
    durs = [float(d or 0) for d in duracoes]
    n = max(0, len(durs) - 1)
    if not durs or any(d <= 0 for d in durs):
        return {'nota': 0.0, 'acertos': 0, 'fronteiras': n, 'sem_duracao': True, 'detalhe': []}
    sil = sorted(float(s) for s in silencios)
    pos = float(inicio or 0.0)
    acertos, detalhe, usados = 0, [], set()
    for i in range(n):
        esperado = pos + durs[i]
        melhor, erro = None, None
        for j, s in enumerate(sil):
            if j in usados:
                continue
            e = abs(s - esperado)
            if e <= janela and (erro is None or e < erro):
                melhor, erro, jm = s, e, j
        if melhor is not None:
            acertos += 1
            usados.add(jm)
            pos = melhor
        else:
            pos = esperado
        detalhe.append((i + 1, esperado, melhor, erro))
    nota = (acertos / n) if n else 1.0
    return {'nota': nota, 'acertos': acertos, 'fronteiras': n, 'sem_duracao': False, 'detalhe': detalhe}


def texto_encaixe(enc: Dict) -> str:
    """Resumo legível de uma nota_encaixe (ex.: "7/9 fronteiras num silêncio (78%)")."""
    if enc.get('sem_duracao'):
        return 'sem durações'
    return f"{enc['acertos']}/{enc['fronteiras']} fronteiras num silêncio ({enc['nota'] * 100:.0f}%)"


# ----------------------------------------------------------------- casamento por duração
def _hungaro(custo: List[List[float]]) -> List[int]:
    """Atribuição de custo mínimo (matriz quadrada). Devolve col[i] de cada linha i."""
    n = len(custo)
    INF = float('inf')
    u = [0.0] * (n + 1); v = [0.0] * (n + 1); p = [0] * (n + 1); way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i; j0 = 0
        minv = [INF] * (n + 1); usado = [False] * (n + 1)
        while True:
            usado[j0] = True
            i0 = p[j0]; delta = INF; j1 = 0
            for j in range(1, n + 1):
                if not usado[j]:
                    cur = custo[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur; way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]; j1 = j
            for j in range(n + 1):
                if usado[j]:
                    u[p[j]] += delta; v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
            if j0 == 0:
                break
    col = [0] * n
    for j in range(1, n + 1):
        if p[j]:
            col[p[j] - 1] = j - 1
    return col


def tolerancia_duracao(d: float) -> float:
    """Diferença aceita entre pedaço real e faixa do cadastro: 4s ou 3%, o maior."""
    return max(4.0, 0.03 * d)


def casar_por_duracao(reais: Sequence[float], cadastro: Sequence[float]) -> Optional[Dict]:
    """
    Casa cada pedaço REAL (na ordem do áudio) com uma faixa do cadastro pela
    duração, mesmo fora de ordem. Só aceita se o número for igual e TODO par
    ficar dentro da tolerância (4s ou 3%) - nunca sai nome trocado.
    Devolve {'faixa_de': [índice no cadastro para cada pedaço], 'pior_erro': s,
             'fora_de_ordem': bool} ou None.
    """
    if not reais or len(reais) != len(cadastro) or any((c or 0) <= 0 for c in cadastro):
        return None
    n = len(reais)
    # Desempate pela ordem do cadastro: com duas faixas de mesma duração
    # (Ray Charles "Forever": 3:42 e 3:42), o pedaço 2 fica com a faixa 2. Sem
    # isso a escolha era arbitrária e a conferência abaixo recusava o disco.
    custo = [[abs(r - c) + 1e-3 * abs(i - j) for j, c in enumerate(cadastro)] for i, r in enumerate(reais)]
    col = _hungaro(custo)
    pior = 0.0
    for i, j in enumerate(col):
        e = abs(reais[i] - cadastro[j])
        if e > tolerancia_duracao(cadastro[j]):
            return None
        pior = max(pior, e)
    # ambiguidade: duas faixas de durações quase iguais que caberiam trocadas
    # podem sair com o nome errado.
    for a in range(n):
        for b in range(a + 1, n):
            ja, jb = col[a], col[b]
            if (abs(reais[a] - cadastro[jb]) <= tolerancia_duracao(cadastro[jb]) and
                    abs(reais[b] - cadastro[ja]) <= tolerancia_duracao(cadastro[ja]) and
                    abs(cadastro[ja] - cadastro[jb]) < 2.0 and ja != jb):
                # só aceita se a ordem do cadastro se mantém entre os dois
                if (ja < jb) != (a < b):
                    return None
    return {'faixa_de': col, 'pior_erro': pior, 'fora_de_ordem': col != sorted(col)}


# ----------------------------------------------------------------- disco sem durações
PALPITE_MAX_SOBRA = 3          # no máximo 3 pedaços a mais que as músicas
PALPITE_CURTO = 0.6            # só junta pedaço com menos de 60% da mediana


def juntar_pedacos_curtos(duracoes: Sequence[float], fronteiras: Sequence[Dict], n_alvo: int) -> Optional[List[List[int]]]:
    """
    Pra disco sem nenhuma duração: os pedaços cortados pelos silêncios
    (duracoes, em ordem) e a força de cada fronteira entre eles
    (fronteiras[i] = {'votos', 'silencio'} entre o pedaço i e o i+1).

    Enquanto sobrar pedaço, pega o MAIS CURTO e o junta ao vizinho do lado
    da fronteira mais fraca (menos detectores, silêncio mais curto). Só
    aceita se sobrarem no máximo PALPITE_MAX_SOBRA (e até 1/4 das músicas)
    e se cada pedaço juntado for bem curto (< PALPITE_CURTO da mediana) -
    uma pausa dentro da música, não uma faixa de verdade. No Luiz Loy (1962)
    os 14 pedaços viraram as 12 músicas certas.

    Devolve os grupos de índices (um por música, em ordem) ou None.
    """
    n = len(duracoes)
    if n_alvo <= 0 or n < n_alvo or len(fronteiras) != n - 1:
        return None
    sobra = n - n_alvo
    if sobra > PALPITE_MAX_SOBRA or sobra > max(1, n_alvo // 4):
        return None
    ordenadas = sorted(duracoes)
    mediana = ordenadas[n // 2] if n % 2 else (ordenadas[n // 2 - 1] + ordenadas[n // 2]) / 2.0
    grupos = [[i] for i in range(n)]
    durs = list(duracoes)
    forca = [(int(f.get('votos', 0) or 0), float(f.get('silencio', 0) or 0)) for f in fronteiras]
    while len(grupos) > n_alvo:
        k = min(range(len(grupos)), key=lambda j: durs[j])
        if durs[k] >= PALPITE_CURTO * mediana:
            return None
        if k == 0:
            viz = 0                      # junta com o seguinte (fronteira 0)
        elif k == len(grupos) - 1:
            viz = k - 1
        else:
            viz = k - 1 if forca[k - 1] < forca[k] else k
        grupos[viz:viz + 2] = [grupos[viz] + grupos[viz + 1]]
        durs[viz:viz + 2] = [durs[viz] + durs[viz + 1]]
        del forca[viz]
    return grupos


# ----------------------------------------------------------------- edições do mesmo álbum
def edicoes_do_mesmo_album(escolhida: Dict, candidatas: Sequence[Dict], parecidos=None) -> List[Dict]:
    """
    Das candidatas que a busca no Discogs já trouxe (até 20, com tracklist e
    durações), as que são o mesmo álbum da escolhida (pontuacao.mesmo_disco:
    mesmo master_id, ou título equivalente e artista parecido). Sem repetir a escolhida nem cadastros com as
    mesmas durações.
    """
    tit = escolhida.get('title') or escolhida.get('album_title') or ''
    mid = escolhida.get('master_id') or escolhida.get('discogs_master_id')
    rid = escolhida.get('release_id') or escolhida.get('discogs_release_id')
    vistas = {tuple(round(segundos(t)) for t in (escolhida.get('tracks') or []))}
    saida = []
    for c in candidatas or []:
        if not c or c is escolhida:
            continue
        if rid and c.get('release_id') == rid:
            continue
        mesmo = (mesmo_disco(escolhida, c) if parecidos is None
                 else (mid and c.get('master_id') == mid) or parecidos(tit, c.get('title') or c.get('album_title') or ''))
        if not mesmo:
            continue
        chave = tuple(round(segundos(t)) for t in (c.get('tracks') or []))
        if not chave or chave in vistas:
            continue
        vistas.add(chave)
        saida.append(c)
    return saida

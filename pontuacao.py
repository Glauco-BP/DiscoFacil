"""
Pontuação dos candidatos do Discogs e nota de identificação.

Funções puras (sem rede), usadas por catalogo.py e pelo corte:

- score_discogs_candidate: escolhe a EDIÇÃO entre os candidatos da busca.
- avaliar_identificacao: "é este o álbum?" (0-100). É essa nota que decide
  entre baixar sozinho e mandar pra "Precisam de você" (confiança mínima das
  Configurações). Se as durações servem pra cortar é outra pergunta: ver
  encaixe.py.
- titles_similar / album_title_similarity / palavras_a_mais: comparação de
  títulos (nos dois sentidos: "Forever" não é "Forever Gold").
- mesmo_disco: a regra ÚNICA de "é o mesmo disco?" que vale em todo lugar
  onde o programa troca de edição depois da escolha.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Dict, List, Optional

# Identificação: duração total a até 5% do áudio = coincide; a 15% ou mais = 0.
IDENT_DURACAO_COINCIDE = 0.05
IDENT_DURACAO_ZERA = 0.15
# Títulos das faixas do vídeo (4+) quase todos fora do disco (menos de 25%): a nota não passa de 40
IDENT_TITULOS_MIN_LISTA = 4
IDENT_TITULOS_QUASE_NENHUM = 0.25
IDENT_TETO_TITULOS_NAO_BATEM = 40
# Duração total do cadastro a mais de 60% de distância do vídeo (menos de 40%
# ou mais de 160% dele) é OUTRO disco: o compacto de 5 min com o mesmo nome da
# coletânea de 77 min ("Can't Play A Playgirl"). Só o título não basta.
DURACAO_OUTRO_DISCO = 0.6
PENALIDADE_OUTRO_DISCO = 40.0


def normalize_title(title: str) -> str:
    """Minúsculas, sem parênteses nem pontuação, espaços simples."""
    title = re.sub(r'[()[\]{}]', '', title.lower())
    title = re.sub(r'[^\w\s]', ' ', title)
    return re.sub(r'\s+', ' ', title).strip()


def titles_similar(title1: str, title2: str, threshold: float = 0.8) -> bool:
    """Um título contém o outro, ou são parecidos (SequenceMatcher >= threshold)."""
    norm1 = normalize_title(title1)
    norm2 = normalize_title(title2)
    if norm1 in norm2 or norm2 in norm1:
        return True
    return SequenceMatcher(None, norm1, norm2).ratio() >= threshold


def album_title_similarity(search_title: str, candidate_title: str, artist_name: Optional[str] = None) -> float:
    """
    Fração das palavras do título BUSCADO que aparecem no do candidato
    (0.0 a 1.0). Por palavras, não por letras: "I Get Chet" não parece
    "Chet Baker Sings" só por dividir "Chet". As palavras do nome do artista
    saem antes (o Discogs às vezes põe o artista no título do release).
    """
    norm_search = normalize_title(search_title)
    norm_cand = normalize_title(candidate_title)

    if artist_name:
        for word in normalize_title(artist_name).split():
            if len(word) > 2:
                norm_search = re.sub(rf'\b{re.escape(word)}\b', '', norm_search).strip()
                norm_cand = re.sub(rf'\b{re.escape(word)}\b', '', norm_cand).strip()
        norm_search = re.sub(r'\s+', ' ', norm_search).strip()
        norm_cand = re.sub(r'\s+', ' ', norm_cand).strip()

    stopwords = {'the', 'a', 'an', 'of', 'and', 'e', 'de', 'da', 'do'}
    words_search = set(w for w in norm_search.split() if w not in stopwords)
    words_cand = set(w for w in norm_cand.split() if w not in stopwords)
    if not words_search or not words_cand:
        return 0.5  # neutro: sobrou título curto demais pra comparar
    return len(words_search & words_cand) / len(words_search)


# Palavras de edição que não mudam o álbum ("Kind Of Blue (Legacy Edition)")
PALAVRAS_DE_EDICAO = {'remaster', 'remastered', 'remasterizado', 'deluxe', 'edition', 'edicao', 'edição',
                      'expanded', 'anniversary', 'legacy', 'mono', 'stereo', 'version', 'bonus', 'tracks',
                      'reissue', 'lp', 'cd'}
# Pontos que se perdem quando TODO o título do candidato é palavra a mais
PENALIDADE_PALAVRAS_A_MAIS = 20.0
PENALIDADE_ANO_COLETANEA = 15.0      # coletânea com ano bem diferente do título do vídeo


def palavras_a_mais(search_title: str, candidate_title: str, artist_name: Optional[str] = None):
    """
    O outro lado da comparação de título: palavras do CANDIDATO que não
    estão no título buscado ("Forever Gold" contra "Forever": 'gold').
    Ignora o que está entre parênteses/colchetes, palavras de edição
    (remastered, deluxe...) e o nome do artista.
    Devolve (fração do candidato que está no buscado, [palavras a mais]).
    """
    sem_parenteses = re.sub(r'[\(\[][^)\]]*[\)\]]', ' ', candidate_title or '')
    cand, busca = normalize_title(sem_parenteses).split(), set(normalize_title(search_title or '').split())
    artista = set(w for w in normalize_title(artist_name or '').split() if len(w) > 2)
    stop = {'the', 'a', 'an', 'of', 'and', 'e', 'de', 'da', 'do', 'o', 'os', 'as'}
    sig = [w for w in cand if w not in stop and w not in PALAVRAS_DE_EDICAO and w not in artista]
    if not sig:
        return 1.0, []
    extras = [w for w in sig if w not in busca]
    return 1.0 - len(extras) / len(sig), extras


def score_discogs_candidate(candidate: Dict, reference_duration: Optional[int] = None,
                            reference_track_titles: Optional[List[str]] = None,
                            year_in_title: Optional[int] = None,
                            search_album_title: Optional[str] = None,
                            search_artist_name: Optional[str] = None,
                            reference_track_count: Optional[int] = None,
                            log_func=None) -> float:
    """
    Pontua um release candidato (quanto maior, mais provável de ser o certo).

    Pesos, do mais forte ao mais fraco:
      1. duração total vs áudio: +100 até ±1% (mín. 10s), caindo 1 ponto por
         segundo além disso;
      2. título do álbum: até +55; abaixo de 35% de palavras em comum, -35
         (outro álbum do mesmo artista);
      3. nº de faixas: +45 com a contagem REAL (depois do corte) ou +30 com a
         estimada pelos títulos do vídeo; metade se difere de 1;
      4. títulos das faixas vs os do vídeo: até +40;
      5. desempates: não-coletânea +8, ano do título +8; sem nenhuma pista,
         leve preferência por menos faixas.
    Duração total a mais de 60% de distância do vídeo: -40 (outro disco).
    """
    score = 0.0
    details = []

    if reference_duration and reference_duration > 0:
        candidate_duration = sum(t.get('duration', 0) for t in candidate['tracks'])
        if candidate_duration > 0:
            diff = abs(candidate_duration - reference_duration)
            tolerance = max(10, reference_duration * 0.01)
            if diff <= tolerance:
                score += 100
                details.append(f"duração bate (±{diff:.0f}s): +100")
            else:
                pts = max(0, 100 - (diff - tolerance))
                score += pts
                details.append(f"duração difere {diff:.0f}s: +{pts:.0f}")
            if diff > DURACAO_OUTRO_DISCO * reference_duration:
                score -= PENALIDADE_OUTRO_DISCO
                details.append(f"duração total {100 * candidate_duration / reference_duration:.0f}% do vídeo "
                               f"(outro disco): -{PENALIDADE_OUTRO_DISCO:.0f}")

    if search_album_title and candidate.get('album_title'):
        title_ratio = album_title_similarity(search_album_title, candidate['album_title'], search_artist_name)
        title_pts = 55 * title_ratio
        if title_ratio < 0.35:
            title_pts -= 35
        else:
            # o outro lado: palavras a mais no candidato ("Forever" × "Forever Gold")
            lado, extras = palavras_a_mais(search_album_title, candidate['album_title'], search_artist_name)
            title_pts -= PENALIDADE_PALAVRAS_A_MAIS * (1 - lado)
            if extras:
                details.append(f"palavras a mais no título ({' '.join(extras[:3])}): "
                               f"-{PENALIDADE_PALAVRAS_A_MAIS * (1 - lado):.0f}")
        score += title_pts
        details.append(f"título álbum (overlap {title_ratio:.2f}): {title_pts:+.0f}")

    effective_track_count = reference_track_count if reference_track_count is not None else (
        len(reference_track_titles) if reference_track_titles else None)
    if effective_track_count is not None:
        diff_count = abs(candidate['track_count'] - effective_track_count)
        weight = 45 if reference_track_count is not None else 30
        if diff_count == 0:
            score += weight
            details.append(f"nº faixas bate ({'real' if reference_track_count is not None else 'estimado'}): +{weight}")
        elif diff_count == 1:
            score += weight / 2
            details.append(f"nº faixas quase bate (±1): +{weight / 2:.0f}")

    if reference_track_titles:
        cand_titles = [t['title'] for t in candidate['tracks'] if t.get('title') and t['title'] != '?']
        matched = sum(1 for ref_title in reference_track_titles
                      if any(titles_similar(ref_title, ct, threshold=0.6) for ct in cand_titles))
        pts = 40 * (matched / len(reference_track_titles))
        score += pts
        details.append(f"títulos faixas ({matched}/{len(reference_track_titles)}): +{pts:.0f}")

    if not candidate.get('is_compilation'):
        score += 8
        details.append("não-compilação: +8")
    if year_in_title and candidate.get('year') == year_in_title:
        score += 8
        details.append(f"ano bate ({year_in_title}): +8")
    elif year_in_title and candidate.get('is_compilation'):
        # coletânea: o ano do título é o da coletânea, não o das gravações
        try:
            longe = abs(int(candidate.get('year') or 0) - int(year_in_title)) > 2
        except (TypeError, ValueError):
            longe = False
        if longe and candidate.get('year'):
            score -= PENALIDADE_ANO_COLETANEA
            details.append(f"coletânea de outro ano ({candidate.get('year')} × {year_in_title}): "
                           f"-{PENALIDADE_ANO_COLETANEA:.0f}")
    if (reference_duration is None and reference_track_titles is None
            and not search_album_title and reference_track_count is None):
        fallback_pts = max(0, 5 - candidate['track_count'] / 10)
        score += fallback_pts
        details.append(f"sem pistas, prefere menos faixas: +{fallback_pts:.1f}")

    if log_func:
        title_preview = candidate.get('album_title', '?')[:40]
        log_func(f"      • '{title_preview}' ({candidate['track_count']} faixas, "
                 f"{candidate.get('year', '?')}) = {score:.1f} pts [{'; '.join(details)}]")
    return score


def avaliar_identificacao(candidate: Dict, reference_duration: Optional[float] = None,
                          reference_track_titles: Optional[List[str]] = None,
                          year_in_title=None, search_album_title: Optional[str] = None,
                          search_artist_name: Optional[str] = None) -> Dict:
    """
    Nota de IDENTIFICAÇÃO (0-100) e as partes que a formaram.

    Mesmos pesos da pontuação, com duas regras:
      - duração total a até ±5% do áudio coincide; entre 5% e 15% perde
        pontos aos poucos;
      - cadastro SEM durações (ex.: Os Boêmios) é "sem informação", não
        falha: a nota fica proporcional ao que dá pra medir (os títulos);
      - duração total a mais de 60% de distância do vídeo: -40 (outro disco,
        mesmo com o título igual);
      - o vídeo lista 4+ músicas e menos de 1/4 delas está no disco: no
        máximo 40% (outro disco, mesmo com a duração batendo).
    """
    tracks = candidate.get('tracks') or []
    pts, possivel, partes = 0.0, 0.0, {}
    if search_album_title and (candidate.get('album_title') or candidate.get('title')):
        r = album_title_similarity(search_album_title, candidate.get('album_title') or candidate.get('title'),
                                   search_artist_name)
        pts += 55 * r - (35 if r < 0.35 else 0)
        possivel += 55
        partes['titulo_album'] = round(r, 2)
        if r >= 0.35:
            lado, extras = palavras_a_mais(search_album_title, candidate.get('album_title') or candidate.get('title'),
                                           search_artist_name)
            pts -= PENALIDADE_PALAVRAS_A_MAIS * (1 - lado)
            if extras:
                partes['palavras_a_mais'] = ' '.join(extras[:3])
    if reference_track_titles:
        cand_titles = [t.get('title') for t in tracks if t.get('title') and t.get('title') != '?']
        achou = sum(1 for rt in reference_track_titles
                    if any(titles_similar(rt, ct, threshold=0.6) for ct in cand_titles))
        pts += 40 * achou / len(reference_track_titles)
        possivel += 40
        partes['titulos_faixas'] = f"{achou}/{len(reference_track_titles)}"
        d = abs(len(tracks) - len(reference_track_titles))
        pts += 30 if d == 0 else (15 if d == 1 else 0)
        possivel += 30
        partes['n_faixas'] = 'igual' if d == 0 else f'difere {d}'
    total = sum((t.get('duration') or 0) for t in tracks if isinstance(t.get('duration'), (int, float)))
    tem_todas = bool(tracks) and all(isinstance(t.get('duration'), (int, float)) and t.get('duration') > 0
                                     for t in tracks)
    com_duracao = bool(reference_duration and reference_duration > 0 and tem_todas and total > 0)
    if com_duracao:
        dif = abs(total - reference_duration) / float(reference_duration)
        if dif <= IDENT_DURACAO_COINCIDE:
            p = 100.0
        else:
            p = max(0.0, 100.0 * (1 - (dif - IDENT_DURACAO_COINCIDE) / (IDENT_DURACAO_ZERA - IDENT_DURACAO_COINCIDE)))
        pts += p
        possivel += 100
        partes['duracao_total'] = f"{'coincide' if dif <= IDENT_DURACAO_COINCIDE else 'difere'} ({dif * 100:.1f}%)"
        if dif > DURACAO_OUTRO_DISCO:
            pts -= PENALIDADE_OUTRO_DISCO
            partes['duracao_total'] += ' - outro disco'
    else:
        partes['duracao_total'] = 'sem informação'
    if not candidate.get('is_compilation'):
        pts += 8
    possivel += 8
    if year_in_title:
        possivel += 8
        if str(candidate.get('year')) == str(year_in_title):
            pts += 8
    if com_duracao:
        nota = max(0.0, min(100.0, pts))
    else:
        nota = max(0.0, min(100.0, 100.0 * pts / possivel)) if possivel else 0.0
    # o vídeo lista as músicas e quase nenhuma está neste disco: é outro disco, mesmo com a
    # duração batendo ("Milton Banana - 1967": LP de 1973 com 0 de 12 títulos e 100%)
    if reference_track_titles and len(reference_track_titles) >= IDENT_TITULOS_MIN_LISTA:
        if achou / len(reference_track_titles) < IDENT_TITULOS_QUASE_NENHUM:
            nota = min(nota, IDENT_TETO_TITULOS_NAO_BATEM)
            partes['titulos_faixas'] += ' - não batem'
    return {'nota': int(round(nota)), 'partes': partes}


def texto_identificacao(ident: Dict) -> str:
    """'100% (título do álbum 1.00 · ... · duração total coincide (1.4%))' pro log."""
    p = ident.get('partes', {})
    pedacos = []
    if 'titulo_album' in p:
        pedacos.append(f"título do álbum {p['titulo_album']:.2f}"
                       + (f" (a mais no Discogs: {p['palavras_a_mais']})" if p.get('palavras_a_mais') else ''))
    if 'titulos_faixas' in p:
        pedacos.append(f"títulos das faixas {p['titulos_faixas']}")
    if 'n_faixas' in p:
        pedacos.append(f"nº de faixas {p['n_faixas']}")
    pedacos.append(f"duração total {p.get('duracao_total', '?')}")
    return f"{ident.get('nota', 0)}% (" + ' · '.join(pedacos) + ")"


# ------------------------------------------------------------------ mesmo disco
_STOP_TITULO = {'the', 'a', 'an', 'of', 'and', 'e', 'de', 'da', 'do', 'o', 'os', 'as', 'la', 'le', 'el'}
MESMO_TITULO_MIN = 0.75     # palavras em comum / palavras dos dois títulos
# palavras de nome de artista que não identificam ninguém ("Zimbo Trio" ≠ "Tamba Trio")
_STOP_ARTISTA = _STOP_TITULO | {'his', 'her', 'their', 'with', 'com', 'sua', 'seu', 'and', 'y', 'band', 'banda',
                                'trio', 'quartet', 'quarteto', 'quintet', 'quinteto', 'sextet', 'sexteto',
                                'orchestra', 'orquestra', 'orchester', 'conjunto', 'group', 'grupo', 'ensemble',
                                'combo', 'friends', 'amigos', 'big', 'all', 'stars', 'singers', 'coro'}
_VARIOS = {'various', 'varios', 'varius', 'va', 'v a', 'diversos', 'coletanea', 'compilation', 'unknown artist',
           'various artists', 'varios artistas', 'artistas varios', 'diversos artistas'}
_ROMANOS = {'i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'}
_AO_VIVO = {'live', 'vivo', 'concert', 'concerto', 'show'}


def _sem_acento(texto: str) -> str:
    texto = unicodedata.normalize('NFKD', texto or '')
    return ''.join(c for c in texto if not unicodedata.combining(c))


def _palavras_do_titulo(titulo: str) -> set:
    """Palavras que identificam o disco: sem acento, sem parênteses, sem palavras de edição."""
    t = re.sub(r'[\(\[][^)\]]*[\)\]]', ' ', _sem_acento(titulo))
    return {w for w in normalize_title(t).split() if w not in _STOP_TITULO and w not in PALAVRAS_DE_EDICAO}


def _marcas_do_titulo(titulo: str) -> set:
    """
    O que diferencia discos de mesmo nome, INCLUSIVE dentro de parênteses:
    número de volume ("Vol. 2", "II"), "ao vivo"/"live". Anos (19xx/20xx)
    não contam: "(2013 Remaster)" é a mesma gravação.
    """
    palavras = normalize_title(_sem_acento(titulo)).split()
    marcas = set()
    for k, w in enumerate(palavras):
        if w.isdigit() and not re.fullmatch(r'(19|20)\d\d', w):
            marcas.add(str(int(w)))
        elif w in _ROMANOS and (k > 0 and palavras[k - 1] in ('vol', 'volume', 'part', 'parte', 'n', 'no')
                                or k == len(palavras) - 1 and w != 'i' and len(palavras) > 1):
            marcas.add(str(['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x'].index(w) + 1))
        elif w in _AO_VIVO:
            marcas.add('ao vivo')
    return marcas


def titulos_do_mesmo_disco(a: str, b: str) -> bool:
    """
    "Vê" = "Ve"; "Forever" ≠ "Forever Gold"; "Os Cobras" ≠ "Cobras Criadas";
    "Samba e Violão" ≠ "Samba e Violão Vol. 2"; "Vê" ≠ "Vê (Ao Vivo)". As
    palavras de edição (remastered...) e o ano não contam; volume e "ao vivo"
    contam até entre parênteses.
    """
    if _marcas_do_titulo(a) != _marcas_do_titulo(b):
        return False
    pa, pb = _palavras_do_titulo(a), _palavras_do_titulo(b)
    if not pa or not pb:
        return normalize_title(_sem_acento(a)) == normalize_title(_sem_acento(b)) != ''
    return len(pa & pb) / len(pa | pb) >= MESMO_TITULO_MIN


def e_varios_artistas(nome: str) -> bool:
    """
    "VA", "V.A.", "V/A", "Various", "Varius", "Vários", "Vários Artistas",
    "Various Artists", "Diversos": coletânea de vários artistas (no Discogs,
    o artista é "Various").
    """
    n = normalize_title(_sem_acento(nome or '')).strip()
    junto = n.replace(' ', '')
    return (n in _VARIOS or junto in {'va', 'various', 'variousartists', 'variosartistas', 'varios', 'varius',
                                      'diversos', 'diversosartistas', 'artistasvarios'})


_e_varios = e_varios_artistas


def artistas_parecidos(a, b) -> bool:
    """
    Alguma palavra própria do nome em comum (sem acento, 3+ letras, sem
    "trio", "orquestra", "his"...). "Various"/"V.A." só é parecido com
    "Various". Sem artista de um dos lados: não dá pra negar.
    """
    def lista(x):
        return [y for y in (x if isinstance(x, (list, tuple)) else [x or '']) if y]
    la, lb = lista(a), lista(b)
    if not la or not lb:
        return True
    va, vb = any(_e_varios(x) for x in la), any(_e_varios(x) for x in lb)
    if va or vb:
        return va and vb

    def palavras(xs):
        return {w for w in normalize_title(_sem_acento(' '.join(xs))).split()
                if len(w) > 2 and w not in _STOP_ARTISTA}
    pa, pb = palavras(la), palavras(lb)
    return not pa or not pb or bool(pa & pb)


def mesmo_disco(a: Dict, b: Dict) -> bool:
    """
    A e B (candidatos do Discogs, dados do álbum, edições do MusicBrainz) são
    o mesmo disco? Mesmo master do Discogs; masters DIFERENTES = discos
    diferentes (o artista com vários LPs com o nome dele); sem master de um
    dos lados, título equivalente (titulos_do_mesmo_disco) e artista parecido.
    Toda troca de edição passa por aqui: o programa trocou "Vê" por "Aos
    Amigos Tom, Chico e Vinicius" (outro LP do Milton Banana) e "Os Cobras"
    por "Cobras Criadas" (outro artista) só porque as durações encaixavam.
    """
    if not a or not b:
        return False
    ma = a.get('master_id') or a.get('discogs_master_id')
    mb = b.get('master_id') or b.get('discogs_master_id')
    if ma and mb:
        return ma == mb
    ta = a.get('album_title') or a.get('title') or ''
    tb = b.get('album_title') or b.get('title') or ''
    return titulos_do_mesmo_disco(ta, tb) and artistas_parecidos(a.get('artists'), b.get('artists'))

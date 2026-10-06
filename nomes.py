"""
Nomes: limpeza e comparação de textos de artista, álbum e faixa.

- nome_artista_exibicao: tira o " (N)" e o "*" que o Discogs põe no nome do
  artista ("Simone (3)", "Marina*"), pra pastas e tags. O nome completo
  continua só por dentro (busca, master_id/release_id).
- limpar_titulo_de_video / titulos_casam: casar o título de um vídeo de
  playlist com a faixa oficial, entendendo o artista na frente
  ("SIMONE PARA LENNON & McCARTNEY"), títulos bilíngues com "="
  ("Para Lennon Y McCartney = Para Lennon E McCartney") e "&" no lugar de
  "E"/"Y"/"and". Também tira sufixos como "(Audio)".
- titulo_sem_album / album_da_descricao: quando o título do vídeo não traz o
  álbum ("Wes Montgomery (Jazz)"), procura o álbum na descrição.
"""
import re
import unicodedata
from difflib import SequenceMatcher
from typing import List, Optional

# ----------------------------------------------------------------- artista
_NUM_DISCOGS = re.compile(r'\s\(\d+\)(?=\s*(?:$|[,&/;]|\s(?:feat\.?|ft\.?|featuring|with|and|e|y)\s))',
                          re.IGNORECASE)
_ASTERISCO = re.compile(r'\*+(?=\s*(?:$|[,&/;)]|\s))')


def nome_artista_exibicao(nome) -> str:
    """'Simone (3)' -> 'Simone'; 'Marina*' -> 'Marina'; 'A (2), B*' -> 'A, B'."""
    if not nome or not isinstance(nome, str):
        return nome
    s = _NUM_DISCOGS.sub('', nome)
    s = _ASTERISCO.sub('', s)
    s = re.sub(r'\s{2,}', ' ', s).strip()
    return s or nome


def artistas_exibicao(lista) -> List[str]:
    """nome_artista_exibicao aplicado a uma lista (vazios saem)."""
    return [nome_artista_exibicao(a) for a in (lista or []) if a]


# ----------------------------------------------------------------- comparação
def sem_acentos(s: str) -> str:
    """'Começar' -> 'Comecar'."""
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))


_CONJ = re.compile(r'\b(?:and|y|et|und)\b')


def normalizar_para_comparar(s: str) -> str:
    """minúsculas, sem acento, sem pontuação, '&'/'and'/'y'/'et' = 'e'."""
    s = sem_acentos(str(s or '')).lower()
    s = s.replace('&', ' e ').replace('+', ' e ')
    s = re.sub(r"[’'`´]", '', s)
    s = re.sub(r'[^\w\s]', ' ', s)
    s = _CONJ.sub('e', s)
    return re.sub(r'\s+', ' ', s).strip()


# sufixos de vídeo que não fazem parte do nome da música
_RUIDO = [
    r'official\s+(?:music\s+)?(?:audio|video|visualizer|lyric\s+video)', r'music\s+video',
    r'(?:lyric|lyrics)\s+video', r'lyrics?', r'letra', r'audio(?:\s+oficial)?', r'áudio(?:\s+oficial)?',
    r'video(?:\s*clipe)?(?:\s+oficial)?', r'vídeo(?:\s*clipe)?(?:\s+oficial)?', r'clipe(?:\s+oficial)?',
    r'visualizer', r'hd', r'hq', r'4k', r'full\s+song', r'official', r'oficial', r'audio\s+only',
]
_RUIDO_RE = re.compile(r'\s*[\(\[]\s*(?:' + '|'.join(_RUIDO) + r')\s*[\)\]]', re.IGNORECASE)
_RUIDO_FIM = re.compile(r'\s*[-–—|]\s*(?:' + '|'.join(_RUIDO) + r')\s*$', re.IGNORECASE)


def tirar_sufixos_de_video(titulo: str) -> str:
    """'Will You Still Love Me Tomorrow (Audio)' -> 'Will You Still Love Me Tomorrow'."""
    if not titulo:
        return titulo
    s = _RUIDO_RE.sub('', titulo)
    s = _RUIDO_FIM.sub('', s)
    s = re.sub(r'\s{2,}', ' ', s).strip(' -–—|')
    return s or titulo


def _tirar_numeracao(s: str) -> str:
    """'03. Título' / '3 - Título' -> 'Título'."""
    return re.sub(r'^\s*\d{1,2}\s*(?:[.)\-–—:]|\s-\s)\s*', '', s)


def tirar_artista_do_titulo(titulo: str, artista: Optional[str]) -> str:
    """
    'SIMONE PARA LENNON & McCARTNEY' -> 'PARA LENNON & McCARTNEY' (artista Simone)
    'Simone - Começar de Novo' -> 'Começar de Novo'; 'Começar de Novo - Simone' -> 'Começar de Novo'
    Nunca devolve vazio: se sobrar nada, fica o título.
    """
    if not titulo or not artista:
        return titulo
    nomes = {nome_artista_exibicao(a.strip()) for a in re.split(r',|&| e | and ', artista) if a.strip()}
    nomes.add(nome_artista_exibicao(artista.strip()))
    s = titulo.strip()
    for nome in sorted(nomes, key=len, reverse=True):
        if len(nome) < 2:
            continue
        padrao = re.escape(sem_acentos(nome))
        alvo = sem_acentos(s)
        m = re.match(r'^\s*' + padrao + r'\s*(?:[-–—:~|]\s*|\s+)', alvo, re.IGNORECASE)
        if m and len(alvo) > m.end():
            s = s[m.end():].strip()
            break
        m = re.search(r'\s*[-–—~|]\s*' + padrao + r'\s*$', alvo, re.IGNORECASE)
        if m and m.start() > 0:
            s = s[:m.start()].strip()
            break
    return s or titulo


def limpar_titulo_de_video(titulo: str, artista: Optional[str] = None) -> str:
    """Numeração, sufixos de vídeo e o nome do artista saem."""
    s = tirar_sufixos_de_video(titulo or '')
    s = _tirar_numeracao(s)
    s = tirar_artista_do_titulo(s, artista)
    s = _tirar_numeracao(s)
    return s.strip() or (titulo or '')


def variantes_titulo_oficial(oficial: str) -> List[str]:
    """'A = B' (bilíngue) -> ['A = B', 'A', 'B']."""
    v = [oficial]
    if '=' in (oficial or ''):
        v += [p.strip() for p in oficial.split('=') if p.strip()]
    return v


def _parecidos(a: str, b: str, limiar=0.8) -> bool:
    """Textos já normalizados: iguais, um contém o outro (palavra inteira, 4+ letras) ou similaridade >= limiar."""
    if not a or not b:
        return False
    if a == b:
        return True
    # contido só como palavra inteira e não curto demais
    menor, maior = (a, b) if len(a) <= len(b) else (b, a)
    if len(menor) >= 4 and re.search(r'(?:^|\s)' + re.escape(menor) + r'(?:\s|$)', maior):
        return True
    return SequenceMatcher(None, a, b).ratio() >= limiar


def titulos_casam(titulo_video: str, oficial: str, artista: Optional[str] = None) -> bool:
    """O vídeo é esta faixa? (artista na frente, '=', '&', acentos e sufixos entendidos)"""
    if not titulo_video or not oficial:
        return False
    videos = {normalizar_para_comparar(x) for x in
              (titulo_video, tirar_sufixos_de_video(titulo_video), limpar_titulo_de_video(titulo_video, artista))}
    oficiais = {normalizar_para_comparar(x) for x in variantes_titulo_oficial(oficial)}
    return any(_parecidos(v, o) for v in videos if v for o in oficiais if o)


# ----------------------------------------------------------------- álbum na descrição
_GENERICOS = {
    'full album', 'album completo', 'completo', 'jazz', 'bossa nova', 'mpb', 'samba', 'soul', 'blues',
    'funk', 'rock', 'pop', 'music', 'musica', 'lp', 'vinyl', 'vinil', 'hq', 'hd', 'disco completo',
    'full lp', 'album', 'disco', 'unknown album', 'instrumental', 'classical', 'classica', 'reggae',
    'forro', 'sertanejo', 'choro', 'gospel', 'r b', 'rnb', 'hip hop', 'rap', 'country', 'latin', 'salsa',
}


def tirar_parenteses_genericos(s: str) -> str:
    """'Wes Montgomery (Jazz)' -> 'Wes Montgomery'."""
    def _troca(m):
        dentro = normalizar_para_comparar(m.group(1))
        return '' if dentro in _GENERICOS or re.fullmatch(r'\d{4}', dentro or '') else m.group(0)
    return re.sub(r'\s*[\(\[]([^\)\]]{1,30})[\)\]]', _troca, s or '').strip()


def titulo_sem_album(artista: str, album: str) -> bool:
    """O título do vídeo não trouxe o nome do álbum?"""
    a = normalizar_para_comparar(tirar_parenteses_genericos(artista or ''))
    b = normalizar_para_comparar(tirar_parenteses_genericos(album or ''))
    if not b or b in _GENERICOS:
        return True
    return a == b


def album_da_descricao(descricao: str, artista: Optional[str] = None) -> Optional[str]:
    """
    Procura o nome do álbum na descrição do vídeo. Devolve None se não achar
    nada confiável. Ordem: rótulo explícito ("Álbum: X"), "Artista - Álbum"
    numa linha, 'do álbum "X"', '"X" (1962)'.
    """
    if not descricao:
        return None
    linhas = [l.strip() for l in descricao.splitlines() if l.strip()][:40]
    art = normalizar_para_comparar(nome_artista_exibicao(tirar_parenteses_genericos(artista or '')))

    def plausivel(x):
        if not x:
            return None
        x = re.sub(r'\s*[\(\[]\s*(?:19|20)\d{2}\s*[\)\]]\s*$', '', x).strip(' "“”\'-–—:')
        x = tirar_sufixos_de_video(x)
        x = re.sub(r'\s*[-–—(]?\s*(?:full\s+album|álbum\s+completo|album\s+completo)\)?\s*$', '', x,
                   flags=re.IGNORECASE).strip(' -–—')
        n = normalizar_para_comparar(x)
        if not (2 <= len(x) <= 80) or 'http' in x.lower() or '@' in x or '#' in x[:1]:
            return None
        if n in _GENERICOS or (art and n == art):
            return None
        return x

    # 1. rótulo explícito
    for l in linhas:
        m = re.match(r'^(?:album|álbum|lp|disco|record|title|título|titulo)\s*[:：\-–—]\s*(.+)$', l, re.IGNORECASE)
        if m and plausivel(m.group(1)):
            return plausivel(m.group(1))
    # 2. "Artista - Álbum (ano)" numa linha
    if art:
        for l in linhas:
            m = re.match(r'^(.+?)\s+[-–—]\s+(.+)$', l)
            if m and _parecidos(normalizar_para_comparar(tirar_parenteses_genericos(m.group(1))), art, 0.85):
                if not re.match(r'^\d', m.group(2)):
                    p = plausivel(m.group(2))
                    if p:
                        return p
    # 3. 'do álbum "X"' / 'from the album "X"'
    prefixo = r'(?:from\s+the\s+(?:album|lp)|do\s+(?:álbum|album|disco|lp)|album|álbum)\s*'
    for aspas in (r'[“"]([^”"]{2,80})[”"]', r"'([^']{2,80})'"):
        m = re.search(prefixo + aspas, descricao, re.IGNORECASE)
        if m and plausivel(m.group(1)):
            return plausivel(m.group(1))
    # 4. '"X" (1962)'
    m = re.search(r'[“"]([^”"]{2,80})[”"]\s*\(\s*(?:19|20)\d{2}\s*\)', descricao)
    if m and plausivel(m.group(1)):
        return plausivel(m.group(1))
    return None

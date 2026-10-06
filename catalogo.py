"""
Catálogos de música: Discogs (fonte da identidade do álbum) e MusicBrainz
(segunda opinião sobre durações e edições), mais as pistas que o próprio
vídeo traz (capítulos e tracklist da descrição).

- Catalogo.discogs(): busca e escolhe a edição; devolve a nota de
  identificação (pontuacao.avaliar_identificacao) como 'confidence_pct'.
- Catalogo.musicbrainz() / musicbrainz_edicoes(): uma ou várias edições com
  todas as durações.
- Catalogo.deezer() / itunes(): só as DURAÇÕES de um álbum que não tem
  nenhuma no Discogs nem no MusicBrainz (APIs públicas, sem chave); os nomes
  continuam os do Discogs. Edição com faixas bônus a mais serve.
- pistas_do_video(video_info): faixas dos capítulos ou da descrição, lidas
  do que o yt-dlp já trouxe (sem nova consulta ao YouTube).

Limites dos serviços: Discogs ~60 pedidos/min (intervalo mínimo + espera
automática no 429); MusicBrainz 1 pedido/s e identificação do programa;
Deezer 50 pedidos a cada 5s, iTunes ~20/min (aqui no máximo ~7 por álbum).
"""
import re
import time
import unicodedata
from typing import Dict, List, Optional

import requests

from nomes import artistas_exibicao
from pontuacao import (album_title_similarity, avaliar_identificacao, e_varios_artistas, score_discogs_candidate,
                       texto_identificacao, titles_similar)


class AjustesCatalogo:
    DISCOGS_TIMEOUT_SEG = 15
    DISCOGS_TENTATIVAS_429 = 3        # novas tentativas quando o Discogs responde 429
    DISCOGS_INTERVALO_MIN_SEG = 0.6   # entre pedidos (o limite é ~60/min)
    DISCOGS_ESPERA_PASSO_SEG = 5      # sem 'Retry-After': espera 5s, 10s, 15s...
    DISCOGS_ESPERA_MAX_SEG = 30
    MAX_CANDIDATOS = 20               # cada candidato custa 1 pedido de detalhe
    MAX_FAIXAS = 30                   # acima disso é box set, não um álbum...
    # ...a não ser que o vídeo seja longo o bastante: coletânea de compactos
    # tem 30+ músicas de 2-3 min ("Can't Play A Playgirl": 34 em 77 min)
    SEG_POR_FAIXA_MIN = 100
    MAX_FAIXAS_VIDEO_LONGO = 60
    MB_INTERVALO_SEG = 1.1
    DEEZER_INTERVALO_SEG = 0.15       # limite do serviço: 50 pedidos a cada 5s
    DEEZER_MAX_ALBUNS = 5             # álbuns da busca conferidos faixa a faixa
    DEEZER_TITULO_MIN = 0.6           # fração das palavras do título do álbum que precisa aparecer (vale pro iTunes)
    ITUNES_INTERVALO_SEG = 0.5        # a busca do iTunes aceita ~20 pedidos/min
    ITUNES_PAISES = ('BR', 'US')      # lojas consultadas, nesta ordem
    CASAR_PELA_POSICAO_MAX = 2        # títulos sem par aceitos pela posição (resto todo casado em ordem)


def pistas_do_video(video_info: Dict) -> Optional[Dict]:
    """
    Faixas que o vídeo informa: capítulos (com duração) ou, na falta deles,
    a tracklist da descrição ("00:00 Nome", "1:02:15 Nome", "01 - Nome",
    "1. Nome"). Na descrição, 'duration' é o tempo escrito na linha (início
    ou duração - ver processo_album.faixas_com_tempo_da_descricao).
    Devolve {'tracks': [{'title', 'duration'}], 'source'} ou None.
    """
    chapters = (video_info or {}).get('chapters') or []
    if chapters:
        tracks = []
        for i, ch in enumerate(chapters):
            ini, fim = ch.get('start_time', 0), ch.get('end_time', 0)
            tracks.append({'title': (ch.get('title') or f'Track {i + 1}').strip(),
                           'duration': int(fim - ini) if fim > ini else 0})
        if tracks:
            return {'tracks': tracks, 'source': 'YouTube Chapters'}

    tracks = []
    for line in ((video_info or {}).get('description') or '').split('\n'):
        m = re.search(r'(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\s+(.+)', line)
        if m:
            horas, mins, secs, title = m.groups()
            title = re.sub(r'^[\s\-–—|:.]+', '', title).strip()
            if title:
                tracks.append({'title': title, 'duration': int(horas or 0) * 3600 + int(mins) * 60 + int(secs)})
                continue
        m = re.search(r'^\s*(\d+)\s*[-–—]\s*(.+)', line)
        if m:
            title = re.sub(r'\s*\([^)]+\)\s*$', '', m.group(2)).strip()
            if len(title) > 2:
                tracks.append({'title': title, 'duration': 0})
                continue
        m = re.search(r'^\s*\d+\.\s*(.+)', line)
        if m and len(m.group(1).strip()) > 2:
            tracks.append({'title': m.group(1).strip(), 'duration': 0})
    return {'tracks': tracks, 'source': 'YouTube Description'} if tracks else None


_TEMPO = re.compile(r'(?<![\d:])(?:(\d{1,2}):)?(\d{1,3}):(\d{2})(?:[.,](\d{1,3}))?(?![\d:])')
_NAO_E_FAIXA = re.compile(r'^(total|duration|dura[cç][aã]o|tempo total|side|lado)\b', re.I)


def linhas_com_tempo(texto: str) -> List[tuple]:
    """
    Linhas de um texto livre (comentário do YouTube, lista colada pelo
    usuário) que têm um tempo "M:SS", "MM:SS", "MMM:SS" ou "H:MM:SS" (com
    décimos opcionais, "8:20.3", como o ✂ Editar grava). Vale
    o PRIMEIRO tempo da linha ("0:00 - 3:12 Nome" = início 0:00); os outros
    saem do título. Linhas de total/lado ("Total 40:20", "Side B 20:00") e
    tempos com segundos acima de 59 ficam de fora.
    Devolve [(segundos, título)]: o título sem número de faixa ("01 -", "1.").
    """
    saida = []
    for linha in (texto or '').splitlines():
        m = _TEMPO.search(linha)
        if not m:
            continue
        h, mi, se, fr = m.groups()
        if int(se) > 59 or (h and int(mi) > 59):
            continue
        seg = int(h or 0) * 3600 + int(mi) * 60 + int(se) + (int(fr) / 10 ** len(fr) if fr else 0.0)
        resto = _TEMPO.sub(' ', linha[:m.start()] + ' ' + linha[m.end():])
        resto = re.sub(r'[\(\[]\s*[-–—]?\s*[\)\]]', ' ', resto).strip()
        resto = re.sub(r'^[\s\-–—|:.()\[\]]*\d{1,2}\s*[.)\-–—:]\s+', '', resto)    # "01 - ", "1. "
        resto = re.sub(r'^[\s\-–—|:.()\[\]]+|[\s\-–—|:(\[]+$', '', resto).strip()
        if _NAO_E_FAIXA.match(resto):
            continue
        saida.append((seg, resto))
    return saida


def inicios_de_texto(texto: str, duracao_video: Optional[float] = None) -> Optional[List[Dict]]:
    """
    Lista com tempos -> [{'title', 'start_time'}] (início de cada faixa).
    INÍCIOS: crescentes, o 1º até 30s (ou, com o vídeo de duração conhecida,
    crescentes, antes do fim e com a soma longe do vídeo - aí o 1º começa
    depois de uma introdução, que fica na faixa 1). DURAÇÕES: somadas a
    partir do 0; com o vídeo conhecido, a soma tem de bater com ele (±10%).
    None se não dá pra saber qual dos dois, ou se não parece uma tracklist.
    """
    linhas = linhas_com_tempo(texto)
    if len(linhas) < 2:
        return None
    tempos = [s for s, _ in linhas]
    crescentes = all(b > a for a, b in zip(tempos, tempos[1:]))
    soma = sum(tempos)
    soma_bate = bool(duracao_video) and abs(soma - duracao_video) <= max(20.0, 0.10 * duracao_video)
    if crescentes and tempos[0] <= 30:
        inicios = [0.0] + [float(x) for x in tempos[1:]]
    elif crescentes and duracao_video and not soma_bate and tempos[-1] < duracao_video:
        inicios = [0.0] + [float(x) for x in tempos[1:]]
    elif all(x > 0 for x in tempos) and (soma_bate or not duracao_video) and not (crescentes and tempos[0] <= 30):
        inicios, acc = [], 0.0
        for x in tempos:
            inicios.append(acc)
            acc += x
    else:
        return None
    if duracao_video and inicios[-1] >= duracao_video:
        return None
    return [{'title': t, 'start_time': ini} for (_, t), ini in zip(linhas, inicios)]


def limite_de_faixas(duracao_video: Optional[float] = None) -> int:
    """
    Máximo de faixas de um candidato do Discogs: 30, ou mais se o vídeo
    comporta (1 faixa a cada 100s, até 60). Acima disso é box set.
    """
    limite = AjustesCatalogo.MAX_FAIXAS
    if duracao_video and duracao_video > 0:
        limite = max(limite, min(AjustesCatalogo.MAX_FAIXAS_VIDEO_LONGO,
                                 int(duracao_video // AjustesCatalogo.SEG_POR_FAIXA_MIN)))
    return limite


def _normalizar(texto: str) -> str:
    """Pra busca: sem acentos, minúsculas, sem pontuação."""
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = texto.replace('-', ' ').replace('_', ' ')
    texto = ''.join(c if c.isalnum() or c.isspace() else ' ' for c in texto)
    return ' '.join(texto.split())


def _generos(release: Dict) -> Optional[str]:
    """Estilos (mais específicos) primeiro, depois gêneros, separados por '; ' (tag TCON)."""
    partes = []
    for g in (release.get('styles') or []) + (release.get('genres') or []):
        if g and g not in partes:
            partes.append(g)
    return '; '.join(partes) if partes else None


def _faixas_do_release(release: Dict) -> List[Dict]:
    """Faixas do tracklist, sem os cabeçalhos de seção (nome de cada LP num disco duplo)."""
    faixas = []
    for t in release.get('tracklist', []):
        tipo = (t.get('type_') or '').strip().lower()
        if tipo and tipo != 'track':
            continue
        dur_str = t.get('duration', '')
        dur = 0
        if dur_str and ':' in dur_str:
            p = dur_str.split(':')
            dur = int(p[0]) * 60 + int(p[1])
        title = (t.get('title') or '').strip() or '?'
        faixas.append({'title': title, 'duration': dur})
    return faixas


class Catalogo:
    _mb_ultima_chamada = 0.0       # o MusicBrainz aceita 1 pedido por segundo

    def __init__(self, config: Dict):
        """config: {'discogs_token': ...} (o dicionário pode ser atualizado depois)."""
        self.config = config
        self.session = requests.Session()
        from versao import APP_USER_AGENT
        self.session.headers.update({'User-Agent': APP_USER_AGENT})     # o Discogs pede uma identificação própria
        # 'rate_limited' quando a busca no Discogs não chegou a ser respondida
        # (limite de pedidos OU conexão que caiu - ultimo_erro_discogs diz
        # qual): isso NÃO é "álbum não existe".
        self.last_error = None
        self.ultimo_motivo_mb = None
        self.ultimo_motivo_deezer = None
        self.ultimo_motivo_itunes = None
        self._ultimo_pedido_discogs = 0.0
        self._ultimo_pedido_deezer = 0.0
        self._ultimo_pedido_itunes = 0.0

    # ------------------------------------------------------------------ Discogs
    def _discogs_get(self, url: str, params: dict, timeout: int = AjustesCatalogo.DISCOGS_TIMEOUT_SEG,
                     max_retries: int = AjustesCatalogo.DISCOGS_TENTATIVAS_429, log_func=None):
        """GET no Discogs com intervalo mínimo entre pedidos e nova tentativa no 429."""
        espera = AjustesCatalogo.DISCOGS_INTERVALO_MIN_SEG - (time.time() - self._ultimo_pedido_discogs)
        if espera > 0:
            time.sleep(espera)
        resp = None
        for tentativa in range(max_retries + 1):
            try:
                resp = self.session.get(url, params=params, timeout=timeout)
            finally:
                self._ultimo_pedido_discogs = time.time()
            if resp.status_code != 429 or tentativa >= max_retries:
                return resp
            try:
                espera = float(resp.headers.get('Retry-After'))
            except (TypeError, ValueError):
                espera = AjustesCatalogo.DISCOGS_ESPERA_PASSO_SEG * (tentativa + 1)
            espera = min(espera, AjustesCatalogo.DISCOGS_ESPERA_MAX_SEG)
            if log_func:
                log_func(f"   ⏳ Discogs: limite de requisições atingido (429) - "
                         f"aguardando {espera:.1f}s e tentando de novo ({tentativa + 1}/{max_retries})...")
            time.sleep(espera)
        return resp

    def _buscar_releases(self, artista_norm, album_norm, _log):
        """
        Duas buscas combinadas: a ESTRUTURADA (artist + release_title) vem
        primeiro por ser mais precisa; a de TEXTO LIVRE completa. Sozinha, a
        livre podia encher o limite de candidatos com outro álbum popular do
        mesmo artista. Sem nada nas duas, busca só pelo álbum.
        Devolve a lista de resultados, ou None se o Discogs não respondeu.
        """
        url = "https://api.discogs.com/database/search"
        token = self.config['discogs_token']
        resultados, vistos = [], set()

        def junta(lista):
            for res in lista:
                if res.get('id') not in vistos:
                    resultados.append(res)
                    vistos.add(res.get('id'))

        if album_norm:
            _log(f"   🔍 Discogs: busca estruturada artist='{artista_norm}' release_title='{album_norm}'")
            r = self._discogs_get(url, {'artist': artista_norm, 'release_title': album_norm,
                                        'type': 'release', 'token': token}, timeout=15, log_func=_log)
            if r.status_code == 200:
                junta(r.json().get('results', []))
        _log(f"   🔍 Discogs: busca livre '{artista_norm} {album_norm}'")
        r = self._discogs_get(url, {'q': f'{artista_norm} {album_norm}', 'type': 'release', 'token': token},
                              timeout=15, log_func=_log)
        if r.status_code == 200:
            junta(r.json().get('results', []))
        elif not resultados:
            _log(f"   ❌ Discogs: erro HTTP {r.status_code}")
            if r.status_code == 429:
                self.last_error = 'rate_limited'
            return None
        _log(f"   🔍 Discogs: {len(resultados)} resultado(s)")
        if not resultados and album_norm:
            _log("   🔍 Discogs: tentando busca só pelo álbum...")
            r = self._discogs_get(url, {'q': album_norm, 'type': 'release', 'token': token},
                                  timeout=15, log_func=_log)
            if r.status_code == 200:
                resultados = r.json().get('results', [])
            elif r.status_code == 429:
                self.last_error = 'rate_limited'
        return resultados

    def _ler_candidatos(self, resultados, _log):
        """Detalhe de cada release (até MAX_CANDIDATOS). Candidatos sem duração também valem."""
        candidatos, com_429, sem_conexao = [], 0, 0
        lote = resultados[:AjustesCatalogo.MAX_CANDIDATOS]
        for idx, res in enumerate(lote, 1):
            if sem_conexao >= 2 and not candidatos:
                break                       # a conexão caiu: não adianta pedir os outros agora
            try:
                rid = res['id']
                r = self._discogs_get(f"https://api.discogs.com/releases/{rid}",
                                      {'token': self.config['discogs_token']}, timeout=15, log_func=_log)
                if r.status_code != 200:
                    com_429 += r.status_code == 429
                    continue
                rel = r.json()
                _log(f"      {idx}. ID:{rid} | {res.get('title', 'Unknown')[:50]} | Ano:{rel.get('year', '')}")
                faixas = _faixas_do_release(rel)
                if not faixas:
                    continue
                artistas_discogs = [a.get('name', '').strip() for a in rel.get('artists', []) if a.get('name')]
                imagens = rel.get('images', [])
                candidatos.append({
                    'tracks': faixas,
                    'track_count': len(faixas),
                    'cover_image': imagens[0].get('uri') if imagens else None,
                    'is_compilation': any('Compilation' in f.get('descriptions', [])
                                          for f in rel.get('formats', [])),
                    'year': rel.get('year', ''),
                    'album_title': (rel.get('title') or res.get('title') or 'Unknown').strip(),
                    # " (N)" e "*" saem do nome de exibição; o completo fica por dentro
                    'artists': artistas_exibicao(artistas_discogs),
                    'artists_discogs': artistas_discogs,
                    'genre': _generos(rel),
                    'release_id': rid,
                    'master_id': rel.get('master_id'),
                })
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
                sem_conexao += 1
                continue
            except Exception:
                continue
        if not candidatos and sem_conexao:
            # nenhuma edição lida porque a conexão caiu: não é "álbum não existe"
            self.last_error = 'rate_limited'
            self.ultimo_erro_discogs = 'conexão'
            _log(f"   ⏳ Discogs: a conexão caiu ao ler as edições - tento de novo daqui a pouco")
        if not candidatos and com_429 and com_429 >= len(lote) // 2:
            self.last_error = 'rate_limited'
        return candidatos

    def discogs(self, artist: str, album: str, reference_duration: Optional[int] = None,
                reference_track_titles: Optional[List[str]] = None,
                log_func=None, return_all_candidates: bool = False):
        """
        Busca o álbum no Discogs e escolhe a edição pela pontuação (duração
        total do vídeo, título do álbum, títulos das faixas do vídeo...).

        Devolve o resultado escolhido (dict) ou None. Com
        return_all_candidates=True, devolve TODOS os candidatos ordenados (o
        1º é o escolhido e traz 'confidence_pct' e 'identificacao'); o corte
        usa os outros como "outras edições do mesmo álbum".
        """
        self.last_error = None
        self.ultimo_erro_discogs = None
        vazio = [] if return_all_candidates else None
        _log = log_func or print

        album_limpo = re.sub(r'\b(cd|dvd|disco|album|full|complete|completo|deluxe|remaster)\b', '', album,
                             flags=re.IGNORECASE)
        album_limpo = re.sub(r'\b(19\d{2}|20\d{2})\b', '', album_limpo)
        album_limpo = ' '.join(re.sub(r'[-_]+', ' ', album_limpo).split()).strip()
        if e_varios_artistas(artist):
            artist = 'Various'               # "VA", "V.A.", "Vários Artistas"...: no Discogs é "Various"
        artista_norm, album_norm = _normalizar(artist), _normalizar(album_limpo)
        _log(f"   🔍 Discogs: artista='{artist}' álbum='{album}' → busca '{artista_norm}' / '{album_norm}'")
        m = re.search(r'\b(19\d{2}|20\d{2})\b', album)
        year_in_title = int(m.group(1)) if m else None

        try:
            resultados = self._buscar_releases(artista_norm, album_norm, _log)
            if not resultados:
                return vazio
            candidatos = self._ler_candidatos(resultados, _log)
            limite = limite_de_faixas(reference_duration)
            fora = [c for c in candidatos if c['track_count'] > limite]
            candidatos = [c for c in candidatos if c['track_count'] <= limite]
            if fora:
                _log(f"   ℹ️  {len(fora)} candidato(s) com mais de {limite} faixas fora (box set): "
                     + ', '.join(f"{c['album_title'][:30]} ({c['track_count']})" for c in fora[:3]))
            if not candidatos:
                return vazio
            _log(f"   ✅ {len(candidatos)} candidatos encontrados")

            _log("   📊 Pontuação de cada candidato:")
            pontuados = sorted(((c, score_discogs_candidate(
                c, reference_duration, reference_track_titles, year_in_title,
                search_album_title=album, search_artist_name=artist, log_func=log_func))
                for c in candidatos), key=lambda x: x[1], reverse=True)
            melhor, melhor_score = pontuados[0]

            # Ano: o MAIS ANTIGO entre as edições da mesma obra (master) -
            # "quando o álbum saiu", não o da reedição escolhida.
            if melhor.get('master_id'):
                anos = [c.get('year') for c, _ in pontuados
                        if c.get('master_id') == melhor.get('master_id') and c.get('year')]
                if anos and min(anos) != melhor.get('year'):
                    _log(f"   📅 Ano de lançamento ajustado: {melhor.get('year')} → {min(anos)} "
                         f"(mais antigo entre as edições catalogadas dessa obra no Discogs)")
                    melhor['year'] = min(anos)

            _log(f"   🏆 Selecionado: {melhor['track_count']} faixas, ano {melhor.get('year', 'N/A')}, "
                 f"score={melhor_score:.1f}" + (f" (duração ref: {reference_duration}s)" if reference_duration else ""))
            if len(pontuados) > 1:
                _log(f"      2º colocado: {pontuados[1][0]['track_count']} faixas, score={pontuados[1][1]:.1f}")
            for i, t in enumerate(melhor['tracks'][:5], 1):
                _log(f"      {i}. '{(t['title'] or '(vazio)')[:50]}'")
            if len(melhor['tracks']) > 5:
                _log(f"      ... e mais {len(melhor['tracks']) - 5}")

            try:
                ident = avaliar_identificacao(melhor, reference_duration, reference_track_titles,
                                              year_in_title, album, artist)
                confianca = ident['nota']
                _log(f"   🪪 Identificação: {texto_identificacao(ident)}")
            except Exception as e:
                ident = None
                confianca = max(0, min(100, round(melhor_score)))
                _log(f"   ⚠️  Identificação: não calculada ({str(e)[:60]}) - usando a pontuação")

            def formata(c, s):
                return {'tracks': c['tracks'], 'source': 'Discogs', 'cover_image': c['cover_image'],
                        'year': c.get('year', ''), 'title': c.get('album_title', album),
                        'artists': c.get('artists') or [artist],
                        'artists_discogs': c.get('artists_discogs') or c.get('artists') or [artist],
                        'genre': c.get('genre'), 'score': s,
                        'master_id': c.get('master_id'), 'release_id': c.get('release_id')}

            escolhido = dict(formata(melhor, melhor_score), confidence_pct=confianca, identificacao=ident)
            if return_all_candidates:
                return [escolhido] + [formata(c, s) for c, s in pontuados[1:]]
            return escolhido
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            # a busca não chegou a ser respondida: não é "álbum não existe" - tenta de novo depois
            self.last_error = 'rate_limited'
            self.ultimo_erro_discogs = 'conexão'
            _log(f"   ⏳ Discogs: a conexão caiu ({type(e).__name__}) - a busca não foi respondida; "
                 f"tento de novo daqui a pouco")
            return vazio
        except Exception as e:
            _log(f"   ❌ Discogs: erro - {type(e).__name__}: {str(e)[:100]}")
            return vazio

    # ------------------------------------------------------------------ MusicBrainz
    def _mb_get(self, url, params):
        """GET no MusicBrainz: no máximo 1 pedido/s e o programa se identifica (exigência do serviço)."""
        espera = AjustesCatalogo.MB_INTERVALO_SEG - (time.time() - Catalogo._mb_ultima_chamada)
        if espera > 0:
            time.sleep(espera)
        Catalogo._mb_ultima_chamada = time.time()
        from versao import APP_USER_AGENT
        cabecalho = {'User-Agent': APP_USER_AGENT,
                     'Accept': 'application/json'}
        return self.session.get(url, params=params, headers=cabecalho, timeout=15)

    def _mb_releases(self, artist, album, limite):
        r = self._mb_get("https://musicbrainz.org/ws/2/release", {
            'query': f'artist:"{artist}" AND release:"{album}"', 'fmt': 'json', 'limit': limite})
        if r.status_code != 200:
            self.ultimo_motivo_mb = f"o serviço respondeu {r.status_code}"
            return None
        return [x for x in (r.json().get('releases') or []) if int(x.get('score', 0) or 0) >= 70]

    def _mb_faixas(self, release_id):
        r = self._mb_get(f"https://musicbrainz.org/ws/2/release/{release_id}", {'inc': 'recordings', 'fmt': 'json'})
        if r.status_code != 200:
            return None
        faixas = []
        for disco in r.json().get('media', []):
            for t in disco.get('tracks', []):
                rec = t.get('recording', {}) or {}
                ms = rec.get('length') or t.get('length') or 0
                faixas.append({'title': rec.get('title') or t.get('title') or '?',
                               'duration': int(ms / 1000) if ms else 0,
                               'duration_exact': (ms / 1000.0) if ms else 0.0})
        return faixas

    def musicbrainz(self, artist: str, album: str, n_faixas: Optional[int] = None) -> Optional[Dict]:
        """
        UMA edição do álbum com todas as durações (e, se n_faixas, com esse nº
        de faixas). Testa até 3 edições. Sem resultado, o motivo fica em
        self.ultimo_motivo_mb (pro log).
        """
        self.ultimo_motivo_mb = None
        try:
            releases = self._mb_releases(artist, album, 10)
            if releases is None:
                return None
            if not releases:
                self.ultimo_motivo_mb = "álbum não encontrado"
                return None
            if n_faixas:
                com_n = [x for x in releases if int(x.get('track-count', 0) or 0) == n_faixas]
                if not com_n:
                    self.ultimo_motivo_mb = (f"nenhuma edição com {n_faixas} faixas "
                                             f"({len(releases)} edição(ões) encontrada(s))")
                    return None
                releases = com_n
            for rel in releases[:3]:
                faixas = self._mb_faixas(rel['id'])
                if not faixas or (n_faixas and len(faixas) != n_faixas):
                    continue
                if not all(t['duration_exact'] > 0 for t in faixas):
                    self.ultimo_motivo_mb = "a edição encontrada não tem as durações"
                    continue
                return {'tracks': faixas, 'source': 'MusicBrainz', 'release_id': rel.get('id'),
                        'title': rel.get('title') or album}
            self.ultimo_motivo_mb = self.ultimo_motivo_mb or "não consegui ler as faixas das edições encontradas"
            return None
        except Exception as e:
            self.ultimo_motivo_mb = f"sem conexão com o serviço ({str(e)[:50]})"
            return None

    def musicbrainz_edicoes(self, artist: str, album: str, n_faixas: int, max_edicoes: int = 3) -> List[Dict]:
        """Até max_edicoes edições diferentes, com n_faixas e todas as durações (pro encaixe)."""
        self.ultimo_motivo_mb = None
        saida = []
        try:
            releases = self._mb_releases(artist, album, 15)
            if releases is None:
                return []
            releases = [x for x in releases if int(x.get('track-count', 0) or 0) == int(n_faixas or 0)]
            if not releases:
                self.ultimo_motivo_mb = f"nenhuma edição com {n_faixas} faixas"
                return []
            for rel in releases:
                if len(saida) >= max_edicoes:
                    break
                faixas = self._mb_faixas(rel['id'])
                if not faixas or len(faixas) != n_faixas or not all(t['duration_exact'] > 0 for t in faixas):
                    continue
                chave = tuple(round(t['duration_exact']) for t in faixas)
                if any(tuple(round(t['duration_exact']) for t in e['tracks']) == chave for e in saida):
                    continue
                saida.append({'tracks': faixas, 'source': 'MusicBrainz', 'release_id': rel.get('id'),
                              'title': rel.get('title') or album, 'year': (rel.get('date') or '')[:4]})
            if not saida:
                self.ultimo_motivo_mb = "as edições encontradas não têm todas as durações"
            return saida
        except Exception as e:
            self.ultimo_motivo_mb = f"sem conexão com o serviço ({str(e)[:50]})"
            return saida

    # ------------------------------------------------------------------ durações de fora (Deezer, iTunes)
    @staticmethod
    def _mesmo_artista(artista: str, nome: str) -> bool:
        """Alguma palavra do artista buscado (sem acento, 3+ letras) aparece no artista da loja."""
        palavras = {w for w in _normalizar(artista).split() if len(w) > 2}
        return bool(palavras & set(_normalizar(nome or '').split()))

    @staticmethod
    def _casar_titulos(titulos: List[str], faixas: List[Dict]):
        """
        faixas: [{'title', 'seg'}] da loja. Cada título do cadastro acha a SUA
        faixa (a da mesma posição primeiro, senão qualquer uma ainda livre);
        faixas a mais na loja (bônus) sobram. Título sem par:
          - se a loja tem o MESMO nº de faixas e todos os outros títulos casaram
            exatamente na mesma posição, a faixa que sobrou naquela posição só
            pode ser ela (até CASAR_PELA_POSICAO_MAX títulos, e no máximo 1/4);
          - senão, None: duração no nome errado é pior que nenhuma.
        Devolve (faixas casadas ou None, [títulos do cadastro sem par], [o que a loja tinha no lugar]).
        """
        livres = list(range(len(faixas)))
        escolha = [None] * len(titulos)
        for i, titulo in enumerate(titulos):
            def parecido(j):
                return titles_similar(_normalizar(titulo), _normalizar(faixas[j].get('title') or ''))
            j = i if i in livres and parecido(i) else next((k for k in livres if parecido(k)), None)
            if j is not None:
                livres.remove(j)
                escolha[i] = j
        sem_par = [i for i, j in enumerate(escolha) if j is None]
        na_loja = [faixas[i].get('title') if i < len(faixas) else '?' for i in sem_par]
        if sem_par:
            em_ordem = all(j == i for i, j in enumerate(escolha) if j is not None)
            if (len(faixas) == len(titulos) and em_ordem and all(i in livres for i in sem_par)
                    and len(sem_par) <= min(AjustesCatalogo.CASAR_PELA_POSICAO_MAX, len(titulos) // 4)):
                for i in sem_par:
                    escolha[i] = i
            else:
                return None, [titulos[i] for i in sem_par], na_loja
        saida = []
        for titulo, j in zip(titulos, escolha):
            seg = float(faixas[j].get('seg') or 0)
            if seg <= 0:
                return None, [titulo], [faixas[j].get('title')]
            saida.append({'title': titulo, 'duration': int(round(seg)), 'duration_exact': seg})
        return saida, [titulos[i] for i in sem_par], na_loja

    def _albuns_que_servem(self, achados: List[Dict], artist: str, album: str, n: int) -> List[Dict]:
        """
        Álbuns da loja ({'id', 'title', 'artist', 'n'}) com o título e o
        artista buscados e PELO MENOS n faixas (edição com bônus serve: as
        faixas são casadas pelo título). Os de n exato primeiro.
        """
        primeiro = artist.split(',')[0].strip()
        bons = [a for a in achados
                if album_title_similarity(album, a.get('title') or '', primeiro) >= AjustesCatalogo.DEEZER_TITULO_MIN
                and self._mesmo_artista(artist, a.get('artist'))
                and (not a.get('n') or int(a['n']) >= n)]
        return sorted(bons, key=lambda a: (bool(a.get('n')) and int(a['n']) != n, int(a.get('n') or n)))

    def _duracoes_numa_loja(self, nome, buscar, faixas_do_album, artist, album, titulos):
        """
        Esqueleto comum: buscar() -> [álbuns] ou None (erro); filtra; casa os
        títulos álbum a álbum. Devolve o resultado ou None (motivo -> retorno 2).
        """
        n = len(titulos)
        achados = buscar()
        if achados is None:
            return None, None
        if not achados:
            return None, "álbum não encontrado"
        servem = self._albuns_que_servem(achados, artist, album, n)
        if not servem:
            mesmos = [a for a in achados if self._mesmo_artista(artist, a.get('artist'))]
            if not mesmos:
                return None, "álbum não encontrado"
            return None, (f"nenhuma edição com as {n} faixas ({len(mesmos)} do artista encontrada(s), "
                          f"com {', '.join(str(a.get('n') or '?') for a in mesmos[:4])} faixas)")
        pior = None
        for a in servem[:AjustesCatalogo.DEEZER_MAX_ALBUNS]:
            faixas = faixas_do_album(a)
            if faixas is None:
                return None, None
            if len(faixas) < n:
                continue
            casadas, sem_par, na_loja = self._casar_titulos(titulos, faixas)
            if casadas:
                extra = len(faixas) - n
                return {'tracks': casadas, 'source': nome, 'album_id': a.get('id'), 'title': a.get('title') or album,
                        'faixas_a_mais': extra, 'pela_posicao': list(zip(sem_par, na_loja))}, None
            if pior is None or len(sem_par) < len(pior[0]):
                pior = (sem_par, na_loja, a)
        if pior:
            pares = '; '.join(f"'{d}' (na loja: '{l}')" for d, l in list(zip(pior[0], pior[1]))[:3])
            return None, (f"os nomes das faixas não batem com os do Discogs - no álbum mais parecido "
                          f"({pior[2].get('title')}), sem par: {pares}"
                          + (f" e mais {len(pior[0]) - 3}" if len(pior[0]) > 3 else ""))
        return None, "os nomes das faixas não batem com os do Discogs"

    # --- Deezer
    def _deezer_get(self, caminho: str, params: Optional[dict] = None):
        """GET na API pública do Deezer. Devolve o JSON, ou None (motivo em ultimo_motivo_deezer)."""
        espera = AjustesCatalogo.DEEZER_INTERVALO_SEG - (time.time() - self._ultimo_pedido_deezer)
        if espera > 0:
            time.sleep(espera)
        self._ultimo_pedido_deezer = time.time()
        r = self.session.get(f"https://api.deezer.com/{caminho}", params=params, timeout=15)
        if r.status_code != 200:
            self.ultimo_motivo_deezer = f"o serviço respondeu {r.status_code}"
            return None
        dados = r.json()
        if isinstance(dados, dict) and dados.get('error'):
            # o Deezer responde 200 com {"error": {...}} (ex.: limite de pedidos)
            erro = dados['error']
            self.ultimo_motivo_deezer = f"o serviço recusou ({(erro.get('message') or erro.get('type') or '?')[:50]})"
            return None
        return dados

    def deezer(self, artist: str, album: str, titulos: List[str]) -> Optional[Dict]:
        """
        Durações das faixas `titulos` (nomes do Discogs, na ordem dele) num
        álbum do Deezer com todos os títulos casados (edição com faixas bônus
        a mais serve). Devolve {'tracks': [{'title', 'duration',
        'duration_exact'}] na ordem de `titulos`, 'source', 'album_id',
        'title', 'faixas_a_mais'} ou None (motivo em self.ultimo_motivo_deezer).
        """
        self.ultimo_motivo_deezer = None
        if not titulos or not artist or not album:
            self.ultimo_motivo_deezer = "sem artista, álbum ou faixas pra buscar"
            return None
        primeiro = artist.split(',')[0].strip()

        def buscar():
            achados = []
            for q in (f'artist:"{primeiro}" album:"{album}"', f'{primeiro} {album}'):
                dados = self._deezer_get('search/album', {'q': q, 'limit': 25})
                if dados is None:
                    return None
                achados = [{'id': a.get('id'), 'title': a.get('title'), 'artist': (a.get('artist') or {}).get('name'),
                            'n': a.get('nb_tracks')} for a in (dados.get('data') or [])]
                if self._albuns_que_servem(achados, artist, album, len(titulos)):
                    break
            return achados

        def faixas_do_album(a):
            dados = self._deezer_get(f"album/{a['id']}/tracks", {'limit': 200})
            if dados is None:
                return None
            return [{'title': f.get('title'), 'seg': f.get('duration')} for f in dados.get('data') or []]
        try:
            r, motivo = self._duracoes_numa_loja('Deezer', buscar, faixas_do_album, artist, album, titulos)
            if motivo:
                self.ultimo_motivo_deezer = motivo
            return r
        except Exception as e:
            self.ultimo_motivo_deezer = f"sem conexão com o serviço ({str(e)[:50]})"
            return None

    # --- iTunes (Apple Music): API pública de busca, sem chave
    def _itunes_get(self, caminho: str, params: dict):
        """GET na API de busca do iTunes. Devolve a lista 'results', ou None (motivo em ultimo_motivo_itunes)."""
        espera = AjustesCatalogo.ITUNES_INTERVALO_SEG - (time.time() - self._ultimo_pedido_itunes)
        if espera > 0:
            time.sleep(espera)
        self._ultimo_pedido_itunes = time.time()
        r = self.session.get(f"https://itunes.apple.com/{caminho}", params=params, timeout=15)
        if r.status_code != 200:
            self.ultimo_motivo_itunes = f"o serviço respondeu {r.status_code}"
            return None
        return r.json().get('results') or []

    def itunes(self, artist: str, album: str, titulos: List[str]) -> Optional[Dict]:
        """Como deezer(), na loja do iTunes/Apple Music (Brasil primeiro, depois EUA)."""
        self.ultimo_motivo_itunes = None
        if not titulos or not artist or not album:
            self.ultimo_motivo_itunes = "sem artista, álbum ou faixas pra buscar"
            return None
        primeiro = artist.split(',')[0].strip()
        pais = {}

        def buscar():
            achados = []
            for p in AjustesCatalogo.ITUNES_PAISES:
                res = self._itunes_get('search', {'term': f'{primeiro} {album}', 'entity': 'album',
                                                  'country': p, 'limit': 25})
                if res is None:
                    return None
                novos = [{'id': a.get('collectionId'), 'title': a.get('collectionName'), 'artist': a.get('artistName'),
                          'n': a.get('trackCount')} for a in res if a.get('collectionId')]
                for a in novos:
                    pais.setdefault(a['id'], p)
                achados += novos
                if self._albuns_que_servem(achados, artist, album, len(titulos)):
                    break
            return achados

        def faixas_do_album(a):
            res = self._itunes_get('lookup', {'id': a['id'], 'entity': 'song', 'country': pais.get(a['id'], 'US'),
                                              'limit': 200})
            if res is None:
                return None
            musicas = sorted((f for f in res if f.get('wrapperType') == 'track'),
                             key=lambda f: (f.get('discNumber') or 1, f.get('trackNumber') or 0))
            return [{'title': f.get('trackName'), 'seg': (f.get('trackTimeMillis') or 0) / 1000.0} for f in musicas]
        try:
            r, motivo = self._duracoes_numa_loja('iTunes', buscar, faixas_do_album, artist, album, titulos)
            if motivo:
                self.ultimo_motivo_itunes = motivo
            return r
        except Exception as e:
            self.ultimo_motivo_itunes = f"sem conexão com o serviço ({str(e)[:50]})"
            return None

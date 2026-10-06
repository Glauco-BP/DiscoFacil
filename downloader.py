"""
Acesso ao YouTube via yt-dlp.

YouTubeDownloader: informações de vídeo, listagem de playlist e canal
(YouTube Data API v3 com queda pro yt-dlp), busca de playlists com filtro
de bitrate, e download de áudio com bitrate mínimo. O download tenta vários
clientes do YouTube e fica com o melhor áudio; usa os cookies do navegador
(com queda suave quando não dá pra lê-los) e contornos para bloqueios
conhecidos (403/robô, "page needs to be reloaded", restrição de idade).
O motivo da última falha fica em last_error / last_error_retryable.
"""
import yt_dlp
import dependencias
from pathlib import Path
from typing import Dict, List, Optional, Callable

class DummyLogger:
    """
    Logger silencioso pro yt-dlp.

    Precisa da interface inteira (inclusive info e progress_bar): a leitura
    de cookies chama os dois, e sem eles toda leitura falhava. Os **kw
    absorvem parâmetros extras de algumas versões (ex.: only_once=True).
    """
    def debug(self, msg, **kw): pass
    def info(self, msg, **kw): pass
    def warning(self, msg, *a, **kw): pass
    def error(self, msg, **kw): pass
    def progress_bar(self):
        return None   # opcional: None faz o yt-dlp usar a barra silenciosa dele


class LoggerDiagnostico:
    """
    Logger do yt-dlp que guarda (em self.avisos) só os avisos que explicam
    qualidade baixa: formatos pulados, PO Token, SABR, DRM. Eles são
    mostrados ao usuário quando o áudio sai abaixo do anunciado; o resto
    fica em silêncio pra não inundar o log.
    """
    SINAIS = ('skipped', 'sabr', 'po token', 'po_token', 'drm', 'missing a url')

    def __init__(self):
        self.avisos = []

    def _guarda(self, msg):
        t = str(msg)
        if any(s in t.lower() for s in self.SINAIS) and t not in self.avisos:
            self.avisos.append(t)

    def debug(self, msg, **kw): self._guarda(msg)
    def info(self, msg, **kw): self._guarda(msg)
    def warning(self, msg, *a, **kw): self._guarda(msg)
    def error(self, msg, **kw): pass
    def progress_bar(self): return None


class DownloadTuning:
    """Limiares usados para aceitar ou descartar um áudio baixado."""
    # Reserva para quando "settings.min_bitrate_kbps" não está configurado.
    DEFAULT_MIN_BITRATE_KBPS = 80

    # Folga antes de rejeitar: o bitrate medido (VBR/overhead de contêiner)
    # raramente bate com o nominal, e um "128k" pode medir 1-2k abaixo.
    BITRATE_TOLERANCE_KBPS = 8


class YouTubeDownloader:
    """
    Fachada sobre o yt-dlp (e a YouTube Data API v3, se houver chave).
    'config_manager' fornece settings.min_bitrate_kbps,
    settings.cookies_browser, album_keywords e a chave da API.
    """
    def __init__(self, config_manager):
        self.config = config_manager
        # Motivo da última falha de download_audio() (None = sucesso).
        # last_error_retryable=False: falha determinística (ex.: bitrate da
        # fonte abaixo do mínimo), o chamador não deve tentar de novo.
        self.last_error = None
        self._ja_tentou_android = False
        self.last_error_retryable = True
    
    def get_video_info(self, url: str) -> Dict:
        """Título, descrição, duração, uploader, thumbnail, id e capítulos do vídeo; {} em caso de erro."""
        ydl_opts = {
            'quiet': True,
            'logger': DummyLogger(),
            'no_warnings': True,
            'extract_flat': False,
            # Cabeçalhos de navegador reduzem o bloqueio
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            },
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', ''),
                    'description': info.get('description', ''),
                    'duration': info.get('duration', 0),
                    'uploader': info.get('uploader', ''),
                    'thumbnail': info.get('thumbnail', ''),
                    'id': info.get('id', ''),
                    'chapters': info.get('chapters', []),
                }
        except Exception:
            return {}
    
    COMENTARIOS_MAX = 60

    def comentarios(self, url: str, maximo: Optional[int] = None) -> Optional[List[str]]:
        """
        Texto dos comentários mais curtidos do vídeo (sem respostas), pra achar
        a tracklist com tempos que alguém postou. None se não deu pra ler.
        Mais lento que get_video_info: só é chamado quando o disco precisa.
        """
        maximo = maximo or self.COMENTARIOS_MAX
        ydl_opts = {
            'quiet': True, 'logger': DummyLogger(), 'no_warnings': True, 'skip_download': True,
            'getcomments': True,
            'extractor_args': {'youtube': {'max_comments': [str(maximo), str(maximo), '0', '0'],
                                           'comment_sort': ['top']}},
        }
        for extra in (self._opcoes_de_cookies(), {}):
            try:
                with yt_dlp.YoutubeDL(dict(ydl_opts, **extra)) as ydl:
                    info = ydl.extract_info(url, download=False) or {}
                return [c.get('text') or '' for c in (info.get('comments') or []) if c.get('text')]
            except Exception:
                if not extra:
                    return None
        return None

    def _parse_iso_duration(self, duration_str: str) -> int:
        """Converte ISO 8601 duration (PT1H2M10S) para segundos"""
        import re
        
        hours = minutes = seconds = 0

        match = re.search(r'(\d+)H', duration_str)
        if match:
            hours = int(match.group(1))
        
        match = re.search(r'(\d+)M', duration_str)
        if match:
            minutes = int(match.group(1))
        
        match = re.search(r'(\d+)S', duration_str)
        if match:
            seconds = int(match.group(1))
        
        return hours * 3600 + minutes * 60 + seconds
    
    def _get_channel_id_from_url(self, channel_url: str) -> Optional[str]:
        """ID do canal: pelo yt-dlp e, se falhar, por regex na URL (/channel/ID ou @handle)."""
        import re

        try:
            ydl_opts = {'quiet': True,
            'logger': DummyLogger(), 'no_warnings': True, 'extract_flat': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                return info.get('channel_id')
        except Exception:
            pass
        
        patterns = [
            r'youtube\.com/channel/([^/?]+)',
            r'youtube\.com/@([^/?]+)',
        ]
        for pattern in patterns:
            match = re.search(pattern, channel_url)
            if match:
                return match.group(1)
        
        return None
    
    def _get_channel_videos_via_api(self, channel_url: str, progress_callback: Optional[Callable] = None) -> List[Dict]:
        """
        Lista os álbuns de um canal pela YouTube Data API v3 (sem o limite
        do yt-dlp): vídeos com palavra-chave de álbum no título ou >= 25 min.
        None se a API não estiver disponível (sem biblioteca, chave ou erro).
        """
        try:
            from googleapiclient.discovery import build
        except ImportError:
            return None

        api_key = self.config.get("api_keys.google_custom_search.api_key")
        if not api_key:
            return None

        channel_id = self._get_channel_id_from_url(channel_url)
        if not channel_id:
            return None
        
        try:
            youtube = build('youtube', 'v3', developerKey=api_key)
            
            # 1. Playlist de uploads do canal
            channels_response = youtube.channels().list(
                part='contentDetails',
                id=channel_id
            ).execute()
            
            if not channels_response['items']:
                return None
            
            uploads_playlist_id = channels_response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
            
            # 2. Todos os vídeos, 50 por página
            videos = []
            next_page_token = None
            page_count = 0
            
            album_keywords = self.config.get("album_keywords", [])
            
            while True:
                playlist_response = youtube.playlistItems().list(
                    part='snippet',
                    playlistId=uploads_playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                ).execute()
                
                page_count += 1
                
                video_ids = []
                for item in playlist_response['items']:
                    video_id = item['snippet']['resourceId']['videoId']
                    video_ids.append(video_id)
                
                # Duração de todos os vídeos da página numa chamada só
                videos_response = youtube.videos().list(
                    part='contentDetails,snippet',
                    id=','.join(video_ids)
                ).execute()
                
                for video in videos_response['items']:
                    title = video['snippet']['title']
                    video_id = video['id']
                    
                    duration_str = video['contentDetails']['duration']
                    duration_seconds = self._parse_iso_duration(duration_str)

                    # Álbum = palavra-chave no título OU >= 25 min (a API v3 não traz capítulos)
                    has_keyword = any(kw.lower() in title.lower() for kw in album_keywords)
                    is_long = duration_seconds >= 1500

                    if has_keyword or is_long:
                        videos.append({
                            'title': title,
                            'url': f"https://www.youtube.com/watch?v={video_id}",
                            'id': video_id,
                            'duration': duration_seconds,
                        })
                
                next_page_token = playlist_response.get('nextPageToken')
                if not next_page_token:
                    break
            
            if progress_callback:
                progress_callback(f"✅ API: {len(videos)} álbuns (de {page_count * 50} vídeos)")
            
            return videos
            
        except Exception as e:
            print(f"⚠️  YouTube API falhou: {e}")
            return None
    
    def _probe_best_audio_bitrate(self, video_url: str) -> Optional[float]:
        """
        Maior bitrate de áudio (abr, kbps) anunciado para o vídeo, sem
        baixar; None se não der pra determinar. Usado por search_playlists.
        """
        ydl_opts = {
            'quiet': True,
            'logger': DummyLogger(),
            'no_warnings': True,
            'skip_download': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
            formats = info.get('formats', []) if info else []
            abrs = [f.get('abr') for f in formats
                    if f.get('abr') and f.get('acodec') and f.get('acodec') != 'none']
            return max(abrs) if abrs else None
        except Exception:
            return None
    
    def search_playlists(self, query: str, max_results: int = 15) -> Optional[List[Dict]]:
        """
        Busca playlists por palavra-chave na YouTube Data API v3 (tela de
        busca). Descarta as de fonte abaixo do bitrate mínimo.

        None = API indisponível (sem biblioteca/chave ou erro); [] = nada achado.
        Cada item: {'playlist_id', 'title', 'channel_title', 'url',
        'item_count' (ou None)}.
        """
        try:
            from googleapiclient.discovery import build
        except ImportError:
            return None

        api_key = self.config.get("api_keys.google_custom_search.api_key")
        if not api_key:
            return None

        try:
            youtube = build('youtube', 'v3', developerKey=api_key)

            search_response = youtube.search().list(
                part='snippet',
                q=query,
                type='playlist',
                maxResults=max_results,
            ).execute()

            items = search_response.get('items', [])
            if not items:
                return []

            playlist_ids = [item['id']['playlistId'] for item in items if item.get('id', {}).get('playlistId')]

            # Nº de vídeos de cada playlist numa chamada só (até 50 IDs):
            # ajuda a distinguir álbum de coletânea/mix gigante.
            item_counts = {}
            if playlist_ids:
                try:
                    details_response = youtube.playlists().list(
                        part='contentDetails',
                        id=','.join(playlist_ids),
                    ).execute()
                    for d in details_response.get('items', []):
                        item_counts[d['id']] = d.get('contentDetails', {}).get('itemCount')
                except Exception:
                    pass  # contagem é opcional

            results = []
            for item in items:
                playlist_id = item.get('id', {}).get('playlistId')
                if not playlist_id:
                    continue
                snippet = item.get('snippet', {})
                results.append({
                    'playlist_id': playlist_id,
                    'title': snippet.get('title', 'Sem título'),
                    'channel_title': snippet.get('channelTitle', ''),
                    'url': f'https://www.youtube.com/playlist?list={playlist_id}',
                    'item_count': item_counts.get(playlist_id),
                })
            
            # Filtro de bitrate: evita descobrir a fonte ruim só ao baixar.
            # Sonda só a primeira faixa de cada playlist (sondar todas seria
            # lento demais; a codificação costuma ser igual na playlist toda).
            min_bitrate = self.config.get("settings.min_bitrate_kbps", DownloadTuning.DEFAULT_MIN_BITRATE_KBPS) if self.config else DownloadTuning.DEFAULT_MIN_BITRATE_KBPS
            try:
                min_bitrate = int(min_bitrate)
            except (TypeError, ValueError):
                min_bitrate = DownloadTuning.DEFAULT_MIN_BITRATE_KBPS
            
            if min_bitrate > 0 and results:
                filtered = []
                for r in results:
                    try:
                        first_item_response = youtube.playlistItems().list(
                            part='contentDetails',
                            playlistId=r['playlist_id'],
                            maxResults=1,
                        ).execute()
                        first_items = first_item_response.get('items', [])
                        if not first_items:
                            continue  # vazia/inacessível
                        first_video_id = first_items[0].get('contentDetails', {}).get('videoId')
                        if not first_video_id:
                            filtered.append(r)  # sem como checar: mantém
                            continue
                        abr = self._probe_best_audio_bitrate(
                            f'https://www.youtube.com/watch?v={first_video_id}'
                        )
                        if abr is None or abr >= min_bitrate:
                            filtered.append(r)
                    except Exception:
                        filtered.append(r)  # falha ao conferir: mantém
                results = filtered
            
            return results

        except Exception as e:
            print(f"⚠️  Busca de playlists falhou: {e}")
            return None

    def get_channel_videos(self, channel_url: str, progress_callback: Optional[Callable] = None) -> List[Dict]:
        """
        Álbuns de um canal: [{'title', 'url', 'id', 'duration'}]. Tenta a
        YouTube Data API v3; sem ela, usa o yt-dlp (filtra só por
        palavra-chave no título) e, se os cookies falharem, repete sem eles.
        """

        if progress_callback:
            progress_callback("Tentando YouTube API...")
        
        videos = self._get_channel_videos_via_api(channel_url, progress_callback)
        if videos:
            if progress_callback:
                progress_callback(f"✅ YouTube API: {len(videos)} álbuns encontrados")
            return videos
        
        if progress_callback:
            progress_callback("YouTube API indisponível, usando yt-dlp...")
        
        ydl_opts = {
            'quiet': True,
            'logger': DummyLogger(),
            'no_warnings': True,
            'extract_flat': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
        }
        
        try:
            if progress_callback:
                progress_callback("Carregando vídeos do canal...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Aba /videos do canal
                if '/videos' not in channel_url and '@' in channel_url:
                    channel_url = f"{channel_url}/videos"
                elif 'youtube.com/c/' in channel_url or 'youtube.com/channel/' in channel_url:
                    channel_url = f"{channel_url}/videos"
                
                info = ydl.extract_info(channel_url, download=False)
                
                if 'entries' not in info:
                    return []
                
                videos = []
                album_keywords = self.config.get("album_keywords", [])
                
                for entry in info['entries']:
                    if entry is None:
                        continue
                    
                    title = entry.get('title', '').lower()

                    is_album = any(keyword.lower() in title for keyword in album_keywords)
                    
                    if is_album:
                        videos.append({
                            'title': entry.get('title', ''),
                            'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                            'id': entry.get('id', ''),
                            'duration': entry.get('duration', 0),
                        })
                
                if progress_callback:
                    progress_callback(f"Encontrados {len(videos)} álbuns no canal")
                
                return videos
                
        except Exception as e:
            # Falha ao ler cookies: repete sem eles
            if self._parece_problema_de_cookies(e):
                print(f"⚠️  Cookies falharam no canal, tentando sem cookies...")
                ydl_opts_no_cookies = {
                    'quiet': True,
            'logger': DummyLogger(),
                    'no_warnings': True,
                    'extract_flat': True,
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_no_cookies) as ydl:
                        if '/videos' not in channel_url and '@' in channel_url:
                            channel_url = f"{channel_url}/videos"
                        elif 'youtube.com/c/' in channel_url or 'youtube.com/channel/' in channel_url:
                            channel_url = f"{channel_url}/videos"
                        
                        info = ydl.extract_info(channel_url, download=False)
                        
                        if 'entries' not in info:
                            return []
                        
                        videos = []
                        album_keywords = self.config.get("album_keywords", [])
                        
                        for entry in info['entries']:
                            if entry is None:
                                continue
                            
                            title = entry.get('title', '').lower()
                            is_album = any(keyword.lower() in title for keyword in album_keywords)
                            
                            if is_album:
                                videos.append({
                                    'title': entry.get('title', ''),
                                    'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                    'id': entry.get('id', ''),
                                    'duration': entry.get('duration', 0),
                                })
                        
                        if progress_callback:
                            progress_callback(f"Encontrados {len(videos)} álbuns no canal")
                        
                        return videos
                except Exception as e2:
                    print(f"Erro ao obter vídeos do canal: {e2}")
                    return []
            else:
                print(f"Erro ao obter vídeos do canal: {e}")
                return []
    
    def get_playlist_videos(self, playlist_url: str, progress_callback: Optional[Callable] = None):
        """
        Vídeos de uma playlist: {'title', 'videos': [{'title', 'url', 'id',
        'duration'}]}. Se os cookies falharem, repete sem eles; em erro,
        devolve a lista vazia.
        """
        ydl_opts = {
            'quiet': True,
            'logger': DummyLogger(),
            'no_warnings': True,
            'extract_flat': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
        }
        
        try:
            if progress_callback:
                progress_callback("Carregando vídeos da playlist...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(playlist_url, download=False)
                
                if not info or 'entries' not in info:
                    return {'title': 'Playlist', 'videos': []}
                
                playlist_title = info.get('title', 'Playlist')
                
                videos = []
                for entry in info['entries']:
                    if entry is None:
                        continue
                    
                    videos.append({
                        'title': entry.get('title', 'Unknown'),
                        'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                        'id': entry.get('id', ''),
                        'duration': entry.get('duration', 0),
                    })
                
                if progress_callback:
                    progress_callback(f"Encontrados {len(videos)} vídeos na playlist")
                
                return {'title': playlist_title, 'videos': videos}
                
        except Exception as e:
            # Falha ao ler cookies: repete sem eles
            if self._parece_problema_de_cookies(e):
                print(f"⚠️  Cookies falharam na playlist, tentando sem cookies...")
                ydl_opts_no_cookies = {
                    'quiet': True,
            'logger': DummyLogger(),
                    'no_warnings': True,
                    'extract_flat': True,
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_no_cookies) as ydl:
                        info = ydl.extract_info(playlist_url, download=False)
                        
                        if not info or 'entries' not in info:
                            return {'title': 'Playlist', 'videos': []}
                        
                        playlist_title = info.get('title', 'Playlist')
                        
                        videos = []
                        for entry in info['entries']:
                            if entry is None:
                                continue
                            
                            videos.append({
                                'title': entry.get('title', 'Unknown'),
                                'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                                'id': entry.get('id', ''),
                                'duration': entry.get('duration', 0),
                            })
                        
                        if progress_callback:
                            progress_callback(f"Encontrados {len(videos)} vídeos na playlist")
                        
                        return {'title': playlist_title, 'videos': videos}
                except Exception as e2:
                    if progress_callback:
                        progress_callback(f"Erro ao buscar playlist: {str(e2)}")
                    return {'title': 'Playlist', 'videos': []}
            else:
                if progress_callback:
                    progress_callback(f"Erro ao buscar playlist: {str(e)}")
                return {'title': 'Playlist', 'videos': []}
    
    def _meets_min_bitrate(self, reported_abr, downloaded_file: Path, progress_callback: Optional[Callable] = None, url: str = '') -> bool:
        """
        True se 'downloaded_file' atinge settings.min_bitrate_kbps (menos
        BITRATE_TOLERANCE_KBPS). Se não atingir, preenche last_error
        (não-retentável) e lista no log os formatos que o YouTube oferecia.

        Mede o arquivo com ffprobe; 'reported_abr' (valor do yt-dlp antes do
        download) é só último recurso, pois já veio muito errado (89k
        reportado, ~175k reais). Sem medida nenhuma, aceita.
        """
        TOLERANCE_KBPS = DownloadTuning.BITRATE_TOLERANCE_KBPS

        min_bitrate = self.config.get("settings.min_bitrate_kbps", DownloadTuning.DEFAULT_MIN_BITRATE_KBPS) if self.config else DownloadTuning.DEFAULT_MIN_BITRATE_KBPS
        try:
            min_bitrate = int(min_bitrate)
        except (TypeError, ValueError):
            min_bitrate = DownloadTuning.DEFAULT_MIN_BITRATE_KBPS
        if min_bitrate <= 0:
            return True

        abr = None
        try:
            import subprocess
            result = subprocess.run(
                ['ffprobe', '-v', 'error', '-show_entries', 'format=bit_rate',
                 '-of', 'default=noprint_wrappers=1:nokey=1', str(downloaded_file)],
                capture_output=True, text=True, timeout=15
            )
            if result.returncode == 0 and result.stdout.strip():
                abr = int(result.stdout.strip()) / 1000
                if progress_callback and abr:
                    progress_callback(f"   🎧 Áudio de origem: {abr:.0f}kbps")
        except Exception:
            abr = None

        if abr is None:
            # ffprobe falhou: usa o valor reportado pelo yt-dlp
            try:
                if reported_abr and reported_abr != 'unknown':
                    abr = float(reported_abr)
            except (TypeError, ValueError):
                abr = None

        if abr is None:
            return True  # sem informação não descarta

        if abr < (min_bitrate - TOLERANCE_KBPS):
            msg = f"Bitrate {abr:.0f}kbps abaixo do mínimo configurado ({min_bitrate}kbps)"
            self.last_error = msg
            self.last_error_retryable = False  # é da fonte: repetir não muda nada
            if progress_callback:
                progress_callback(f"✗ {msg} - descartando")
                # Mostra o que o YouTube oferecia: separa "escolhemos mal"
                # de "o vídeo só tem áudio ruim".
                if url:
                    for linha in self.listar_formatos_audio(url):
                        progress_callback(f"      {linha}")
            return False
        return True

    # Clientes do YouTube (player_client), do que dá melhor áudio pro que só
    # funciona: os formatos oferecidos e o bloqueio por robô variam por
    # cliente. None = não força nada (melhores formatos, mais bloqueado);
    # 'android' por último: quase sempre passa, quase sempre em baixa.
    CLIENTES_EM_ORDEM = [None, 'tv', 'web_safari', 'mweb', 'android']

    def _melhor_audio_disponivel(self, url):
        """
        Maior bitrate de áudio anunciado pro vídeo, em kbps (0 se falhar).
        É o alvo de baixar_melhor_audio: se há 138k, 62k não basta mesmo
        passando no mínimo configurado.
        """
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True,
                                   'skip_download': True,
                                   'logger': DummyLogger(),
                                   **dependencias.opcoes_js_runtimes()}) as ydl:
                info = ydl.extract_info(url, download=False)
            melhores = [f.get('abr') or 0 for f in (info.get('formats') or [])
                        if f.get('vcodec') in (None, 'none')]
            return max(melhores) if melhores else 0
        except Exception:
            return 0

    # Ordem testada no modo "automático". Firefox primeiro: é o único que não
    # trava o arquivo de cookies enquanto está aberto.
    NAVEGADORES_PARA_TENTAR = ['firefox', 'edge', 'chrome', 'brave',
                                'opera', 'vivaldi', 'chromium']

    def _descobrir_navegador_com_cookies(self, log=None):
        """
        Nome do primeiro navegador com cookies legíveis, ou '' se nenhum.

        Testa só a leitura (rápido, sem rede). O resultado, inclusive o
        fracasso, fica em cache até esquecer_navegador_de_cookies(). Com
        'log', informa o escolhido ou o motivo de cada falha.
        """
        if getattr(self, '_navegador_cookies', None) is not None:
            return self._navegador_cookies
        try:
            from yt_dlp.cookies import extract_cookies_from_browser
        except Exception:
            self._navegador_cookies = ''
            return ''
        motivos = {}
        for nome in self.NAVEGADORES_PARA_TENTAR:
            try:
                jar = extract_cookies_from_browser(nome, logger=DummyLogger())
                if jar is not None and len(jar) == 0:
                    motivos[nome] = 'lido, mas sem nenhum cookie'
                if jar is not None and len(jar) > 0:
                    self._navegador_cookies = nome
                    if log:
                        log(f"🍪 Usando cookies do {nome} ({len(jar)} cookies) - "
                            f"é o que libera o áudio de melhor qualidade.")
                    return nome
            except Exception as e:
                motivos[nome] = str(e).replace('ERROR: ', '')[:90]
                continue
        self._navegador_cookies = ''
        if log:
            log("🍪 Nenhum navegador com cookies legíveis - seguindo sem eles. Motivo por navegador:")
            for nome in ('firefox', 'edge', 'chrome'):
                if nome in motivos:
                    log(f"      • {nome}: {motivos[nome]}")
        return ''

    def esquecer_navegador_de_cookies(self):
        """
        Limpa o cache do navegador de cookies. Chamado após falha: o
        navegador pode ter sido aberto (trava o arquivo) ou fechado.
        """
        self._navegador_cookies = None

    def _opcoes_de_cookies(self):
        """
        Opções do yt-dlp com os cookies do navegador ({'cookiesfrombrowser'})
        conforme settings.cookies_browser ('automático'/vazio = descobrir;
        'nenhum' = {}).

        Com a sessão do navegador o YouTube não trata o programa como robô e
        entrega a lista completa de formatos. A leitura pode falhar (arquivo
        travado, DPAPI no Chrome), por isso os chamadores seguem sem cookies.
        """
        try:
            navegador = (self.config.get('settings.cookies_browser', '') or '').strip().lower()
        except Exception:
            navegador = ''
        if navegador in ('automático', 'automatico', 'auto', ''):
            navegador = self._descobrir_navegador_com_cookies(
                getattr(self, '_log_cookies', None))
        if not navegador or navegador in ('nenhum', 'none', 'off'):
            return {}
        return {'cookiesfrombrowser': (navegador,)}

    @staticmethod
    def _parece_problema_de_cookies(erro):
        """
        True se o erro foi ao LER os cookies do navegador (não no download):
        banco travado/não copiável, criptografia (DPAPI, keyring), permissão.
        """
        t = str(erro).lower()
        # "Sign in to confirm... use --cookies-from-browser" é o YouTube
        # PEDINDO cookies, não falha de leitura: não pode largá-los aqui.
        if 'sign in to confirm' in t or '--cookies' in t:
            return False
        return any(s in t for s in (
            'cookie database', 'cookies database', 'cookie file', 'cookies from browser',
            'failed to load cookies', 'dpapi', 'decrypt', 'could not copy',
            'keyring', 'permission denied'))

    @staticmethod
    def _precisa_de_login(erro):
        """Vídeo que o YouTube só libera logado (restrição de idade etc.)."""
        t = str(erro).lower()
        return ('confirm your age' in t or 'age-restricted' in t or 'age restricted' in t
                or 'inappropriate for some users' in t)

    @staticmethod
    def _parece_pagina_recarregar(erro):
        """
        True para "The page needs to be reloaded" (yt-dlp #17389/#17405):
        com cookies de conta logada o yt-dlp usa o cliente 'tv_downgraded',
        que o YouTube responde como injogável. Contorno em
        _tentar_contornos_recarregar.
        """
        return 'page needs to be reloaded' in str(erro).lower()

    def _registrar_contorno(self, evitar_tv=None, sem_cookies=None):
        """Memoriza, até fechar o programa, o contorno que funcionou (sem tv_downgraded / sem cookies)."""
        if evitar_tv:
            self._evitar_tv_downgraded = True
        if sem_cookies:
            self._sem_cookies_na_sessao = True

    def _aplicar_contornos(self, opts, cliente=None):
        """Aplica nas opções do yt-dlp os contornos já descobertos nesta sessão."""
        if getattr(self, '_sem_cookies_na_sessao', False):
            opts.pop('cookiesfrombrowser', None)
        clientes = [cliente] if cliente else []
        if getattr(self, '_evitar_tv_downgraded', False):
            clientes = (clientes or ['default']) + ['-tv_downgraded']
        if clientes:
            opts['extractor_args'] = {'youtube': {'player_client': clientes}}
        return opts

    def _tentar_contornos_recarregar(self, opts, cliente, executar, progress_callback=None):
        """
        Depois de um "The page needs to be reloaded": tenta 1) sem o cliente
        tv_downgraded, ainda com cookies; 2) sem cookies. Devolve o resultado
        de executar(opts) do primeiro que funcionar, ou relança o último erro.
        """
        if progress_callback and not getattr(self, '_avisou_recarregar', False):
            progress_callback("   ↻ O YouTube pediu pra \"recarregar a página\" (problema conhecido "
                              "com contas logadas) - tentando por outro caminho...")
            self._avisou_recarregar = True
        ultimo = None
        degraus = []
        if not getattr(self, '_evitar_tv_downgraded', False):
            degraus.append(('evitar_tv', False))
        if opts.get('cookiesfrombrowser'):
            degraus.append(('evitar_tv', True))
        for _, tirar_cookies in degraus:
            o = dict(opts)
            clientes = ([cliente] if cliente else ['default']) + ['-tv_downgraded']
            o['extractor_args'] = {'youtube': {'player_client': clientes}}
            if tirar_cookies:
                o.pop('cookiesfrombrowser', None)
            try:
                r = executar(o)
                self._registrar_contorno(evitar_tv=True, sem_cookies=tirar_cookies)
                if progress_callback:
                    progress_callback("   ✓ Funcionou " + ("sem os cookies do navegador" if tirar_cookies
                                                           else "evitando o cliente com problema")
                                      + " - as próximas faixas já vão direto por esse caminho.")
                return r
            except Exception as e:
                # Segue pro próximo degrau com qualquer erro: o degrau 1 pode
                # dar "Requested format is not available" e o 2 funcionar.
                ultimo = e
        if ultimo is not None:
            raise ultimo
        raise RuntimeError('The page needs to be reloaded')

    @staticmethod
    def _parece_bloqueio_do_youtube(erro):
        """
        True se o YouTube barrou o acesso (403 ou checagem de robô), e não o
        vídeo em si. Costuma passar repetindo com o cliente android.
        """
        t = str(erro).lower()
        return ('403' in t or 'forbidden' in t
                or "not a bot" in t or 'sign in to confirm' in t)

    def listar_formatos_audio(self, url, limite=8):
        """
        Linhas de log com os formatos só-áudio oferecidos pra 'url', do maior
        bitrate pro menor (até 'limite'). Diagnóstico de rejeição por
        bitrate: mostra se havia áudio melhor que o baixado.
        """
        try:
            import yt_dlp
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True,
                                   'skip_download': True,
                                   'logger': DummyLogger(),
                                   **dependencias.opcoes_js_runtimes()}) as ydl:
                info = ydl.extract_info(url, download=False)
            formatos = []
            for f in (info.get('formats') or []):
                if f.get('vcodec') not in (None, 'none'):
                    continue  # tem vídeo, não interessa
                abr = f.get('abr') or f.get('tbr') or 0
                formatos.append((abr, str(f.get('acodec', '?')),
                                 str(f.get('ext', '?')), str(f.get('format_id', '?'))))
            if not formatos:
                return ["ℹ️  Não consegui listar os formatos de áudio."]
            formatos.sort(reverse=True)
            linhas = ["📋 Áudios que o YouTube oferece pra este vídeo:"]
            for abr, ac, ext, fid in formatos[:limite]:
                marca = f"{abr:.0f}kbps" if abr else "bitrate não informado"
                linhas.append(f"• {marca:<22} {ac} ({ext}, id {fid})")
            return linhas
        except Exception as e:
            return [f"ℹ️  Não consegui listar os formatos: {str(e)[:70]}"]

    def baixar_melhor_audio(self, url, output_path, progress_callback=None):
        """
        Baixa com cada cliente de CLIENTES_EM_ORDEM e fica com o arquivo de
        maior bitrate, apagando os outros. Devolve (caminho ou None, kbps).

        Para ao atingir 90% do melhor anunciado (ou o mínimo configurado):
        no caso bom custa um download só. O primeiro que funciona pode vir
        bem abaixo do disponível (ex.: 62k num vídeo com 138k).
        """
        from pathlib import Path as _P
        alvo = self._melhor_audio_disponivel(url)
        self._ultimo_alvo = alvo
        try:
            minimo = int(self.config.get('settings.min_bitrate_kbps', 80) or 80)
        except Exception:
            minimo = 80
        bom_o_bastante = max(minimo, int(alvo * 0.9)) if alvo else minimo
        if progress_callback and alvo:
            progress_callback(f"   🎯 Melhor áudio anunciado: {alvo:.0f}kbps "
                              f"(aceito a partir de {bom_o_bastante:.0f}kbps)")

        melhor_arquivo, melhor_taxa, melhor_cliente = None, 0, None
        self._erros_por_cliente = {}
        clientes = list(self.CLIENTES_EM_ORDEM)
        for cliente in clientes:
            arq = self._baixar_com_cliente(url, output_path, cliente, progress_callback)
            if not arq:
                continue
            taxa = self._medir_kbps(arq)
            nome = cliente or 'padrão'
            if progress_callback:
                progress_callback(f"   🎧 {nome}: {taxa:.0f}kbps")
            if taxa > melhor_taxa:
                if melhor_arquivo and Path(melhor_arquivo) != Path(arq):
                    try: _P(melhor_arquivo).unlink()
                    except Exception: pass
                melhor_arquivo, melhor_taxa, melhor_cliente = arq, taxa, nome
            elif Path(arq) != Path(melhor_arquivo or ''):
                try: _P(arq).unlink()
                except Exception: pass
            if melhor_taxa >= bom_o_bastante:
                break

        # Abaixo do alvo com o contorno "sem cookies" ativo: tenta este vídeo
        # com a conta do navegador (sem tv_downgraded). Sem cookies às vezes
        # só o android passa (48k num vídeo de 135k).
        if (melhor_taxa < bom_o_bastante and getattr(self, '_sem_cookies_na_sessao', False)
                and self._opcoes_de_cookies()):
            if progress_callback:
                progress_callback("   ↻ Sem os cookies não veio a qualidade cheia - tentando este "
                                  "vídeo com a sua conta do navegador...")
            self._forcar_cookies_agora = True
            try:
                arq = self._baixar_com_cliente(url, output_path, None, progress_callback)
            finally:
                self._forcar_cookies_agora = False
            if arq:
                taxa = self._medir_kbps(arq)
                if progress_callback:
                    progress_callback(f"   🎧 com a conta: {taxa:.0f}kbps")
                if taxa > melhor_taxa:
                    if melhor_arquivo and Path(melhor_arquivo) != Path(arq):
                        try: _P(melhor_arquivo).unlink()
                        except Exception: pass
                    melhor_arquivo, melhor_taxa, melhor_cliente = arq, taxa, 'com a conta'
                elif Path(arq) != Path(melhor_arquivo or ''):
                    try: _P(arq).unlink()
                    except Exception: pass

        if melhor_arquivo and progress_callback:
            progress_callback(f"   ✅ Ficando com {melhor_taxa:.0f}kbps (via {melhor_cliente})")
            # Abaixo do anunciado: mostra os erros/avisos do yt-dlp (uma vez por sessão)
            if alvo and melhor_taxa < bom_o_bastante and not getattr(self, '_ja_explicou', False):
                avisos = getattr(self, '_ultimos_avisos', []) or []
                progress_callback(f"   ℹ️  O vídeo tem {alvo:.0f}kbps, mas o YouTube só "
                                  f"liberou {melhor_taxa:.0f}kbps pra download. Motivo "
                                  f"informado pelo yt-dlp:")
                for nome_c, err_c in list((getattr(self, '_erros_por_cliente', {}) or {}).items())[:3]:
                    progress_callback(f"      • {nome_c}: {err_c}")
                if avisos:
                    for a in avisos[:3]:
                        progress_callback(f"      • {a.replace('WARNING: ', '')[:150]}")
                else:
                    progress_callback("      • (nenhum aviso específico - restrição do lado do YouTube)")
                self._ja_explicou = True
        return melhor_arquivo, melhor_taxa

    def _medir_kbps(self, arquivo):
        """Bitrate real do arquivo em kbps (stream, senão contêiner); 0 se não der pra medir."""
        import subprocess as _sp
        for args in (['-select_streams', 'a:0', '-show_entries', 'stream=bit_rate'],
                     ['-show_entries', 'format=bit_rate']):
            try:
                r = _sp.run(['ffprobe', '-v', 'error'] + args +
                            ['-of', 'default=noprint_wrappers=1:nokey=1', str(arquivo)],
                            capture_output=True, text=True, timeout=15)
                t = r.stdout.strip()
                if t.isdigit() and int(t) > 0:
                    return int(t) / 1000
            except Exception:
                continue
        return 0

    def _baixar_com_cliente(self, url, output_path, cliente, progress_callback=None):
        """
        Um download com o player_client 'cliente' (None = não força).
        Trata restrição de idade, "page needs to be reloaded" e falha de
        cookies. Devolve o maior arquivo de áudio novo em 'output_path', ou
        None (o erro fica em _erros_por_cliente).
        """
        import yt_dlp
        from pathlib import Path as _P
        antes = {p.name for p in _P(output_path).glob('*.*')}
        diag = LoggerDiagnostico()
        self._ultimos_avisos = diag.avisos
        opts = {
            'format': 'bestaudio/best',
            'format_sort': ['abr', 'asr', 'size'],
            'outtmpl': str(_P(output_path) / '%(id)s.%(format_id)s.%(ext)s'),
            'quiet': True, 'no_warnings': False, 'logger': diag,
            'verbose': False,
            'prefer_free_formats': True, 'postprocessors': [],
            **self._opcoes_de_cookies(),
            # Deno: sem ele só o android baixa (~48kbps).
            **dependencias.opcoes_js_runtimes(),
        }
        forcar_cookies = getattr(self, '_forcar_cookies_agora', False)
        self._aplicar_contornos(opts, cliente)
        if forcar_cookies:
            # Tentativa com a conta: repõe os cookies mesmo com o contorno ativo
            opts.update(self._opcoes_de_cookies())
            clientes = ([cliente] if cliente else ['default']) + ['-tv_downgraded']
            opts['extractor_args'] = {'youtube': {'player_client': clientes}}

        def _executar(o):
            with yt_dlp.YoutubeDL(o) as ydl:
                ydl.download([url])
        try:
            _executar(opts)
        except Exception as e:
            if not isinstance(getattr(self, '_erros_por_cliente', None), dict):
                self._erros_por_cliente = {}
            self._erros_por_cliente[cliente or 'padrão'] = str(e).replace('ERROR: ', '')[:160]
            if (self._precisa_de_login(e) and not opts.get('cookiesfrombrowser')
                    and not forcar_cookies and self._opcoes_de_cookies()):
                # Restrição de idade sem cookies (contorno ativo): tenta com a conta
                if progress_callback and cliente is None:
                    progress_callback("   ↻ Vídeo com restrição de idade - tentando com a sua conta do navegador...")
                self._forcar_cookies_agora = True
                try:
                    r = self._baixar_com_cliente(url, output_path, cliente, progress_callback)
                finally:
                    self._forcar_cookies_agora = False
                return r
            if self._parece_pagina_recarregar(e) and forcar_cookies:
                return None
            if self._parece_pagina_recarregar(e):
                try:
                    self._tentar_contornos_recarregar(opts, cliente, _executar, progress_callback)
                except Exception:
                    return None
            elif self._parece_problema_de_cookies(e):
                # Leitura dos cookies falhou: repete sem eles e redescobre o navegador depois
                self.esquecer_navegador_de_cookies()
                opts.pop('cookiesfrombrowser', None)
                try:
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        ydl.download([url])
                except Exception:
                    return None
            else:
                return None
        novos = [p for p in _P(output_path).glob('*.*')
                 if p.name not in antes and p.suffix.lower() in
                 ('.m4a', '.webm', '.opus', '.mp3', '.mp4', '.ogg')]
        if not novos:
            return None
        return str(max(novos, key=lambda p: p.stat().st_size))

    def download_audio(self, url: str, output_path: str, progress_callback: Optional[Callable] = None) -> Optional[str]:
        """
        Baixa o áudio de 'url' em 'output_path' e devolve o caminho, ou None
        (motivo em last_error).

        Com o contorno "sem cookies" ativo, o YouTube às vezes libera bem
        menos que anuncia (138k anunciado, 62k entregue). Nesse caso exige
        90% do melhor anunciado, não só o mínimo configurado; abaixo disso
        apaga o arquivo e falha sem retentativa.
        """
        self._ultimo_alvo = 0
        arq = self._download_audio_interno(url, output_path, progress_callback)
        if not arq or not getattr(self, '_sem_cookies_na_sessao', False):
            return arq
        try:
            alvo = getattr(self, '_ultimo_alvo', 0) or self._melhor_audio_disponivel(url)
            try:
                minimo = int(self.config.get('settings.min_bitrate_kbps', 80) or 80)
            except Exception:
                minimo = 80
            piso = max(minimo, int(alvo * 0.9)) if alvo else minimo
            taxa = self._medir_kbps(arq)
        except Exception:
            return arq
        if taxa and taxa + 0.5 >= piso:
            return arq
        try:
            Path(arq).unlink()
        except Exception:
            pass
        self.last_error = (f"Sem os cookies o YouTube só liberou {taxa:.0f}kbps (o vídeo tem "
                           f"{alvo:.0f}kbps) - não salvei pra não perder qualidade")
        self.last_error_retryable = False
        if progress_callback:
            progress_callback(f"   ✗ {self.last_error}")
        return None

    def _download_audio_interno(self, url: str, output_path: str, progress_callback: Optional[Callable] = None) -> Optional[str]:
        """
        Baixa o melhor áudio e confere o bitrate mínimo; devolve o caminho
        ou None. Caminho principal: baixar_melhor_audio. Se ele não trouxer
        nada, cai num download direto com a cadeia de reserva
        cookies -> sem cookies -> cliente android.
        """
        self.last_error = None
        self.last_error_retryable = True
        # Por download: cada faixa tem direito à sua tentativa com o android.
        self._ja_tentou_android = False
        output_template = str(Path(output_path) / '%(id)s.%(ext)s')

        # Caminho principal; o download direto abaixo é a reserva.
        try:
            arq, taxa = self.baixar_melhor_audio(url, output_path, progress_callback)
            if arq:
                if self._meets_min_bitrate(None, Path(arq), progress_callback, url=url):
                    return arq
                return None
        except Exception as e:
            if progress_callback:
                progress_callback(f"   ⚠️  Busca pelo melhor áudio falhou "
                                  f"({str(e)[:70]}) - usando o caminho antigo")
        
        def progress_hook(d):
            if progress_callback and d['status'] == 'downloading':
                try:
                    percent = d.get('_percent_str', '0%')
                    speed = d.get('_speed_str', 'N/A')
                    progress_callback(f"Baixando: {percent} - {speed}")
                except Exception:
                    pass
        
        # Seleção de áudio: melhor áudio sem preferir contêiner (o opus
        # costuma ter o maior bitrate; exigir m4a o descartava), ordenado
        # explicitamente por bitrate.
        ydl_opts = {
            'format': 'bestaudio/best',
            'format_sort': ['abr', 'asr', 'size'],
            'outtmpl': output_template,
            'progress_hooks': [progress_hook],
            'quiet': True,
            'logger': DummyLogger(),
            'no_warnings': True,
            # False faria o yt-dlp preferir m4a, anulando a ordenação por bitrate
            'prefer_free_formats': True,
            'postprocessors': [],
            **self._opcoes_de_cookies(),
            **dependencias.opcoes_js_runtimes(),
            'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
            # Sem player_client fixo: forçar cliente empobrece a lista de
            # formatos (62k vindo de um vídeo com 138k). O yt-dlp escolhe.
        }
        
        self._aplicar_contornos(ydl_opts)

        def _extrair(o):
            with yt_dlp.YoutubeDL(o) as ydl:
                return ydl.extract_info(url, download=True)

        try:
            if progress_callback:
                progress_callback("Iniciando download...")
            
            try:
                info = _extrair(ydl_opts)
            except Exception as e_rec:
                if (self._precisa_de_login(e_rec) and not ydl_opts.get('cookiesfrombrowser')
                        and self._opcoes_de_cookies()):
                    # Restrição de idade sem cookies (contorno ativo): tenta com a conta
                    o = dict(ydl_opts)
                    o.update(self._opcoes_de_cookies())
                    o['extractor_args'] = {'youtube': {'player_client': ['default', '-tv_downgraded']}}
                    info = _extrair(o)
                elif self._parece_pagina_recarregar(e_rec):
                    info = self._tentar_contornos_recarregar(ydl_opts, None, _extrair, progress_callback)
                else:
                    raise
            if True:

                video_id = info.get('id', '')

                ext = info.get('ext', 'webm')
                downloaded_file = Path(output_path) / f"{video_id}.{ext}"
                
                if not downloaded_file.exists():
                    # A extensão final pode diferir da informada
                    for test_ext in ['opus', 'm4a', 'webm', 'mp4', 'mp3', 'ogg']:
                        test_file = Path(output_path) / f"{video_id}.{test_ext}"
                        if test_file.exists():
                            downloaded_file = test_file
                            break
                
                if downloaded_file.exists():
                    audio_quality = info.get('abr', 'unknown')
                    audio_codec = info.get('acodec', 'unknown')
                    
                    if progress_callback:
                        progress_callback(f"✓ Áudio baixado: {audio_codec} {audio_quality}kbps")
                        progress_callback(f"✓ Arquivo: {downloaded_file.name}")

                    # Abaixo do mínimo: descarta em vez de salvar áudio ruim
                    if not self._meets_min_bitrate(audio_quality, downloaded_file, progress_callback, url=url):
                        try:
                            downloaded_file.unlink()
                        except Exception:
                            pass
                        return None
                    
                    return str(downloaded_file)
                
                self.last_error = "Arquivo baixado não encontrado no disco após o download"
                return None
                
        except Exception as e:
            # Reserva 1: falha ao ler cookies -> repete sem eles
            if self._parece_problema_de_cookies(e):
                if progress_callback:
                    progress_callback(
                        "   ⚠️  Não consegui ler os cookies do navegador "
                        "(ele costuma travar o arquivo enquanto está aberto).")
                    progress_callback(
                        "   ↻ Seguindo SEM cookies. Pra usá-los: feche o "
                        "navegador antes de baixar, ou escolha o Firefox nas "
                        "Configurações, que não trava o arquivo.")
                ydl_opts_no_cookies = {
                    # Mesma seleção de áudio do caminho principal
                    'format': 'bestaudio/best',
                    'format_sort': ['abr', 'asr', 'size'],
                    'outtmpl': output_template,
                    'progress_hooks': [progress_hook],
                    'quiet': True,
            'logger': DummyLogger(),
                    'no_warnings': True,
                    'prefer_free_formats': True,
                    'postprocessors': [],
                }
                try:
                    with yt_dlp.YoutubeDL(ydl_opts_no_cookies) as ydl:
                        info = ydl.extract_info(url, download=True)
                        
                        video_id = info.get('id', '')
                        ext = info.get('ext', 'webm')
                        downloaded_file = Path(output_path) / f"{video_id}.{ext}"
                        
                        if not downloaded_file.exists():
                            for test_ext in ['opus', 'm4a', 'webm', 'mp4', 'mp3', 'ogg']:
                                test_file = Path(output_path) / f"{video_id}.{test_ext}"
                                if test_file.exists():
                                    downloaded_file = test_file
                                    break
                        
                        if downloaded_file.exists():
                            audio_quality = info.get('abr', 'unknown')
                            audio_codec = info.get('acodec', 'unknown')
                            
                            if progress_callback:
                                progress_callback(f"✓ Áudio baixado: {audio_codec} {audio_quality}kbps")
                                progress_callback(f"✓ Arquivo: {downloaded_file.name}")

                            if not self._meets_min_bitrate(audio_quality, downloaded_file, progress_callback, url=url):
                                try:
                                    downloaded_file.unlink()
                                except Exception:
                                    pass
                                return None
                            
                            return str(downloaded_file)
                        
                        self.last_error = "Arquivo baixado não encontrado no disco após o download (sem cookies)"
                        return None
                except Exception as e2:
                    # Sem cookies o YouTube pode barrar (403): último degrau,
                    # o cliente android (menos qualidade, mais chance).
                    if (self._parece_bloqueio_do_youtube(e2)
                            and not getattr(self, '_ja_tentou_android', False)):
                        self._ja_tentou_android = True
                        try:
                            if progress_callback:
                                progress_callback("   ↻ Sem cookies o YouTube barrou - "
                                                  "tentando com o cliente alternativo…")
                            opts_and = dict(ydl_opts_no_cookies)
                            opts_and['extractor_args'] = {
                                'youtube': {'player_client': ['android', 'web']}}
                            with yt_dlp.YoutubeDL(opts_and) as ydl:
                                ydl.download([url])
                            achados = [a for a in Path(output_path).glob('*.*')
                                       if a.suffix.lower() in
                                       ('.m4a', '.webm', '.opus', '.mp3', '.mp4', '.ogg')]
                            if achados:
                                maior = max(achados, key=lambda p: p.stat().st_size)
                                if self._meets_min_bitrate(None, maior, progress_callback, url=url):
                                    return str(maior)
                                return None
                        except Exception as e4:
                            if progress_callback:
                                progress_callback(f"✗ Também falhou no cliente alternativo: "
                                                  f"{str(e4)[:110]}")
                    if progress_callback:
                        progress_callback(f"✗ Erro no download: {e2}")
                    self.last_error = f"Erro no download: {str(e2)[:200]}"
                    print(f"Erro ao baixar áudio: {e2}")
                    return None
            elif self._parece_bloqueio_do_youtube(e) and not getattr(self, '_ja_tentou_android', False):
                # Reserva 2: bloqueio (403/robô) -> repete com o cliente
                # android, que passa pelo bloqueio mas oferece menos formatos.
                # Áudio pior é melhor que nenhum (o mínimo ainda é conferido).
                self._ja_tentou_android = True
                try:
                    if progress_callback:
                        progress_callback("   ↻ YouTube barrou o acesso - "
                                          "repetindo com outro cliente…")
                    opts_android = dict(ydl_opts)
                    opts_android['extractor_args'] = {
                        'youtube': {'player_client': ['android', 'web']}}
                    with yt_dlp.YoutubeDL(opts_android) as ydl:
                        ydl.download([url])
                    arquivos = list(Path(output_path).glob('*.*'))
                    arquivos = [a for a in arquivos if a.suffix.lower() in
                                ('.m4a', '.webm', '.opus', '.mp3', '.mp4', '.ogg')]
                    if arquivos:
                        maior = max(arquivos, key=lambda p: p.stat().st_size)
                        if self._meets_min_bitrate(None, maior, progress_callback, url=url):
                            return str(maior)
                        return None
                except Exception as e3:
                    if progress_callback:
                        progress_callback(f"✗ Também falhou com o outro cliente: {str(e3)[:120]}")
                self.last_error = f"Erro no download: {str(e)[:200]}"
            else:
                if progress_callback:
                    progress_callback(f"✗ Erro no download: {e}")
                self.last_error = f"Erro no download: {str(e)[:200]}"
                print(f"Erro ao baixar áudio: {e}")
                return None
    
    def download_thumbnail(self, url: str, output_path: str, quality: str = "medium") -> Optional[str]:
        """
        Salva a thumbnail do vídeo no arquivo 'output_path'; devolve o
        caminho ou None. quality: 'low' (120x90), 'medium' (320x180),
        'high' (480x360) ou 'max' (1280x720).
        """
        try:
            info = self.get_video_info(url)
            thumbnail_url = info.get('thumbnail', '')
            
            if not thumbnail_url:
                return None
            
            if 'youtube.com' in url or 'youtu.be' in url:
                video_id = info.get('id', '')
                if quality == 'low':
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/default.jpg"
                elif quality == 'medium':
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg"
                elif quality == 'high':
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                else:  # max
                    thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

            import requests
            response = requests.get(thumbnail_url, timeout=10)
            response.raise_for_status()
            
            output_file = Path(output_path)
            with open(output_file, 'wb') as f:
                f.write(response.content)
            
            print(f"✓ Thumbnail baixada: {output_file.name}")
            return str(output_file)
            
        except Exception as e:
            print(f"Erro ao baixar thumbnail: {e}")
            return None

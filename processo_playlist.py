"""
Modo playlist: uma playlist = um álbum, um vídeo por faixa.

process_playlist(url)
  1. Lista os vídeos e tira artista/álbum/ano do título da playlist.
  2. Identifica no Discogs (duração somada e títulos dos vídeos como pistas).
     Aceita sozinho com nota >= mínima e nº de faixas a até 2 do da playlist;
     senão vai pra "Precisam de você".
  3. Cada vídeo vira uma faixa (process_playlist_song): casa o vídeo com a
     faixa oficial do Discogs (_match_playlist_track), baixa, converte pra
     MP3 na taxa da fonte e grava as tags. Uma faixa que falha recusa a
     playlist inteira (álbum incompleto): a pasta parcial é apagada e a
     playlist vai pra "Precisam de você".
"""
import re
import shutil
import subprocess
import time
from pathlib import Path

import nomes
import saida
from audio_util import FFMPEG_PATH, _subprocess_no_window_kwargs, duracao_do_arquivo, medir_bitrate_fonte, taxa_mp3_para
from metadata_manager import gravar_tags
from pontuacao import titles_similar

TAMANHO_MINIMO_FAIXA = 10_000           # bytes
MAX_DIFERENCA_DE_FAIXAS = 2             # Discogs × nº de vídeos da playlist


class PlaylistMixin:
    """Playlist = um álbum, um vídeo por faixa."""

    def process_playlist(self, playlist_url):
        """Identifica e baixa uma playlist (chamado pelo trabalhador da fila)."""
        self._ensure_acervo_and_queue()
        self.log(f"\n{'=' * 60}")
        self.log("PLAYLIST")
        self.log(f"{'=' * 60}")
        self.log(f"URL: {playlist_url}\n")
        self.log("Buscando vídeos da playlist...")
        dados = self.downloader.get_playlist_videos(playlist_url, self.log) or {}
        titulo, videos = dados.get('title', 'Playlist'), dados.get('videos', [])
        if not videos:
            self.log("✗ Nenhum vídeo encontrado nesta playlist")
            return
        self.log(f"✓ {len(videos)} vídeo(s) encontrado(s)")
        self.log(f"📀 Playlist: {titulo}\n")

        self.log("🔎 Identificando playlist no Discogs...")
        artista, album, ano = self._extract_artist(titulo), self._extract_album(titulo), self._extract_year(titulo)
        data = self._buscar_playlist_no_discogs(artista, album, videos)
        confianca = data.get('confidence_pct', 0) if data else 0
        meta = None
        if not data:
            reason = "Playlist não encontrada no Discogs"
        else:
            self._reg('FONTE', f"playlist ({len(videos)} vídeos) -> " + self._descrever_fonte(data))
            n_discogs = len(data.get('tracks', []))
            if abs(n_discogs - len(videos)) > MAX_DIFERENCA_DE_FAIXAS:
                reason = f"Nº de faixas não bate (Discogs: {n_discogs}, playlist: {len(videos)})"
            elif confianca < self.AUTO_PROCESS_MIN_CONFIDENCE_PCT:
                reason = (f"Confiança {confianca}% abaixo do mínimo automático "
                          f"({self.AUTO_PROCESS_MIN_CONFIDENCE_PCT}%) - score={data.get('score', 0):.0f}")
            else:
                self.log(f"   Discogs: ✅ {n_discogs} faixas (playlist: {len(videos)}) | confiança: {confianca}%")
                meta = self._metadados_da_playlist(data, artista, album, ano)
            if not meta:
                self.log(f"   ⚠️  {reason}")
        if not meta:
            self.pending_queue.add(kind='baixa_confianca' if data else 'nao_encontrado',
                                   url=playlist_url, video_title=titulo, title_artist=artista,
                                   title_album=album, year=str(ano or ''), confidence_pct=confianca,
                                   reason=reason, discogs_data=data, source_type='playlist')
            self.log(f"\n⏸️  Playlist adicionada à fila de pendentes ({confianca}% de confiança) - {reason}")
            self.log("   Abra 'Álbuns pendentes' para decidir se baixa ou descarta.\n")
            return

        chave = meta.get('discogs_master_id') or meta.get('discogs_release_id')
        if chave and self.acervo_index.has(chave):
            self.log(f"\n⏭️  PLAYLIST JÁ ESTÁ NO ACERVO: {self.acervo_index.get(chave).get('folder', '?')}\n")
            return
        self.log("")
        falhou = self._baixar_faixas_da_playlist(videos, titulo, meta)
        if falhou:
            self.pending_queue.add(
                kind='falha_download', url=playlist_url, video_title=titulo,
                title_artist=meta.get('artist'), title_album=meta.get('album'), year=str(meta.get('year') or ''),
                # o motivo REAL (ex.: bitrate recusado), não só "falhou no download"
                reason=(f"Faixa '{falhou}' recusada: "
                        f"{getattr(self.downloader, 'last_error', '') or 'falha no download'} - playlist incompleta"),
                discogs_data=meta, source_type='playlist')
            self.log("\n⏸️  Playlist rejeitada (incompleta) e adicionada à fila de pendentes para nova tentativa depois.\n")
        else:
            self.log("\n✓ Playlist concluída!")

    def _buscar_playlist_no_discogs(self, artista, album, videos):
        """O resultado escolhido no Discogs, ou None."""
        try:
            return self.catalogo.discogs(artista, album,
                                         reference_duration=sum(v.get('duration', 0) or 0 for v in videos) or None,
                                         reference_track_titles=[v['title'] for v in videos if v.get('title')] or None,
                                         log_func=self.log)
        except Exception as e:
            self.log(f"   Discogs: ❌ Erro: {str(e)[:50]}")
            return None

    @staticmethod
    def _metadados_da_playlist(data, artista, album, ano):
        """Resultado do Discogs -> metadados usados em cada faixa (tags, pasta, tracklist oficial)."""
        artistas = data.get('artists') or [artista]
        return {'artist': ', '.join(artistas), 'album': data.get('title') or album,
                'year': data.get('year') or ano, 'cover_image': data.get('cover_image'),
                'discogs_master_id': data.get('master_id'), 'discogs_release_id': data.get('release_id'),
                'album_artist': artistas[0], 'genre': data.get('genre'), 'tracks': data.get('tracks') or []}

    def _baixar_faixas_da_playlist(self, videos, titulo_playlist, meta):
        """
        Baixa cada vídeo como uma faixa. Devolve None se todas deram certo,
        ou o título da que falhou (aí a pasta parcial é apagada).
        """
        pasta = None
        for j, video in enumerate(videos, 1):
            self.log(f"\n--- VÍDEO {j}/{len(videos)} ---")
            self.log(f"Título: {video['title']}")
            try:
                ok, pasta_atual = self.process_playlist_song(video['url'], video['title'], titulo_playlist, j,
                                                             len(videos), meta, duracao_video=video.get('duration'))
                pasta = pasta_atual or pasta
            except Exception as e:
                self.log(f"\n⚠️ Erro no vídeo {j}: {str(e)[:150]}")
                ok = False
            if not ok:
                self.log(f"\n❌ Faixa {j}/{len(videos)} falhou - a playlist inteira será rejeitada "
                         f"(álbum incompleto sem ela)")
                try:
                    if pasta and Path(pasta).exists():
                        shutil.rmtree(pasta)
                        self.log(f"   🗑️  Pasta parcial removida: {pasta}")
                except Exception as e:
                    self.log(f"   ⚠️  Não consegui remover a pasta parcial: {str(e)[:80]}")
                return video['title']
        return None

    def _process_pending_playlist_item(self, item) -> bool:
        """
        "Baixar" numa pendência de playlist. Usa o que já foi achado; sem
        isso (ou com a busca corrigida pelo usuário), tenta o Discogs de novo
        (qualquer nota, nº de faixas a até 2) e, por fim, o título da playlist.
        """
        url = item['url']
        self.log(f"\n▶ Processando playlist pendente: {item['video_title']}")
        dados = self.downloader.get_playlist_videos(url, self.log) or {}
        videos = dados.get('videos', [])
        titulo = dados.get('title', item['video_title'])
        if not videos:
            self.log("   ✗ Nenhum vídeo encontrado nessa playlist (removida/privada?)")
            return False

        data = None if item.get('busca_corrigida') else item.get('discogs_data')
        if data and 'album' in data:                  # já no formato da playlist (falha de download)
            meta = data
        elif data:
            meta = self._metadados_da_playlist(data, item['title_artist'], item['title_album'], item['year'])
        else:
            if item.get('busca_corrigida'):
                artista, album, ano = item['title_artist'], item['title_album'], item.get('year', '')
                self.log(f"   ✏️  Busca corrigida por você: '{artista}' – '{album}'")
            else:
                artista, album, ano = (self._extract_artist(titulo), self._extract_album(titulo),
                                       self._extract_year(titulo))
            novo = self._buscar_playlist_no_discogs(artista, album, videos)
            if novo and abs(len(novo.get('tracks', [])) - len(videos)) <= MAX_DIFERENCA_DE_FAIXAS:
                self.log(f"   Discogs: ✅ {len(novo['tracks'])} faixas (playlist: {len(videos)})")
                meta = self._metadados_da_playlist(novo, artista, album, ano)
            else:
                self.log("   ⚠️  Discogs não confirmou - usando o título da playlist")
                meta = {'artist': artista, 'album': album, 'year': ano, 'cover_image': None}
        chave = meta.get('discogs_master_id') or meta.get('discogs_release_id')
        if chave and self.acervo_index.has(chave):
            self.log(f"   ⏭️  Já está no acervo: {self.acervo_index.get(chave).get('folder', '?')}")
            return True
        return not self._baixar_faixas_da_playlist(videos, titulo, meta)

    # ------------------------------------------------------------------ uma faixa
    def process_playlist_song(self, url, title, playlist_name, track_number, total_tracks, playlist_metadata=None,
                              duracao_video=None):
        """Um vídeo da playlist -> um MP3 com tags. Devolve (ok, pasta)."""
        self.log(f"\n{'=' * 60}")
        self.log("🎵 PROCESSANDO MÚSICA")
        self.log(f"{'=' * 60}\n")
        meta = playlist_metadata
        if meta:
            artist, album, year = meta['artist'], meta['album'], meta['year']
            # nome e número oficiais do Discogs; sem casamento, o título do vídeo limpo
            oficial, numero, casou = self._match_playlist_track(title, track_number, meta, duracao_video=duracao_video)
            if casou and oficial:
                song, track_number = oficial, numero
            else:
                song = self._musica_do_titulo(title)[1]
                song = nomes.limpar_titulo_de_video(song, artist) or song
        else:
            artist, song = self._musica_do_titulo(title)
            artist = artist or "Unknown Artist"
            song = nomes.tirar_sufixos_de_video(song) or song
            album, year = self._album_do_nome_da_playlist(playlist_name, artist)

        output_dir = Path(self.config.get_output_directory()) / saida.nome_da_pasta(artist, album, year)
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / f"{track_number:02d} - {saida.limpar_nome(song[:50])}.mp3"
        if filepath.exists():
            self.log(f"⏭️  MÚSICA JÁ EXISTE: {filepath}\n")
            return True, output_dir

        self.log("1. Baixando áudio...")
        temp_dir = Path(self.config.get_output_directory()) / ".temp"
        temp_dir.mkdir(exist_ok=True)
        audio_file = saida.baixar_audio(self.downloader, url, temp_dir, self.log, TAMANHO_MINIMO_FAIXA)
        if not audio_file:
            motivo = getattr(self.downloader, 'last_error', None) or "Vídeo privado, removido ou bloqueado"
            self.log(f"\n❌ FALHA APÓS {saida.TENTATIVAS_DOWNLOAD} TENTATIVAS")
            self.log(f"   URL: {url}")
            self.log(f"   💡 Motivo: {motivo}")
            return False, output_dir

        self.log("\n2. Baixando capa...")
        capa = output_dir / "cover.jpg"
        if capa.exists():
            self.log("✓ Capa já existe")
        elif not saida.baixar_capa((meta or {}).get('cover_image'), capa, self.log, 'Discogs'):
            self.downloader.download_thumbnail(url, str(capa))
            self.log("✓ Capa baixada (YouTube)")

        # Com o áudio em mãos, confere a duração contra a do Discogs (só avisa)
        if meta and meta.get('tracks'):
            real = duracao_do_arquivo(audio_file)
            if real:
                self._match_playlist_track(title, track_number, meta, audio_duration=real)

        self.log("\n3. Convertendo para MP3...")
        if not self._converter_para_mp3(audio_file, filepath):
            return False, output_dir

        self.log("\n4. Adicionando metadados...")
        self._tags_da_faixa(filepath, song, artist, album, year, track_number, total_tracks, meta, capa, output_dir)
        shutil.rmtree(temp_dir, ignore_errors=True)
        self.log(f"\n{'=' * 60}")
        self.log("✓ MÚSICA CONCLUÍDA!")
        self.log(f"{'=' * 60}\n")
        return True, output_dir

    @staticmethod
    def _musica_do_titulo(title):
        """'03. Artista - Música' -> ('Artista', 'Música'); sem ' - ', (None, título)."""
        if '. ' in title and title.split('.')[0].strip().isdigit():
            title = title.split('. ', 1)[1]
        if ' - ' in title:
            artista, musica = title.split(' - ', 1)
            return artista.strip(), musica.strip()
        return None, title

    @staticmethod
    def _album_do_nome_da_playlist(nome, artista):
        """Sem Discogs: álbum e ano tirados do nome da playlist (sem 'Full Album' nem o artista na frente)."""
        album = re.sub(r'\s*[-–—(]?\s*(full\s+(album|álbum|albúm)|álbum\s+completo|album\s+completo)\)?.*$',
                       '', nome, flags=re.IGNORECASE | re.UNICODE).strip()
        m = re.search(r'[-–—\(]\s*(\d{4})\s*[\)\-–—]?', album)
        ano = m.group(1) if m else None
        if m:
            album = album[:m.start()].strip()
        if album.lower().startswith(artista.lower()):
            album = album[len(artista):].strip().lstrip('- ')
        return album or nome, ano

    def _converter_para_mp3(self, audio_file, filepath) -> bool:
        """
        Converte com o ffmpeg do programa, na taxa da fonte (taxa_mp3_para),
        e confere a duração. Falhou: apaga o MP3 parcial e o original.
        """
        taxa = taxa_mp3_para(medir_bitrate_fonte(audio_file))
        dur_origem = duracao_do_arquivo(audio_file)
        try:
            r = subprocess.run([FFMPEG_PATH, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(audio_file),
                                '-vn', '-map', '0:a:0', '-c:a', 'libmp3lame', '-b:a', f"{taxa}k", str(filepath)],
                               capture_output=True, text=True, timeout=900, **_subprocess_no_window_kwargs())
            if r.returncode != 0:
                raise RuntimeError((r.stderr or '').strip()[-200:] or f"ffmpeg saiu com código {r.returncode}")
            dur_mp3 = duracao_do_arquivo(str(filepath))
            if dur_origem and (not dur_mp3 or abs(dur_mp3 - dur_origem) > max(3.0, dur_origem * 0.03)):
                raise RuntimeError(f"MP3 com duração errada ({dur_mp3 or 0:.0f}s, esperado {dur_origem:.0f}s)")
            self.log(f"✓ Salvo em: {filepath}")
            return True
        except Exception as e:
            Path(filepath).unlink(missing_ok=True)
            self.log(f"✗ Erro na conversão pra MP3: {str(e)[:160]}")
            Path(audio_file).unlink(missing_ok=True)
            return False

    def _tags_da_faixa(self, filepath, song, artist, album, year, numero, total, meta, capa, output_dir):
        """Tags (metadata_manager.gravar_tags), capa e IDs do Discogs da faixa."""
        meta = meta or {}
        time.sleep(0.2)                         # o ffmpeg acabou de fechar o arquivo
        if not gravar_tags(filepath, song, artist, album, numero, total, ano=year or '',
                           artista_album=meta.get('album_artist') or artist, genero=meta.get('genre') or '',
                           capa=capa if capa.exists() else None):
            self.log("⚠ Erro ao adicionar metadados")
            return
        self.log("✓ Metadados adicionados")
        master_id, release_id = meta.get('discogs_master_id'), meta.get('discogs_release_id')
        if master_id or release_id:
            self.metadata_manager.add_discogs_ids(str(filepath), master_id=master_id, release_id=release_id)
            self.log(f"   🏷️  Discogs master_id={master_id or '-'} release_id={release_id or '-'}")
            if self._ensure_acervo_and_queue():
                self.acervo_index.add(master_id or release_id, output_dir.name, release_id=release_id)

    def _match_playlist_track(self, video_title, playlist_position, playlist_metadata,
                              audio_duration=None, duracao_video=None):
        """
        Casa um vídeo da playlist com a faixa da tracklist oficial do Discogs.

        Candidatas: faixas cujo título parece o do vídeo (comparação
        aproximada, artista na frente, títulos bilíngues com "=", "&" no
        lugar de "E"/"Y"). Entre elas vence a de duração compatível com o
        áudio (quando medida) e, depois, a de título mais longo - na "Aja" do
        Steely Dan o nome do álbum aparece em todo vídeo, e a faixa "Aja"
        venceria todas por ser a primeira.
        Sem casamento, o Groq pode sugerir, mas só vale se a duração do vídeo
        confirmar. Nunca inventa: sem nada, fica o título do vídeo.

        Devolve (título oficial, nº da faixa, casou?).
        """
        tracks = (playlist_metadata or {}).get('tracks') or []
        if not tracks:
            return None, playlist_position, False
        cleaned = video_title
        for ruido in ['(Official Audio)', '(Official Video)', '(Audio)', '(HD)',
                      '[Official Audio]', '[Audio]', '(Lyrics)', '(Full Song)']:
            cleaned = cleaned.replace(ruido, '').replace(ruido.lower(), '')
        cleaned = cleaned.strip()
        if '. ' in cleaned and cleaned.split('.')[0].strip().isdigit():
            cleaned = cleaned.split('. ', 1)[1]
        artista_pl = (playlist_metadata or {}).get('artist') or ''

        candidatos = []
        for idx, track in enumerate(tracks, 1):
            official = track.get('title', '')
            if not official or not (titles_similar(cleaned, official) or titles_similar(video_title, official)
                                    or nomes.titulos_casam(video_title, official, artista_pl)):
                continue
            esperada = track.get('duration', 0) or 0
            pontos, encaixe = len(official), None
            if audio_duration and esperada > 0:
                diff, tol = abs(audio_duration - esperada), max(15.0, esperada * 0.10)
                encaixe = (diff, tol)
                pontos += 1000 if diff <= tol else -500
            candidatos.append((pontos, idx, official, esperada, encaixe))

        if candidatos:
            candidatos.sort(reverse=True)
            _, idx, official, esperada, encaixe = candidatos[0]
            if len(candidatos) > 1:
                outros = ', '.join(f"'{x[2]}'" for x in candidatos[1:4])
                self.log(f"   🔎 '{official}' escolhida entre {len(candidatos)} faixas parecidas (as outras: {outros})")
            if encaixe:
                diff, tol = encaixe
                if diff > tol:
                    self.log(f"   ⚠️  Duração não bate: vídeo tem {audio_duration / 60:.1f}min, Discogs informa "
                             f"{esperada / 60:.1f}min pra '{official}' (diferença de {diff:.0f}s) - pode ser vídeo "
                             f"com intro, versão estendida ou faixa diferente")
                else:
                    self.log(f"   ✓ Duração confere com o Discogs ({audio_duration / 60:.1f}min)")
            if idx != playlist_position:
                self.log(f"   🔢 Faixa {idx} no Discogs (a playlist tinha na posição "
                         f"{playlist_position}) - usando a numeração do Discogs")
            self.log(f"   🏷️  Título oficial do Discogs: '{official}'")
            return official, idx, True

        ajuda = getattr(self, 'groq', None)
        if audio_duration is None and ajuda is not None and ajuda.disponivel():
            idx0 = ajuda.escolher_faixa(video_title, [t.get('title', '') for t in tracks], artista_pl)
            if idx0 is not None:
                oficial = tracks[idx0].get('title', '')
                esperada = tracks[idx0].get('duration', 0) or 0
                if duracao_video and esperada > 0 and abs(duracao_video - esperada) <= max(15.0, esperada * 0.10):
                    self.log(f"   🤖 Groq: '{video_title[:45]}' é '{oficial}' - e a duração confirma "
                             f"({duracao_video / 60:.1f}min × {esperada / 60:.1f}min)")
                    self._reg('AVISO', f"nome de faixa pelo Groq, confirmado pela duração: '{video_title}' -> '{oficial}'")
                    return oficial, idx0 + 1, True
                self.log(f"   🤖 Groq sugeriu '{oficial}', mas a duração não confirma - fica o título do vídeo")
        self.log(f"   ⚠️  '{cleaned[:45]}' não casou com nenhuma faixa da tracklist do Discogs - "
                 f"usando o título do vídeo e a posição na playlist")
        self._reg('AVISO', f"faixa de playlist sem casamento: '{video_title}' | tracklist: "
                           + ' / '.join(t.get('title', '') for t in tracks))
        return None, playlist_position, False

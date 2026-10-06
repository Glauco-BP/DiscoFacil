"""
Modo álbum: um vídeo do YouTube = um álbum inteiro.

process_single_video(url)
  1. Lê o vídeo e tira artista/álbum/ano do título (identificacao_titulo.py).
     Título sem nome de álbum: procura na descrição; senão, sugestão do Groq
     (só sugestão - quem confirma é o Discogs).
  2. Identifica no Discogs (catalogo.py), com as pistas do próprio vídeo:
     duração total e títulos dos capítulos/descrição.
     Não achou, limite de pedidos ou nota abaixo da mínima das Configurações
     -> vai pra "Precisam de você", sem baixar nada.
  3. _download_and_process: baixa (ou aproveita o download antecipado),
     afina as durações com o MusicBrainz (disco sem nenhuma duração: pega
     as do Deezer ou do iTunes), corta e grava (tags, IDs do Discogs, capa). Falhou o download ou o corte -> "Precisam de você".

_process_pending_video_item: o usuário mandou baixar uma pendência (ou
corrigiu o artista/álbum a buscar - 'busca_corrigida').
_resolver_sem_discogs: pendência "não encontrado" - Discogs de novo,
capítulos, tracklist da descrição, MusicBrainz e, por fim, só os silêncios.

Os "dados do álbum" que circulam entre as etapas são montados por
dados_para_corte(); as faixas vão em 'M:SS' (a duração exata, quando
existe, em 'duration_seconds').
"""
import os
import shutil
import time
from pathlib import Path

import edicao_cortes
import encaixe as ENC
import nomes
import saida
from audio_util import duracao_do_arquivo
from catalogo import inicios_de_texto, pistas_do_video
from corte_album import AlbumCutter
from corte_audio import esquecer_medidas
from corte_estrategias import match_durations_to_tracks
from pontuacao import (avaliar_identificacao, mesmo_disco, score_discogs_candidate, texto_identificacao,
                       titles_similar)
from util import onde_quebrou, segundos_da_faixa
from versao import APP_TITULO
from youtube_chapters_extractor import YouTubeChaptersExtractor

TAMANHO_MINIMO_ALBUM = 100_000
# Durações do Deezer/iTunes só valem se a soma delas bater com o áudio (mesma gravação).
DEEZER_SOMA_FOLGA_SEG = 20.0
DEEZER_SOMA_FOLGA_FRACAO = 0.05      # bytes: menos que isso é download quebrado
# Corte recusado e menos da metade das trocas de faixa caindo num silêncio:
# a pendência diz "provavelmente outro disco" (Ray Charles "Forever" foi
# identificado como a coletânea "Forever Gold", com a mesma duração total).
ENCAIXE_OUTRO_DISCO = 0.5
# Comentário com tempos só vale se pelo menos esta fração dos títulos bate com o Discogs, na mesma
# posição (e o primeiro e o último batem, e nunca dois seguidos sem bater)
COMENTARIO_TITULOS_MIN = 0.8


def _mss(segundos) -> str:
    s = int(round(segundos or 0))
    return f"{s // 60}:{s % 60:02d}" if s > 0 else "0:00"


def faixas_com_tempo_da_descricao(pistas, duracao_video):
    """
    Tracklist da descrição com tempos -> faixas com duração. Tempos
    crescentes a partir do zero ("00:00 A / 03:45 B") são INÍCIOS: a duração
    é a distância até o próximo (a última vai até o fim do vídeo). Senão,
    cada tempo já é a duração. None se faltar algum tempo ou der duração <= 0.
    """
    if not pistas or pistas.get('source') != 'YouTube Description':
        return None
    tempos = [t['duration'] for t in pistas['tracks']]
    if not tempos or any(t <= 0 for t in tempos[1:]):
        return None
    if tempos[0] < 30 and all(b > a for a, b in zip(tempos, tempos[1:])):
        fim = duracao_video or 0
        if fim <= tempos[-1]:
            return None
        tempos = [b - a for a, b in zip(tempos, tempos[1:] + [fim])]
    elif tempos[0] <= 0:
        return None
    return [{'title': t['title'], 'duration': d} for t, d in zip(pistas['tracks'], tempos)]


def dados_para_corte(resultado, artista, album, ano, fonte='Discogs', **extra):
    """
    Resultado de um catálogo (faixas com duração em segundos) -> dados do
    álbum no formato do corte. 'fonte' é o rótulo da capa no log.
    """
    faixas = []
    for i, t in enumerate(resultado.get('tracks') or [], 1):
        f = {'number': i, 'title': t.get('title') or '?', 'duration': _mss(segundos_da_faixa(t))}
        if t.get('duration_seconds'):
            f['duration_seconds'] = t['duration_seconds']
        faixas.append(f)
    dados = {
        'tracks': faixas,
        'title': resultado.get('title') or album,
        'artists': resultado.get('artists') or [artista],
        'year': resultado.get('year') or ano,
        'genre': resultado.get('genre'),
        'cover_image': resultado.get('cover_image'),
        'cover_source': fonte,
        'discogs_master_id': resultado.get('master_id'),
        'discogs_release_id': resultado.get('release_id'),
        'confidence_pct': resultado.get('confidence_pct', 0),
        'identificacao': resultado.get('identificacao'),
    }
    dados.update(extra)
    return dados


class AlbumMixin:
    """Um álbum num vídeo: identificar, baixar, cortar, gravar."""

    # ------------------------------------------------------------------ identificação
    def process_single_video(self, url):
        """Identifica o álbum do vídeo e, se der pra seguir sozinho, baixa e corta."""
        self._ensure_acervo_and_queue()
        self.log(f"\n{'=' * 60}")
        self.log("🚀 INICIANDO PROCESSAMENTO")
        self.log(f"{'=' * 60}")
        self.log(f"📌 {APP_TITULO}")
        self.log(f"URL: {url}")
        self.log(f"Horário: {time.strftime('%H:%M:%S')}\n")

        self.log("1. Obtendo informações...")
        video_info = self.downloader.get_video_info(url)
        if not video_info:
            self.log("✗ Falha")
            return
        self.log(f"✓ Título: {video_info['title']}")
        title_artist, title_album, year = self._artista_album_ano(video_info)

        # Pasta no formato antigo (Artista/Álbum) já com MP3: pula
        antiga = Path(self.config.get_output_directory()) / title_artist[:50] / title_album[:50]
        if antiga.exists() and list(antiga.glob("*.mp3")):
            self.log(f"\n⏭️  ÁLBUM JÁ EXISTE: {antiga}\n")
            return

        self.log("\n2. 🔎 Identificando álbum no Discogs...")
        pistas = pistas_do_video(video_info)
        titulos_video = [t['title'] for t in pistas['tracks'] if t.get('title')] if pistas else None
        candidatos = self._buscar_no_discogs(title_artist, title_album, video_info, titulos_video)
        escolhido = candidatos[0] if candidatos else None
        confianca = escolhido.get('confidence_pct', 0) if escolhido else 0
        # "não achou" é diferente de "o Discogs nem respondeu" (limite de pedidos)
        limite = not escolhido and getattr(self.catalogo, 'last_error', None) == 'rate_limited'

        if escolhido:
            self.log(f"  📀 Discogs... ✅ {len(escolhido['tracks'])} faixas | confiança: {confianca}%")
            self._reg('FONTE', self._descrever_fonte(escolhido, len(candidatos)))
        elif limite:
            porque = ("a conexão caiu" if getattr(self.catalogo, 'ultimo_erro_discogs', None) == 'conexão'
                      else "limite de requisições atingido")
            self.log(f"  📀 Discogs... ⏳ {porque} - não deu pra checar esse álbum agora (volta sozinho pra fila)")
        else:
            self.log("  📀 Discogs... ❌ álbum não encontrado")

        if not escolhido or confianca < self.AUTO_PROCESS_MIN_CONFIDENCE_PCT:
            if limite:
                kind = 'erro_discogs'
                if getattr(self.catalogo, 'ultimo_erro_discogs', None) == 'conexão':
                    reason = ("O Discogs não respondeu (a conexão caiu) - volta sozinho pra fila em 10 minutos")
                else:
                    reason = ("Limite de requisições do Discogs atingido - a busca não chegou a ser "
                              "respondida (tentar de novo deve resolver)")
            elif not escolhido:
                kind, reason = 'nao_encontrado', "Álbum não encontrado no Discogs"
            else:
                kind = 'baixa_confianca'
                reason = (f"Confiança {confianca}% abaixo do mínimo automático "
                          f"({self.AUTO_PROCESS_MIN_CONFIDENCE_PCT}%) - score={escolhido.get('score', 0):.0f}")
            self.pending_queue.add(kind=kind, url=url, video_title=video_info['title'],
                                   title_artist=title_artist, title_album=title_album, year=str(year or ''),
                                   confidence_pct=confianca, reason=reason, discogs_data=escolhido)
            self.log(f"\n⏸️  Adicionado à fila de pendentes ({confianca}% de confiança)")
            self.log(f"   Motivo: {reason}")
            self.log("   Abra 'Álbuns pendentes' para decidir se baixa ou descarta.\n")
            return

        if self._ja_no_acervo(escolhido):
            return

        dados = dados_para_corte(escolhido, title_artist, title_album, year,
                                 # a ordem DESTE vídeo (pra conferir o encaixe) e a
                                 # descrição (se o Groq precisar ler)
                                 ordem_do_video=titulos_video or None,
                                 titulo_buscado=title_album,
                                 descricao_video=(video_info.get('description') or '')[:4000])
        artist, album = ', '.join(dados['artists']), dados['title']
        self.log(f"\n✓ Identificado via Discogs: {album}")
        self.log(f"   Artista: {artist}")
        self.log(f"   {len(dados['tracks'])} faixas | {_mss(sum(segundos_da_faixa(t) for t in dados['tracks']))}")
        self.log("\n   Primeiras faixas:")
        for t in dados['tracks'][:3]:
            self.log(f"      {t['number']}. {t['title']} ({t['duration']})")
        if len(dados['tracks']) > 3:
            self.log(f"      ... e mais {len(dados['tracks']) - 3}")

        self._download_and_process(url, video_info, artist, album, dados['year'], 'discogs',
                                   dados['tracks'], True, dados, discogs_candidates=candidatos)

    def _artista_album_ano(self, video_info):
        """
        Artista, álbum e ano tirados do título. Título sem álbum ("Wes
        Montgomery (Jazz)"): o álbum vem da descrição ou, sem ela, da
        sugestão do Groq.
        """
        titulo = video_info['title']
        artista, album, ano = self._extract_artist(titulo), self._extract_album(titulo), self._extract_year(titulo)
        try:
            if not nomes.titulo_sem_album(artista, album):
                return artista, album, ano
            limpo = nomes.tirar_parenteses_genericos(artista) or artista
            descricao = video_info.get('description') or ''
            achado = nomes.album_da_descricao(descricao, limpo)
            if achado:
                self.log(f"   📝 O título não traz o álbum - achei na descrição: '{achado}' (artista: {limpo})")
                self._reg('FONTE', f"álbum lido da descrição: '{achado}' | artista '{limpo}' "
                                   f"| título do vídeo: {titulo}")
                return limpo, achado, ano
            self.log("   📝 O título não traz o nome do álbum, e a descrição também não")
            ajuda = getattr(self, 'groq', None)
            if ajuda is not None and ajuda.disponivel():
                sug = ajuda.album_do_titulo_e_descricao(titulo, descricao)
                if sug:
                    art = sug['artist'] or limpo
                    self.log(f"   🤖 Sugestão do Groq pra buscar: '{sug['album']}' ({art}) "
                             f"- vale só se o Discogs confirmar")
                    self._reg('FONTE', f"sugestão do Groq: álbum '{sug['album']}' | artista '{art}'")
                    return art, sug['album'], sug['year'] or ano
        except Exception as e:
            self.log(f"   ⚠️  Não consegui ler a descrição: {str(e)[:80]}")
        return artista, album, ano

    def _buscar_no_discogs(self, artista, album, video_info, titulos_video):
        """Todos os candidatos do Discogs (o 1º é o escolhido), ou []."""
        try:
            return self.catalogo.discogs(artista, album, reference_duration=video_info.get('duration'),
                                         reference_track_titles=titulos_video, log_func=self.log,
                                         return_all_candidates=True) or []
        except Exception as e:
            self.log(f"  📀 Discogs... ❌ ERRO: {e}")
            return []

    def _ja_no_acervo(self, resultado) -> bool:
        """O álbum (master do Discogs, ou release sem master) já está no acervo?"""
        chave = resultado.get('master_id') or resultado.get('release_id')
        if not (chave and self.acervo_index.has(chave)):
            return False
        self.log(f"\n⏭️  ÁLBUM JÁ ESTÁ NO ACERVO: {self.acervo_index.get(chave).get('folder', '?')}")
        self.log(f"   (Discogs {'master_id' if resultado.get('master_id') else 'release_id'} "
                 f"{chave} já indexado - pulando)\n")
        return True

    # ------------------------------------------------------------------ baixar e cortar
    def _download_and_process(self, url, video_info, artist, album, year,
                              final_source, final_tracks, has_timestamps,
                              discogs_data, discogs_candidates=None, from_pending=False,
                              allow_cross_validation=None, tempos_usuario=None):
        """
        Baixa, corta e grava. Devolve True se o álbum ficou pronto.

        from_pending: já é uma tentativa a partir de "Precisam de você" - se
        falhar, o item continua lá (não cria outro).
        allow_cross_validation: libera o último recurso do corte (nomes
        genéricos "Track N"). Padrão = from_pending; a pendência passa o valor
        certo, porque só quem caiu lá por CORTE que falhou deve usá-lo.
        tempos_usuario: texto com os tempos que o usuário informou em
        "Precisam de você" - vale antes de tudo.
        """
        if allow_cross_validation is None:
            allow_cross_validation = from_pending
        self._notas_corte = {}

        self.log("\n6. Baixando áudio...")
        temp_dir = Path(self.config.get_output_directory()) / "_temp"
        temp_dir.mkdir(exist_ok=True)
        audio_file = None
        try:
            if getattr(self, 'pre_download', None):
                audio_file = self.pre_download.pegar(url, mover_para=str(temp_dir))
                if audio_file:
                    self.log("✓ Áudio baixado")
        except Exception as e:
            self.log(f"   ⚠️  Download antecipado não aproveitado ({str(e)[:80]}) - baixando agora")
            audio_file = None
        if not audio_file:
            # áudio guardado quando o disco foi pra "Precisam de você" (ou baixado pelo ✂ Editar)
            guardado = edicao_cortes.audio_guardado(self.config.get_output_directory(), url)
            if guardado:
                try:
                    audio_file = str(temp_dir / guardado.name)
                    shutil.copy2(guardado, audio_file)
                    self.log("✓ Áudio guardado da pendência - sem baixar de novo")
                except OSError:
                    audio_file = None
        if not audio_file:
            audio_file = saida.baixar_audio(self.downloader, url, temp_dir, self.log, TAMANHO_MINIMO_ALBUM)

        if not audio_file:
            motivo = getattr(self.downloader, 'last_error', None) or "Vídeo privado, removido ou bloqueado"
            self.log("\n❌ FALHA NO DOWNLOAD")
            self.log(f"   URL: {url}")
            self.log(f"   💡 Motivo: {motivo}")
            self._cleanup_temp_dir(temp_dir)
            if not from_pending:
                self._pendencia_de_falha('falha_download', url, video_info, artist, album, year, discogs_data,
                                         f"Falha no download: {motivo}")
                self.log("   ⏸️  Adicionado à fila de pendentes para nova tentativa depois.\n")
            else:
                self.log("")
            return False

        self._antecipar_proximo(url)        # enquanto este é cortado, o próximo já vai baixando

        self.log(f"\n7. Processando separação (fonte: {final_source})...")
        base = Path(self.config.get_output_directory())
        nome = saida.nome_da_pasta(artist, album, year)
        output_dir, n = base / nome, 2
        while output_dir.exists() and list(output_dir.glob("*.mp3")):   # reedição: "(2)", "(3)"...
            output_dir, n = base / f"{nome} ({n})", n + 1
        output_dir.mkdir(parents=True, exist_ok=True)

        # Ajuste fino pelo MusicBrainz: um erro aqui nunca derruba o álbum.
        if final_source == "discogs" and discogs_data:
            try:
                discogs_data = self._refine_durations_with_musicbrainz(
                    discogs_data, artist, album, audio_file) or discogs_data
            except Exception as e:
                self.log(f"   ℹ️  MusicBrainz: ajuste pulado ({e}) - seguindo com as durações do Discogs")
        # Disco sem NENHUMA duração no Discogs/MusicBrainz: tenta Deezer e iTunes.
        if final_source == "discogs" and discogs_data and not any(
                segundos_da_faixa(t) > 0 for t in discogs_data.get('tracks') or []):
            try:
                self._duracoes_de_fora(discogs_data, artist, album, audio_file)
            except Exception as e:
                self.log(f"   ℹ️  Deezer/iTunes: consulta pulada ({str(e)[:60]} [{onde_quebrou(e)}])")

        def separar(fonte, faixas, candidatos=None, cv=allow_cross_validation):
            return self._process_separation_by_source(audio_file, fonte, faixas, True, discogs_data, video_info,
                                                      output_dir, discogs_candidates=candidatos,
                                                      allow_cross_validation=cv)

        # Ordem: (1) capítulos do vídeo com os nomes do Discogs - posições
        # reais, sem a deriva da soma de durações; (2) a edição que encaixa
        # no áudio; (3) capítulos sozinhos; (4) só os silêncios, com os nomes
        # casados pela duração (mesmo fora de ordem).
        ok = None
        capitulos = YouTubeChaptersExtractor.extract_from_video_info(video_info) if video_info else None
        duracao_video = (video_info or {}).get('duration') or self._medir_duracao_audio(audio_file)

        def nas_posicoes(lista, marcar, exato=False):
            return self._process_separation_by_source(audio_file, 'posicoes', lista, True, discogs_data, video_info,
                                                      output_dir, marcar_sem_silencio=marcar, exato=exato)
        if tempos_usuario:
            lista = self._faixas_dos_tempos(tempos_usuario, discogs_data, duracao_video)
            exato = tempos_usuario.lstrip().startswith('#exato')       # cortes marcados no ✂ Editar
            if exato and not lista:
                self.log("   ⚠️  Não consegui ler os cortes salvos no ✂ Editar - o disco continua em "
                         "\"Precisam de você\" (abra o ✂ Editar de novo e salve)")
                final_source, capitulos, discogs_candidates = 'editor', None, None
            if lista:
                self.log(f"\n✍️  {'Cortes marcados por você no ✂ Editar' if exato else 'Tempos informados por você'}: "
                         f"{len(lista)} faixas")
                self._reg('FONTE', f"{'cortes do editor' if exato else 'tempos informados pelo usuário'} | "
                                   f"{len(lista)} faixas")
                ok = nas_posicoes(lista, marcar=False, exato=exato)
                if exato and not ok:
                    # os cortes do editor são a última palavra: sem eles, nada de outro corte por conta própria
                    self.log("   ⚠️  Os cortes do ✂ Editar não puderam ser aplicados - o disco continua em "
                             "\"Precisam de você\"")
                    final_source, capitulos, discogs_candidates = 'editor', None, None
            else:
                self.log("\n⚠️  Não entendi os tempos informados (precisa de uma linha por faixa com o tempo) - "
                         "seguindo pelo caminho normal")
        comentarios_vistos = False
        sem_duracoes = bool(final_source == "discogs" and discogs_data and not any(
            segundos_da_faixa(t) > 0 for t in discogs_data.get('tracks') or []))
        if not ok and not capitulos and sem_duracoes:
            # sem durações em lugar nenhum: os tempos que alguém postou nos comentários
            comentarios_vistos = True
            lista = self._tempos_dos_comentarios(url, discogs_data, duracao_video)
            if lista:
                ok = nas_posicoes(lista, marcar=True)
        if not ok and allow_cross_validation and final_source == "discogs" and discogs_candidates:
            # "processar mesmo assim": antes dos nomes genéricos, outra edição que case com o áudio
            ok, output_dir, discogs_data = self._tentar_outra_edicao(audio_file, video_info, artist, year, discogs_data,
                                                                    discogs_candidates, output_dir)
        if not ok and final_source == "discogs" and discogs_data and capitulos:
            self.log(f"\n🎯 Vídeo tem {len(capitulos)} chapters - conferindo contra o Discogs...")
            juntos = self._merge_chapters_with_discogs(capitulos, discogs_data)
            if juntos:
                ok = separar("youtube_chapters", juntos, discogs_candidates)
                if ok:
                    self.log("✅ Cortado pelas posições dos chapters (sem depender da soma de durações)")
        if not ok and final_source != 'editor':
            ok = self._process_separation_by_source(
                audio_file, final_source, final_tracks, has_timestamps, discogs_data, video_info, output_dir,
                discogs_candidates=discogs_candidates, allow_cross_validation=allow_cross_validation)
        if not ok and final_source == "discogs" and discogs_data and not capitulos and not comentarios_vistos:
            # o corte falhou (músicas sem pausa entre elas): os tempos dos comentários
            comentarios_vistos = True
            lista = self._tempos_dos_comentarios(url, discogs_data, duracao_video)
            if lista:
                ok = nas_posicoes(lista, marcar=True)
        if not ok and final_source == "discogs":
            self.log("\n📍 Tentando fallback sem Discogs...")
            if capitulos:
                self.log(f"✓ {len(capitulos)} chapters encontrados")
                ok = separar("youtube_chapters", capitulos)
            if not ok and not allow_cross_validation:
                ok = separar("silencio_nomes", final_tracks, discogs_candidates, cv=False)

        if not ok and final_source == "discogs" and discogs_candidates and not allow_cross_validation:
            ok, output_dir, discogs_data = self._tentar_outra_edicao(audio_file, video_info, artist, year, discogs_data,
                                                                    discogs_candidates, output_dir)

        notas = getattr(self, '_notas_corte', None) or {}
        if ok:
            self._reg('NOTAS', self._texto_notas(discogs_data, notas, 'cortado'))
            edicao_cortes.esquecer_audio(self.config.get_output_directory(), url)
            self.log("\n✓ Processamento concluído!")
            self.log(f"   📁 {output_dir}")
            self._cleanup_temp_dir(temp_dir)
            return True

        self.log("✗ Falha ao processar separação")
        self.log("")
        self.log("💡 Este álbum pode ser:")
        self.log("   • Vinil antigo com ruído constante")
        self.log("   • Faixas sem silêncios entre elas")
        self.log("   • Áudio de baixa qualidade")
        self.log("   • Uma edição diferente da que o Discogs encontrou (nº de faixas não bate)")
        if output_dir.exists():
            try:
                shutil.rmtree(output_dir)
                self.log(f"\n🗑️  Pasta deletada: {output_dir}")
            except Exception as e:
                self.log(f"   ⚠️  Erro ao deletar pasta: {e}")
        self._reg('NOTAS', self._texto_notas(discogs_data, notas, 'recusado'))
        try:
            # guardado pro ✂ Editar de "Precisam de você" (sem baixar de novo)
            guardado = edicao_cortes.guardar_audio(self.config.get_output_directory(), url, audio_file)
            if guardado:
                self.log(f"   💾 Áudio guardado em {edicao_cortes.PASTA_AUDIOS} pra você conferir os cortes (✂ Editar)")
                # os silêncios já medidos vão junto: o ✂ Editar abre mais rápido
                cache = getattr(self, '_cache_gaps', None)
                st = os.stat(audio_file)
                if cache and cache[0] == (str(audio_file), st.st_size, int(st.st_mtime)):
                    edicao_cortes.gravar_medidas(
                        edicao_cortes.arquivo_de_medidas(self.config.get_output_directory(), url), guardado,
                        gaps=cache[1])
        except OSError as e:
            self.log(f"   ⚠️  Áudio não guardado ({str(e)[:60]})")
        if not from_pending:
            motivo = notas.get('motivo') or "Corte não bateu com as faixas do Discogs (pode ser edição diferente)"
            kind = 'falha_corte'
            acertos, fronteiras = notas.get('encaixe_medido') or (0, 0)
            if fronteiras and acertos / fronteiras < ENCAIXE_OUTRO_DISCO:
                # a maioria das músicas não cai em silêncio nenhum: o disco
                # identificado provavelmente não é o do vídeo
                kind = 'outro_disco'
                motivo = (f"Provavelmente é outro disco: só {acertos} de {fronteiras} trocas de faixa do Discogs "
                          f"caem num silêncio do áudio - use ✏️ Corrigir busca")
                self.log(f"   🤔 {motivo}")
            self._pendencia_de_falha(
                kind, url, video_info, artist, album, year, discogs_data,
                motivo + (" - use ✂ Editar pra ouvir e acertar os cortes, ou Enfileirar pra processar mesmo "
                          "assim (as emendas saem pela duração, a conferir)"
                          if any(segundos_da_faixa(t) > 0 for t in (discogs_data or {}).get('tracks') or [])
                          else " - use ✂ Editar pra ouvir e marcar os cortes, ou Enfileirar pra processar mesmo "
                               "assim (nomes genéricos: Track 1, Track 2...)"),
                # as edições candidatas vão junto: a nova tentativa não refaz a busca
                candidatas=list(discogs_candidates or [])[:20], notas=notas)
            self.log("   ⏸️  Adicionado à fila de pendentes para decidir depois.\n")
        self._cleanup_temp_dir(temp_dir)
        return False

    def _tentar_outra_edicao(self, audio_file, video_info, artist, year, discogs_data, candidatos, output_dir):
        """
        Último passo antes de desistir: outra edição da busca, com o título
        exato do vídeo, que case com os pedaços do áudio
        (escolha_edicao._reidentificar_pelo_audio). Achou: corta com ela numa
        pasta com o nome dela. Devolve (ok, pasta, dados do álbum).
        """
        try:
            cutter = AlbumCutter(artist=artist, album='', audio_file=str(audio_file), metadata={'tracks': []},
                                 output_dir=str(output_dir), log_func=self.log)
            achado = self._reidentificar_pelo_audio(cutter, discogs_data, candidatos)
        except Exception as e:
            self.log(f"   ⚠️  Não deu pra procurar outra edição pelo áudio ({str(e)[:80]} [{onde_quebrou(e)}])")
            achado = None
        if not achado:
            self.log("   ℹ️  Outra edição pelo áudio: nenhuma com o título do vídeo casou com os pedaços")
            return False, output_dir, discogs_data
        novo, faltam = achado
        dados = dados_para_corte(novo, artist, (discogs_data or {}).get('title', ''), year,
                                 titulo_buscado=(discogs_data or {}).get('titulo_buscado'))
        self.log(f"\n🔁 O áudio bate com outra edição da busca: '{dados['title']}' ({dados['year'] or '?'}, "
                 f"Discogs {dados['discogs_release_id']}) - cada faixa casada pela duração")
        if faltam:
            self.log(f"   ℹ️  O vídeo não tem a(s) última(s) faixa(s) do cadastro: {', '.join(faltam)}")
        self._reg('FONTE', f"outra edição, casada pelo áudio: Discogs {dados['discogs_release_id']} "
                           f"'{dados['title']}' ({dados['year']}) | {len(dados['tracks'])} faixas"
                           + (f" | faltam no vídeo: {', '.join(faltam)}" if faltam else ''))
        if self._ja_no_acervo(novo):
            shutil.rmtree(output_dir, ignore_errors=True)
            return True, output_dir, dados
        shutil.rmtree(output_dir, ignore_errors=True)
        nova_pasta = Path(self.config.get_output_directory()) / saida.nome_da_pasta(
            ', '.join(dados['artists']), dados['title'], dados['year'])
        nova_pasta.mkdir(parents=True, exist_ok=True)
        ok = self._process_separation_by_source(audio_file, 'discogs', dados['tracks'], True, dados, video_info,
                                                nova_pasta, discogs_candidates=None, allow_cross_validation=False)
        if not ok:
            shutil.rmtree(nova_pasta, ignore_errors=True)
            Path(output_dir).mkdir(parents=True, exist_ok=True)     # as próximas tentativas usam a pasta
            return False, output_dir, discogs_data
        return True, nova_pasta, dados

    def _pendencia_de_falha(self, kind, url, video_info, artist, album, year, discogs_data, reason, **extra):
        """Manda pra "Precisam de você" um álbum já identificado que falhou ao baixar ou cortar."""
        self.pending_queue.add(
            kind=kind, url=url, video_title=(video_info or {}).get('title', album),
            title_artist=artist, title_album=album, year=str(year or ''),
            confidence_pct=(discogs_data or {}).get('confidence_pct', 0),
            reason=reason, discogs_data=self._discogs_data_to_raw_shape(discogs_data), **extra)

    # ------------------------------------------------------------------ pendências
    def _process_pending_video_item(self, item) -> bool:
        """
        "Baixar" numa pendência de vídeo. True = sai da lista (pronto ou já
        no acervo); False = continua lá.
        """
        url = item['url']
        self.log(f"\n▶ Processando pendente: {item['video_title']}")
        video_info = self.downloader.get_video_info(url)
        if not video_info:
            self.log("   ✗ Não foi possível obter informações do vídeo (removido/privado?)")
            return False

        item = dict(item)       # cópia: uma tentativa que falha não muda o que está salvo
        if item.get('editor_sem_discogs') and (item.get('tempos_usuario') or '').lstrip().startswith('#exato'):
            # salvo no ✂ Editar sem disco do Discogs confirmado: o palpite guardado (que pode ser outro
            # disco) não entra; artista/álbum/ano e os nomes são os que você deixou no editor
            artist, album, year = item.get('title_artist') or '', item.get('title_album') or '', item.get('year') or ''
            self.log(f"   ✂️  Cortes e nomes do ✂ Editar, sem o Discogs: '{artist}' – '{album}'")
            dados = dados_para_corte({}, artist, album, year, fonte='YouTube')
            return self._download_and_process(url, video_info, artist, album, year, 'editor', [], False, dados,
                                              from_pending=True, tempos_usuario=item['tempos_usuario'])
        if item.get('busca_corrigida'):
            # nomes digitados pelo usuário: busca refeita, e ele já decidiu baixar
            self.log(f"   ✏️  Busca corrigida por você: '{item['title_artist']}' – '{item['title_album']}'")
            (artist, album, year, fonte, faixas, has_timestamps, dados, candidatos) = self._resolver_sem_discogs(
                video_info, item['title_artist'], item['title_album'], item.get('year', ''))
            return self._download_and_process(url, video_info, artist, album, year, fonte, faixas, has_timestamps,
                                              dados, discogs_candidates=candidatos, from_pending=True,
                                              tempos_usuario=item.get('tempos_usuario'))
        if item['kind'] == 'erro_discogs':
            # Da outra vez o Discogs nem respondeu: tenta ele de novo primeiro.
            self.log("   🔁 Tentando o Discogs de novo...")
            pistas = pistas_do_video(video_info)
            titulos = [t['title'] for t in pistas['tracks'] if t.get('title')] if pistas else None
            cands = self._buscar_no_discogs(item['title_artist'], item['title_album'], video_info, titulos)
            novo = cands[0] if cands else None
            conf = novo.get('confidence_pct', 0) if novo else 0
            if novo and conf >= self.AUTO_PROCESS_MIN_CONFIDENCE_PCT:
                self.log(f"   ✅ Discogs encontrou dessa vez: {len(novo['tracks'])} faixas | confiança: {conf}%")
                item['kind'], item['discogs_data'] = 'baixa_confianca', novo
            elif getattr(self.catalogo, 'last_error', None) == 'rate_limited':
                self.log("   ⏳ O Discogs ainda não respondeu - deixa na fila e tenta de novo daqui a pouco")
                return False
            else:
                self.log("   ⚠️  Discogs não confirmou dessa vez - seguindo pelo caminho sem Discogs")
                item['kind'] = 'nao_encontrado'

        guardado = item.get('discogs_data')
        if item['kind'] in ('baixa_confianca', 'falha_download', 'falha_corte', 'outro_disco') and guardado:
            if self._ja_no_acervo(guardado):
                return True
            dados = dados_para_corte(guardado, item['title_artist'], item['title_album'], item['year'],
                                     confidence_pct=guardado.get('confidence_pct', item.get('confidence_pct', 0)),
                                     titulo_buscado=guardado.get('titulo_buscado') or item['title_album'])
            candidatas = item.get('candidatas') or None
            if candidatas:
                self.log(f"   📚 {len(candidatas)} edição(ões) candidata(s) guardada(s) com o item - "
                         f"sem refazer a busca")
            return self._download_and_process(
                url, video_info, ', '.join(dados['artists']), dados['title'], dados['year'],
                'discogs', dados['tracks'], True, dados, discogs_candidates=candidatas, from_pending=True,
                tempos_usuario=item.get('tempos_usuario'),
                # nomes genéricos só pra quem caiu aqui porque o CORTE falhou
                allow_cross_validation=(item['kind'] in ('falha_corte', 'outro_disco')))

        (artist, album, year, fonte, faixas, has_timestamps, dados, candidatos) = self._resolver_sem_discogs(
            video_info, item['title_artist'], item['title_album'], item['year'])
        return self._download_and_process(url, video_info, artist, album, year, fonte, faixas, has_timestamps,
                                          dados, discogs_candidates=candidatos, from_pending=True,
                                              tempos_usuario=item.get('tempos_usuario'))

    def _resolver_sem_discogs(self, video_info, title_artist, title_album, year):
        """
        Pendência "não encontrado" que o usuário mandou baixar. Tenta, nesta
        ordem: Discogs de novo (qualquer nota - o usuário decidiu), capítulos
        do vídeo, tracklist com tempos na descrição, MusicBrainz e, por fim,
        só os silêncios (nomes "Track N").

        Devolve (artist, album, year, fonte, faixas, has_timestamps, dados,
        candidatos), os argumentos de _download_and_process.
        """
        self.log("\n2. 🔎 Caminho sem Discogs confirmado")
        pistas = pistas_do_video(video_info)
        titulos = [t['title'] for t in pistas['tracks'] if t.get('title')] if pistas else None
        cands = self._buscar_no_discogs(title_artist, title_album, video_info, titulos)
        if cands:
            dados = dados_para_corte(cands[0], title_artist, title_album, year)
            self.log(f"   📀 Discogs: {len(dados['tracks'])} faixas | confiança {dados['confidence_pct']}%")
            self._reg('FONTE', self._descrever_fonte(cands[0], len(cands)))
            return (', '.join(dados['artists']), dados['title'], dados['year'], 'discogs', dados['tracks'],
                    True, dados, cands)

        def usar(resultado, fonte, rotulo):
            dados = dados_para_corte(resultado, title_artist, title_album, year, fonte=rotulo)
            self.log(f"   ✓ {rotulo}: {len(dados['tracks'])} faixas")
            self._reg('FONTE', f"{rotulo} | {len(dados['tracks'])} faixas | {title_artist} - {title_album}")
            return title_artist, title_album, year, fonte, dados['tracks'], True, dados, None

        capitulos = YouTubeChaptersExtractor.extract_from_video_info(video_info)
        if capitulos:
            return usar({'tracks': capitulos}, 'youtube_chapters', 'capítulos do vídeo')
        da_descricao = faixas_com_tempo_da_descricao(pistas, video_info.get('duration'))
        if da_descricao:
            return usar({'tracks': da_descricao}, 'description', 'tracklist da descrição')
        try:
            mb = self.catalogo.musicbrainz(nomes.nome_artista_exibicao(title_artist), title_album)
        except Exception:
            mb = None
        if mb and mb.get('tracks'):
            faixas = [dict(t, duration_seconds=t.get('duration_exact') or t.get('duration')) for t in mb['tracks']]
            return usar({'tracks': faixas}, 'musicbrainz', 'MusicBrainz')
        self.log(f"   ℹ️  MusicBrainz: {getattr(self.catalogo, 'ultimo_motivo_mb', None) or 'sem dados'}")
        self.log("   ✂️  Nenhuma lista de faixas - corte só pelos silêncios (Track 1, Track 2...)")
        self._reg('FONTE', f"só silêncios | {title_artist} - {title_album}")
        dados = dados_para_corte({}, title_artist, title_album, year, fonte='YouTube')
        return title_artist, title_album, year, 'silence_only', [], False, dados, None

    def _discogs_data_to_raw_shape(self, discogs_data):
        """Dados do álbum ('M:SS') -> formato salvo nas pendências (segundos, chaves do catálogo)."""
        if not discogs_data:
            return None
        return {
            'tracks': [{'title': t.get('title'), 'duration': int(round(segundos_da_faixa(t)))}
                       for t in discogs_data.get('tracks', [])],
            'title': discogs_data.get('title'),
            'artists': discogs_data.get('artists'),
            'year': discogs_data.get('year'),
            'genre': discogs_data.get('genre'),
            'cover_image': discogs_data.get('cover_image'),
            'master_id': discogs_data.get('discogs_master_id'),
            'release_id': discogs_data.get('discogs_release_id'),
            'confidence_pct': discogs_data.get('confidence_pct', 0),
            'identificacao': discogs_data.get('identificacao'),
            'titulo_buscado': discogs_data.get('titulo_buscado'),
        }

    # ------------------------------------------------------------------ durações
    def _refine_durations_with_musicbrainz(self, discogs_data, artist, album, audio_file=None):
        """
        Troca as durações do Discogs ("M:SS", digitadas da capa) pelas do
        MusicBrainz (milissegundos, do índice do CD) quando estas encaixam
        CLARAMENTE melhor no áudio medido: pelo menos 5s e 30% menos erro na
        soma. Quem decide é o áudio, não o catálogo (no "Hollywood Dream" o
        Discogs dizia 3:15 e a gravação tinha ~3:25).
        Só vale com o mesmo nº de faixas e títulos parecidos; senão, mantém.
        """
        if not discogs_data or not artist or not album:
            return discogs_data
        faixas = discogs_data.get('tracks') or []
        if not faixas or not getattr(self, 'catalogo', None):
            return discogs_data
        try:
            mb = self.catalogo.musicbrainz(artist, album, n_faixas=len(faixas))
        except Exception:
            mb = None
        if not mb or not mb.get('tracks'):
            motivo = getattr(self.catalogo, 'ultimo_motivo_mb', None) or "sem dados"
            self.log(f"   ℹ️  MusicBrainz: {motivo} - seguindo com as durações do Discogs")
            return discogs_data
        faixas_mb = mb['tracks']
        if len(faixas_mb) != len(faixas):
            self.log(f"   ℹ️  MusicBrainz: {len(faixas_mb)} faixas contra {len(faixas)} do "
                     f"Discogs - seguindo com o Discogs")
            return discogs_data
        for i, faixa in enumerate(faixas):
            if not titles_similar(faixa.get('title', ''), faixas_mb[i].get('title', '')):
                self.log(f"   ℹ️  MusicBrainz achou o álbum mas os títulos divergem "
                         f"(faixa {i + 1}) - mantendo as durações do Discogs")
                return discogs_data

        soma_disc = sum(segundos_da_faixa(f) for f in faixas)
        soma_mb = sum(float(f.get('duration_exact', 0) or 0) for f in faixas_mb)
        if soma_mb <= 0 or soma_disc <= 0:
            return discogs_data
        real = self._medir_duracao_audio(audio_file) if audio_file else None
        if not real or real <= 0:
            self.log("   ℹ️  Não consegui medir o áudio pra comparar as duas fontes - mantendo o Discogs")
            return discogs_data
        erro_disc, erro_mb = abs(soma_disc - real), abs(soma_mb - real)
        self.log(f"   📏 Somas contra o áudio real ({real:.0f}s): "
                 f"Discogs erra {erro_disc:.0f}s, MusicBrainz erra {erro_mb:.0f}s")
        if erro_mb < erro_disc - 5.0 and erro_mb < erro_disc * 0.7:
            for i, faixa in enumerate(faixas):
                exata = float(faixas_mb[i].get('duration_exact', 0) or 0)
                if exata > 0:
                    # o exato vai em 'duration_seconds' (o corte lê primeiro);
                    # 'duration' mantém o tipo que já tinha
                    faixa['duration_seconds'] = exata
                    faixa['duration'] = _mss(exata) if isinstance(faixa.get('duration'), str) else exata
            self.log(f"   🎯 Usando as durações do MusicBrainz: encaixam "
                     f"{erro_disc - erro_mb:.0f}s melhor no áudio real")
        else:
            self.log("   ↩️  Discogs continua tão bom ou melhor - mantendo")
        return discogs_data

    # lojas consultadas, em ordem: (nome no log, método do Catalogo, motivo da falha)
    LOJAS_DE_DURACOES = (('Deezer', 'deezer', 'ultimo_motivo_deezer'),
                         ('iTunes', 'itunes', 'ultimo_motivo_itunes'))

    def _duracoes_de_fora(self, discogs_data, artist, album, audio_file=None):
        """
        Disco sem nenhuma duração no Discogs nem no MusicBrainz (Neco, "Coquetel
        Bossa Nova"; Os Cobras): pega as do Deezer e, se não der, as do iTunes.
        Os NOMES continuam os do Discogs; a loja só entra se todos os títulos
        casarem (edição com faixas bônus a mais serve) e a soma bater com o
        áudio. Preenche as faixas de discogs_data no lugar (são as mesmas que
        vão pro corte). True se usou.
        """
        faixas = discogs_data.get('tracks') or []
        cat = getattr(self, 'catalogo', None)
        if not faixas or cat is None:
            return False
        titulos = [t.get('title') or '' for t in faixas]
        real = self._medir_duracao_audio(audio_file) if audio_file else None
        for nome, metodo, motivo_attr in self.LOJAS_DE_DURACOES:
            if not hasattr(cat, metodo):
                continue
            r = getattr(cat, metodo)(artist, album, titulos)
            if not r or len(r.get('tracks') or []) != len(faixas):
                self.log(f"   ℹ️  {nome}: {getattr(cat, motivo_attr, None) or 'sem dados'} - sem durações daqui")
                continue
            soma = sum(t['duration_exact'] for t in r['tracks'])
            if real and real > 0 and abs(soma - real) > max(DEEZER_SOMA_FOLGA_SEG, DEEZER_SOMA_FOLGA_FRACAO * real):
                self.log(f"   ℹ️  {nome}: achou o álbum, mas a soma ({_mss(soma)}) não bate com o áudio "
                         f"({_mss(real)}) - pode ser outra gravação")
                continue
            for faixa, t in zip(faixas, r['tracks']):
                faixa['duration_seconds'] = t['duration_exact']
                faixa['duration'] = _mss(t['duration_exact']) if isinstance(faixa.get('duration'), str) else t['duration']
            discogs_data['fonte_duracoes'] = nome
            bonus = f", edição com {r['faixas_a_mais']} faixa(s) a mais" if r.get('faixas_a_mais') else ''
            if r.get('pela_posicao'):
                bonus += "; pela posição: " + '; '.join(f"'{d}' = '{l}'" for d, l in r['pela_posicao'])
            self.log(f"   🎵 {nome}: durações das {len(faixas)} faixas (álbum {r.get('album_id')}{bonus}, soma "
                     f"{_mss(soma)}) - os nomes continuam os do Discogs")
            self._reg('FONTE', f"durações do {nome} (álbum {r.get('album_id')}): o Discogs não as informa")
            return True
        self.log("   ℹ️  Disco segue sem durações")
        return False

    def _medir_duracao_audio(self, audio_file):
        """Duração real do arquivo (ffprobe), ou None."""
        return duracao_do_arquivo(audio_file) if audio_file else None

    # ------------------------------------------------------------------ tempos (comentários, usuário)
    def _faixas_dos_tempos(self, texto, discogs_data, duracao_video):
        """
        Texto com tempos (colado pelo usuário) -> faixas pra cortar nas posições.
        Nomes: linha com nome escrito = a faixa do Discogs com esse nome (grafia
        oficial), senão o nome escrito; linha sem nome = o Discogs na mesma
        posição se o nº de linhas bate, senão "Track N". None se o texto não
        tem uma lista de tempos.
        """
        exatos = edicao_cortes.ler_tempos_exatos(texto)
        if exatos is not None:
            # cortes do ✂ Editar: os nomes são os da tabela, como estão (já vêm do Discogs ou de você)
            return self._com_duracoes(exatos, [x['title'] or f'Track {i + 1}' for i, x in enumerate(exatos)],
                                      duracao_video)
        if (texto or '').lstrip().startswith('#exato'):
            return None
        lista = inicios_de_texto(texto, duracao_video)
        if not lista:
            return None
        oficiais = [t.get('title') for t in (discogs_data or {}).get('tracks') or []
                    if (t.get('title') or '?') != '?']
        mesma_contagem = len(oficiais) == len(lista)
        livres = list(range(len(oficiais)))
        titulos = []
        for i, x in enumerate(lista):
            escrito = (x['title'] or '').strip()
            if escrito:
                # o nome escrito decide QUAL faixa é; o Discogs só dá a grafia oficial
                k = next((k for k in livres if nomes.titulos_casam(escrito, oficiais[k])), None)
                if k is not None:
                    livres.remove(k)
                titulos.append(oficiais[k] if k is not None else escrito)
            else:
                titulos.append(oficiais[i] if mesma_contagem else f'Track {i + 1}')
        if oficiais and not mesma_contagem:
            self.log(f"   ℹ️  {len(lista)} tempos e {len(oficiais)} faixas no Discogs - "
                     f"os nomes vêm do que está escrito na lista")
        return self._com_duracoes(lista, titulos, duracao_video)

    @staticmethod
    def _com_duracoes(lista, titulos, duracao_video):
        fins = [x['start_time'] for x in lista[1:]] + [duracao_video or lista[-1]['start_time']]
        return [{'number': i + 1, 'title': titulos[i], 'start_time': x['start_time'],
                 'duration_seconds': max(0.0, fim - x['start_time'])}
                for i, (x, fim) in enumerate(zip(lista, fins))]

    def _tempos_dos_comentarios(self, url, discogs_data, duracao_video):
        """
        Procura nos comentários mais curtidos do vídeo uma tracklist com tempos
        ("0:00 Música 1 / 3:12 Música 2…") que seja ESTE disco: o mesmo nº de
        faixas do Discogs, pelo menos COMENTARIO_TITULOS_MIN dos títulos
        batendo na mesma posição (primeiro e último inclusive, nunca dois
        seguidos sem bater) e, se o Discogs tem durações, as durações
        parecidas (como os capítulos). O corte ainda confere os tempos com as
        pausas do áudio (cut_at_positions). Devolve as faixas com os nomes do
        Discogs, ou None.
        """
        oficiais = (discogs_data or {}).get('tracks') or []
        baixador = getattr(self, 'downloader', None)
        if len(oficiais) < 2 or not url or baixador is None or not hasattr(baixador, 'comentarios'):
            return None
        self.log("\n💬 Procurando os tempos das faixas nos comentários do vídeo...")
        try:
            textos = baixador.comentarios(url)
        except Exception as e:
            textos = None
            self.log(f"   ℹ️  Comentários não lidos ({str(e)[:60]})")
        if not textos:
            self.log("   ℹ️  Nenhum comentário lido")
            return None
        n = len(oficiais)
        melhor = None
        for texto in textos:
            lista = inicios_de_texto(texto, duracao_video)
            if not lista or len(lista) != n:
                continue
            casa = [nomes.titulos_casam(x['title'], o.get('title') or '') for x, o in zip(lista, oficiais)]
            batem = sum(casa)
            # a lista tem de ser ESTE disco, na mesma ordem: quase todos os títulos batendo na posição,
            # o primeiro e o último inclusive, e nunca dois seguidos sem bater (faixa pulada desloca o resto)
            if (batem < max(2, n * COMENTARIO_TITULOS_MIN) or not casa[0] or not casa[-1]
                    or any(not a and not b for a, b in zip(casa, casa[1:]))):
                continue
            faixas = self._com_duracoes(lista, [o.get('title') for o in oficiais], duracao_video)
            longe = [i for i, (f, o) in enumerate(zip(faixas, oficiais))
                     if segundos_da_faixa(o) > 0
                     and abs(f['duration_seconds'] - segundos_da_faixa(o)) > max(15.0, 0.12 * segundos_da_faixa(o))]
            if len(longe) > max(1, n // 4):
                continue
            if melhor is None or batem > melhor[0]:
                melhor = (batem, faixas)
        if not melhor:
            self.log(f"   ℹ️  {len(textos)} comentário(s) lido(s), nenhum com os tempos das {n} faixas deste disco")
            return None
        self.log(f"   ✅ Um comentário tem os tempos das {n} faixas ({melhor[0]}/{n} títulos batem com o Discogs)")
        self._reg('FONTE', f"tempos de um comentário do vídeo | {n} faixas, {melhor[0]}/{n} títulos batem")
        return melhor[1]

    def _merge_chapters_with_discogs(self, chapters, discogs_data):
        """
        POSIÇÕES dos capítulos (marcadas neste upload, sem soma de durações)
        + NOMES do Discogs (o oficial, não o que o uploader digitou). Faixa
        sem duração no Discogs só leva o nome oficial se o capítulo tiver o
        mesmo nome; senão fica o do capítulo.
        Só junta com o mesmo nº de faixas e durações parecidas (no máximo 1/4
        das faixas fora de max(15s, 12%)); senão é outra edição: None.
        """
        if not chapters or not discogs_data:
            return None
        faixas = discogs_data.get('tracks') or []
        if not faixas:
            return None
        if len(chapters) != len(faixas):
            self.log(f"   ⚠️  Chapters ({len(chapters)}) e Discogs ({len(faixas)}) "
                     f"discordam no número de faixas - não vou misturar as duas fontes")
            return None
        divergencias = []
        for i, cap in enumerate(chapters):
            dur_cap = cap.get('duration_seconds', 0) or 0
            dur_disc = segundos_da_faixa(faixas[i])
            if dur_cap > 0 and dur_disc > 0 and abs(dur_cap - dur_disc) > max(15.0, dur_disc * 0.12):
                divergencias.append((i + 1, dur_cap, dur_disc, abs(dur_cap - dur_disc)))
        if len(divergencias) > max(1, len(chapters) // 4):
            self.log(f"   ⚠️  {len(divergencias)} faixa(s) com duração bem diferente entre "
                     f"chapters e Discogs - provavelmente edições diferentes, não vou misturar")
            for n, dc, dd, diff in divergencias[:3]:
                self.log(f"      Faixa {n}: chapter {dc}s vs Discogs {dd}s ({diff:.0f}s de diferença)")
            return None
        if divergencias:
            self.log(f"   ℹ️  {len(divergencias)} faixa(s) com duração um pouco diferente - "
                     f"dentro do aceitável, seguindo com as posições dos chapters")
        def nome(i, cap):
            oficial = (faixas[i].get('title') or '').strip()
            if not oficial or oficial == '?':
                return cap.get('title', f'Track {i + 1}')
            # sem duração no Discogs nada confere a posição: o nome do capítulo tem de ser o mesmo
            if segundos_da_faixa(faixas[i]) <= 0 and not nomes.titulos_casam(cap.get('title') or '', oficial):
                return cap.get('title') or f'Track {i + 1}'
            return oficial
        juntos = [{'number': i + 1,
                   'title': nome(i, cap),
                   'start_time': cap.get('start_time', 0), 'end_time': cap.get('end_time', 0),
                   'duration': cap.get('duration', ''), 'duration_seconds': cap.get('duration_seconds', 0)}
                  for i, cap in enumerate(chapters)]
        self.log(f"   ✅ Posições dos chapters + títulos do Discogs ({len(juntos)} faixas)")
        return juntos

    # ------------------------------------------------------------------ corte
    def _process_separation_by_source(self, audio_file, source, tracks, has_timestamps, discogs_data,
                                      video_info=None, output_dir=None, discogs_candidates=None,
                                      allow_cross_validation=False, marcar_sem_silencio=True, exato=False):
        """
        Corta o áudio e grava as faixas. Devolve True, ou None se não deu.

        source: 'discogs' (escolhe a edição que encaixa, escolha_edicao.py),
        'silencio_nomes' (só silêncios, nomes casados pela duração),
        'posicoes' (tracks com 'start_time': tempos de um comentário ou do
        usuário; marcar_sem_silencio marca as fronteiras sem silêncio) ou
        qualquer outra (capítulos, descrição, MusicBrainz, só silêncios:
        estratégias de corte_estrategias.py). has_timestamps: não usado
        (mantido pela assinatura).
        """
        self.log(f"\n7. Processando separação (fonte: {source})...")
        dd = discogs_data or {}
        artist = (dd.get('artists') or ['Unknown'])[0]
        album = dd.get('title', 'Unknown')
        metadata = {
            'tracks': [{'number': i, 'title': t.get('title', f'Track {i}'), 'duration': segundos_da_faixa(t)}
                       for i, t in enumerate(tracks or [], 1)],
            'artist': artist,
            'album': dd.get('title', 'Unknown Album'),
            'year': dd.get('year', ''),
            # TPE2: o 1º artista oficial agrupa as faixas mesmo com participações
            'album_artist': artist if discogs_data else None,
            'genre': dd.get('genre'),
        }
        output_dir = str(output_dir) if output_dir else str(
            Path(self.config.get_output_directory()) / saida.nome_da_pasta(artist, album))
        try:
            cutter = AlbumCutter(artist=artist, album=album, audio_file=str(audio_file), metadata=metadata,
                                 output_dir=output_dir, log_func=self.log, catalogo=getattr(self, 'catalogo', None))
            self.log("   🔍 MEGA DETECTOR: Detectando gaps...")
            all_gaps = self._gaps_do_audio(cutter)
            self.log(f"   ✓ {sum(len(g) for g in all_gaps.values())} gaps detectados em {len(all_gaps)} métodos")

            self.log("   ✂️  SMART CUTTER: Decidindo estratégia...")
            tem_duracoes = bool(metadata['tracks']) and all(t['duration'] > 0 for t in metadata['tracks'])
            if source == 'posicoes':
                # tempos de um comentário do vídeo ou digitados pelo usuário
                # tempos de comentário (marcados) são conferidos com as pausas; os do usuário valem como estão
                if not cutter.cortar_nas_posicoes(all_gaps, [t['start_time'] for t in tracks],
                                                  [t['title'] for t in tracks], marcar_sem_silencio,
                                                  conferir_com_pausas=marcar_sem_silencio, exato=exato):
                    return None
                discogs_candidates = None
            elif source == 'silencio_nomes':
                cuts = self._cortar_pelos_silencios_com_nomes(cutter, all_gaps, metadata, discogs_data,
                                                             discogs_candidates)
                if not cuts:
                    return None
                cutter.cuts = cuts
                discogs_candidates = None           # nomes já casados pela duração
            elif source == 'discogs' and tem_duracoes and not allow_cross_validation:
                try:
                    escolha = self._cortar_pela_melhor_edicao(cutter, all_gaps, metadata, discogs_data,
                                                              discogs_candidates)
                except Exception as e:
                    # um erro na escolha por encaixe nunca derruba o álbum
                    self.log(f"   ⚠️  Encaixe não pôde ser avaliado ({str(e)[:80]} [{onde_quebrou(e)}]) "
                             f"- seguindo pelo corte normal")
                    escolha = ({'cuts': cutter.cuts, 'fonte': None, 'trocou': False}
                               if cutter.smart_cut(all_gaps, allow_cross_validation=False) else None)
                if not escolha:
                    self.log("   ✗ Smart cut falhou")
                    return None
                cutter.cuts = escolha['cuts']
                if escolha['trocou']:
                    f = escolha['fonte']
                    metadata = dict(metadata, tracks=escolha['metadata']['tracks'])
                    cutter.metadata = metadata
                    if f['origem'] == 'discogs' and f['cand']:
                        c = f['cand']
                        discogs_data = dict(dd, discogs_master_id=c.get('master_id') or dd.get('discogs_master_id'),
                                            discogs_release_id=c.get('release_id'))
                        if c.get('cover_image'):
                            discogs_data['cover_image'] = c['cover_image']
                        self.log(f"   🔄 Edição trocada pela que encaixa: Discogs release {c.get('release_id')}")
                    discogs_candidates = None       # escolha feita faixa a faixa: não reavalia pela soma
            elif (source == 'discogs' and allow_cross_validation and metadata['tracks'] and not tem_duracoes
                  and (cuts := self._cortar_pelos_silencios_com_nomes(cutter, all_gaps, metadata, discogs_data,
                                                                     discogs_candidates))):
                # pendência "processar mesmo assim" de disco sem durações: antes do
                # "Track N", tenta os nomes pela ordem (palpite marcado)
                cutter.cuts = cuts
                discogs_candidates = None
            elif not cutter.smart_cut(all_gaps, allow_cross_validation=allow_cross_validation):
                self.log("   ✗ Smart cut falhou")
                return None

            estimadas = [c['track'] for c in cutter.cuts or [] if c.get('corte_estimado')]
            if estimadas:
                self.log(f"   ⚠️  Faixa(s) {estimadas}: corte estimado pela duração (músicas emendadas) - "
                         f"vale ouvir a emenda")
                self._reg('AVISO', f"corte estimado pela duração (conferir): faixas {estimadas}")

            if discogs_candidates and len(discogs_candidates) > 1 and cutter.cuts:
                try:
                    discogs_data = self._reavaliar_com_o_corte(cutter, metadata, discogs_data,
                                                               discogs_candidates, video_info)
                except Exception as e:
                    self.log(f"   ⚠️  Reavaliação não pôde ser feita: {str(e)[:80]}")

            self.log("   ✂️  Cortando faixas...")
            if not cutter.cut_tracks():
                self.log("   ✗ Falha ao cortar faixas")
                return None
            self.log("   🏷️  Adicionando tags...")
            cutter.add_tags()
            self._gravar_ids_e_capa(output_dir, discogs_data, video_info)
            self.log(f"✓ Separação concluída: {len(cutter.cuts)} faixas")
            self.log(f"   📁 {output_dir}")
            return True
        except Exception as e:
            self.log(f"✗ Erro na separação: {e} [{onde_quebrou(e)}]")
            return None

    def _reavaliar_com_o_corte(self, cutter, metadata, discogs_data, candidatos, video_info):
        """
        ESCOLHA RETARDADA: com o nº REAL de faixas e a duração REAL de cada
        uma (medidas no corte), repontua as edições do MESMO disco
        (pontuacao.mesmo_disco) que a busca trouxe; a melhor vira a fonte de
        capa, IDs e nomes. Outro disco da busca nunca entra, mesmo encaixando
        melhor ("Vê" virou "Aos Amigos Tom, Chico e Vinicius"; "Os Cobras"
        virou "Cobras Criadas"). Trocar de edição exige ainda que a nova
        passe na identificação contra o vídeo.

        Os arquivos já cortados só recebem os nomes da escolhida com prova
        pela duração: nº igual e cada pedaço casando com a sua faixa, ou a
        soma de faixas vizinhas fechando com cada pedaço (~2s). Sem isso
        ficam como estão (nome errado é pior que genérico). Devolve os dados.
        """
        cortes = cutter.cuts
        fim_video = (video_info or {}).get('duration')
        reais = [max(0, (c['end'] if c.get('end') is not None else (fim_video or c.get('start', 0)))
                     - c.get('start', 0)) for c in cortes]
        n_real, total_real = len(cortes), sum(reais)
        dd = discogs_data or {}
        ref = {'title': dd.get('title'), 'artists': dd.get('artists'), 'master_id': dd.get('discogs_master_id')}
        mesmos = [c for c in candidatos if mesmo_disco(ref, c)]
        fora = len(candidatos) - len(mesmos)
        self.log(f"   🔁 Reavaliando a edição com dados reais do corte ({n_real} faixas, {total_real:.0f}s "
                 f"medidos), só entre as {len(mesmos)} edição(ões) do mesmo disco"
                 + (f" - {fora} outro(s) disco(s) da busca ficam de fora" if fora else ""))
        if not mesmos:
            return dd

        def titulo(c):
            return c.get('album_title') or c.get('title')
        notas = sorted(((c, score_discogs_candidate(
            {'tracks': c['tracks'], 'track_count': len(c['tracks']), 'year': c.get('year'), 'is_compilation': False,
             'album_title': titulo(c)},
            reference_duration=total_real, reference_track_count=n_real,
            search_album_title=dd.get('title'), search_artist_name=(dd.get('artists') or [None])[0],
            log_func=self.log)) for c in mesmos), key=lambda x: x[1], reverse=True)
        melhor, nota = notas[0]

        empatados = [c for c, s in notas if abs(s - nota) <= 1.0]
        if len(empatados) > 1:
            def erro_medio(c):
                d = [abs(reais[i] - c['tracks'][i].get('duration', 0))
                     for i in range(min(len(reais), len(c['tracks']))) if c['tracks'][i].get('duration', 0) > 0]
                return sum(d) / len(d) if d else float('inf')
            ajustes = sorted(((c, erro_medio(c)) for c in empatados), key=lambda x: x[1])
            melhor_erro, pior_erro = ajustes[0][1], ajustes[-1][1]
            if melhor_erro < float('inf') and pior_erro - melhor_erro > 0.5:
                self.log(f"   🔬 Desempate fino por faixa entre {len(empatados)} edições empatadas em "
                         f"~{nota:.1f} pts: erro médio de {melhor_erro:.1f}s/faixa na escolhida")
                melhor = ajustes[0][0]
            elif melhor_erro < float('inf'):
                self.log(f"   🔬 {len(empatados)} edições empatadas em ~{nota:.1f} pts, todas com o mesmo "
                         f"encaixe por faixa (~{melhor_erro:.1f}s) - entradas duplicadas da mesma gravação")

        rid = dd.get('discogs_release_id')
        original = next((c for c in mesmos if rid and c.get('release_id') == rid), None)
        if rid and melhor.get('release_id') != rid:
            ident = avaliar_identificacao(
                dict(melhor, album_title=titulo(melhor)), reference_duration=total_real,
                search_album_title=dd.get('titulo_buscado') or dd.get('title'),
                search_artist_name=(dd.get('artists') or [None])[0])
            minimo = getattr(self, 'AUTO_PROCESS_MIN_CONFIDENCE_PCT', 80)
            if ident['nota'] < minimo:
                self.log(f"   ↩️  A edição {melhor.get('release_id')} encaixaria melhor, mas não passa na "
                         f"identificação ({texto_identificacao(ident)}; mínimo {minimo}%) - fica a escolhida")
                if original is None:
                    return dd
                melhor = original
        if rid and melhor.get('release_id') != rid:
            self.log(f"   🔄 Outra edição do mesmo disco: Discogs {rid} → {melhor.get('release_id')} "
                     f"('{titulo(melhor)}', bate melhor com o áudio real)")
        else:
            self.log("   ✓ Edição escolhida confirmada com dados reais")
        # o candidato traz 'master_id'/'release_id'; a gravação lê com o prefixo
        novo = dict(melhor, discogs_master_id=melhor.get('master_id'), discogs_release_id=melhor.get('release_id'))
        if not novo.get('title'):
            novo['title'] = titulo(melhor)
        metadata['artist'] = (melhor.get('artists') or [metadata['artist']])[0]
        metadata['album'] = novo.get('title') or metadata['album']
        # ano: o do lançamento (já escolhido pela busca), não o da reedição que casou melhor
        metadata['year'] = dd.get('year') or melhor.get('year', metadata['year'])
        if dd.get('year'):
            novo['year'] = dd['year']

        faixas = melhor['tracks']
        durs = [segundos_da_faixa(f) for f in faixas]
        com_duracoes = bool(durs) and all(d > 0 for d in durs)
        if not com_duracoes:
            self.log("   ℹ️  A edição não tem durações: os nomes dos arquivos ficam como saíram do corte")
        elif len(faixas) == n_real:
            m = ENC.casar_por_duracao(reais, durs)
            if m and m['faixa_de'] == list(range(n_real)):
                trocados = 0
                for c, f in zip(cortes, faixas):
                    tit_f = f.get('title')
                    if tit_f and tit_f != '?' and c.get('title') != tit_f:
                        c['title'] = tit_f
                        trocados += 1
                if trocados:
                    self.log(f"   ✏️  Nomes aplicados a {trocados} arquivo(s): cada pedaço casa com a sua faixa "
                             f"(pior diferença {m['pior_erro']:.1f}s)")
            else:
                self.log("   ⚠️  Mesmo nº de faixas, mas as durações não casam uma a uma - os nomes ficam "
                         "como saíram do corte")
        else:
            self.log(f"   🧮 Diferença de {abs(len(faixas) - n_real)} faixas - tentando casar durações "
                     f"reais com as esperadas antes de desistir dos nomes (margem baixa, ~2s)...")
            grupos = match_durations_to_tracks(reais, durs, base_tolerance=2.0)
            if grupos:
                trocados = 0
                for c, g in zip(cortes, grupos):
                    titulos = [faixas[k].get('title') for k in g if faixas[k].get('title') not in (None, '', '?')]
                    if titulos and c.get('title') != ' / '.join(titulos):
                        c['title'] = ' / '.join(titulos)
                        trocados += 1
                grudados = sum(1 for g in grupos if len(g) > 1)
                extra = f" ({grudados} arquivo(s) com faixas grudadas, nome composto)" if grudados else ""
                self.log(f"   ✅ Casamento por duração bateu certinho! Nomes aplicados a {trocados} arquivo(s){extra}")
            else:
                self.log(f"   ⚠️  Mantendo os nomes do corte: a edição tem {len(faixas)} faixas, o corte deu "
                         f"{n_real} pedaço(s), e a aritmética de duração não fechou - nomear arriscaria "
                         f"juntar faixas erradas")
        metadata['tracks'] = [{'number': k + 1,
                               'title': (faixas[k].get('title') if k < len(faixas) else None) or f'Track {k + 1}',
                               'duration': faixas[k].get('duration', 0) if k < len(faixas) else 0}
                              for k in range(n_real)]
        cutter.metadata = metadata
        return novo

    def _gravar_ids_e_capa(self, output_dir, discogs_data, video_info):
        """IDs do Discogs (TXXX, base do "já está no acervo?") e capa (Discogs; senão, a miniatura do vídeo)."""
        dd = discogs_data or {}
        master_id, release_id = dd.get('discogs_master_id'), dd.get('discogs_release_id')
        if master_id or release_id:
            n = sum(1 for f in Path(output_dir).glob("*.mp3")
                    if self.metadata_manager.add_discogs_ids(str(f), master_id=master_id, release_id=release_id))
            self.log(f"   🏷️  Discogs master_id={master_id or '-'} release_id={release_id or '-'} "
                     f"gravado em {n} faixa(s)")
            self.acervo_index.add(master_id or release_id, Path(output_dir).name, release_id=release_id)
        capa = Path(output_dir) / "cover.jpg"
        ok = saida.baixar_capa(dd.get('cover_image'), capa, self.log, dd.get('cover_source') or 'Discogs')
        if not ok and video_info and video_info.get('thumbnail'):
            ok = saida.baixar_capa(video_info['thumbnail'], capa, self.log, 'YouTube')
        if ok:
            falhas = saida.embutir_capa(output_dir, capa) or []
            if falhas:
                self.log(f"   ⚠️  A capa não entrou em {len(falhas)} arquivo(s) (aberto noutro programa?): "
                         f"{', '.join(falhas[:4])}{' ...' if len(falhas) > 4 else ''}")
                self._reg('AVISO', f"capa não gravada em {len(falhas)} arquivo(s): {', '.join(falhas[:10])}")

    def _cleanup_temp_dir(self, temp_dir):
        """Apaga a pasta temporária do download e libera as medidas do áudio."""
        esquecer_medidas()
        try:
            if temp_dir.exists():
                self.log("\n🗑️  Limpando pasta temporária...")
                shutil.rmtree(temp_dir)
                self.log("   ✓ Pasta _temp removida")
        except Exception as e:
            self.log(f"   ⚠️  Erro ao limpar pasta temporária: {e}")

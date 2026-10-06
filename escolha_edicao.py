"""
Identificação × encaixe (mixin EdicaoMixin).

Identificar ("é este o álbum?") é a nota do Discogs; ENCAIXAR ("as durações
deste cadastro servem pra cortar ESTE áudio?") é medido faixa a faixa contra
os silêncios reais (encaixe.py). Aqui se escolhe, entre a edição escolhida,
as outras edições do mesmo álbum e as do MusicBrainz, a que encaixa; empate
desempata pelo MusicBrainz; a ordem da descrição do vídeo também é testada.
Sem encaixe bom: corta pelos silêncios e casa os nomes pela duração
(_cortar_pelos_silencios_com_nomes), ou recusa com o motivo.
"""
import os

import encaixe as ENC
import nomes
from ajustes import CutTuning
from corte_estrategias import SmartCutter
from pontuacao import (album_title_similarity, artistas_parecidos, mesmo_disco, palavras_a_mais,
                       texto_identificacao)


class EdicaoMixin:
    """Identificação × encaixe: qual edição serve pra cortar este áudio."""

    @staticmethod
    def _texto_notas(discogs_data, notas, resultado):
        """Linha de resumo "resultado | identificação | encaixe | usada | motivo" pro histórico."""
        ident = (discogs_data or {}).get('identificacao')
        if isinstance(ident, dict):
            t_ident = texto_identificacao(ident)
        else:
            t_ident = f"{(discogs_data or {}).get('confidence_pct', '?')}%"
        partes = [f"{resultado}", f"identificação {t_ident}",
                  f"encaixe da escolhida: {notas.get('encaixe_escolhida', '-')}"]
        if notas.get('encaixe_usada'):
            partes.append(f"usada: {notas['encaixe_usada']}")
        if notas.get('motivo'):
            partes.append(f"motivo: {notas['motivo']}")
        return ' | '.join(partes)

    def _gaps_do_audio(self, cutter):
        """Detecção de silêncios uma vez por arquivo (a passada seguinte reaproveita)."""
        try:
            st = os.stat(cutter.audio_file)
            chave = (str(cutter.audio_file), st.st_size, int(st.st_mtime))
        except Exception:
            chave = None
        cache = getattr(self, '_cache_gaps', None)
        if chave and cache and cache[0] == chave:
            self.log("   ♻️  Silêncios já detectados neste áudio - reaproveitando")
            return cache[1]
        g = cutter.detect_gaps()
        if chave:
            self._cache_gaps = (chave, g)
        return g

    def _novo_cortador(self, cutter, metadata, all_gaps, base=None):
        """SmartCutter pra uma tentativa, reaproveitando o áudio já decodificado."""
        sc = SmartCutter(metadata, all_gaps, cutter.audio_file, log_func=self.log,
                         catalogo=self.catalogo, artist=cutter.artist, album=cutter.album)
        if base is not None:
            for k in ('_rms_audio_cache', '_env_cache', '_cached_total_duration',
                      '_initial_silence_offset_cache'):
                if getattr(base, k, None) is not None:
                    setattr(sc, k, getattr(base, k))
        return sc

    @staticmethod
    def _faixas_para_corte(faixas):
        """Converte faixas de qualquer fonte no formato do SmartCutter (number/title/duration em s)."""
        return [{'number': i, 'title': (t.get('title') or f'Track {i}'),
                 'duration': ENC.segundos(t)} for i, t in enumerate(faixas, 1)]

    def _silencios_para_encaixe(self, sc, n_fronteiras):
        """
        Posições de silêncio usadas pra medir o encaixe: só os clusters com votos
        suficientes, se houver ao menos metade das fronteiras; senão, todos.
        """
        clusters = sc.cluster_gaps()
        fortes = [c['position'] for c in clusters if c['votes'] >= CutTuning.MIN_VOTES_TO_TRUST]
        if len(fortes) >= max(1, n_fronteiras // 2):
            return fortes
        return [c['position'] for c in clusters]

    def _nomes_do_discogs_para(self, faixas_mb, faixas_discogs):
        """
        Edição do MusicBrainz: as durações vêm dela, os NOMES continuam do
        Discogs (casados pelo título, um pra um). Devolve None se menos de 70%
        casar - aí não é "a mesma lista de faixas".
        """
        livres = list(range(len(faixas_discogs)))
        nomes_out, casou = [], 0
        for t in faixas_mb:
            achou = None
            for j in livres:
                if nomes.titulos_casam(t.get('title', ''), faixas_discogs[j].get('title', '')):
                    achou = j
                    break
            if achou is not None:
                livres.remove(achou)
                casou += 1
                nomes_out.append(faixas_discogs[achou].get('title'))
            else:
                nomes_out.append(t.get('title'))
        if not faixas_mb or casou / len(faixas_mb) < 0.7:
            return None
        return nomes_out

    def _fontes_musicbrainz(self, cutter, faixas_escolhida, silencios, total, inicio):
        """
        Edições do MusicBrainz com o mesmo nº de faixas, já com nota de encaixe.
        Durações do MusicBrainz, nomes do Discogs; edições cujos títulos não
        batem são ignoradas. Devolve lista de fontes (vazia se nada útil).
        """
        fontes = []
        mh = getattr(self, 'catalogo', None)
        if mh is None or not hasattr(mh, 'musicbrainz_edicoes'):
            return fontes
        try:
            artista = nomes.nome_artista_exibicao(cutter.artist or '')
            edicoes = mh.musicbrainz_edicoes(artista, cutter.album or '', len(faixas_escolhida))
        except Exception as e:
            self.log(f"   ℹ️  MusicBrainz: não consultado ({str(e)[:60]})")
            return fontes
        if not edicoes:
            motivo = getattr(mh, 'ultimo_motivo_mb', None) or 'nada encontrado'
            self.log(f"   ℹ️  MusicBrainz: nenhuma edição útil ({motivo})")
            return fontes
        for ed in edicoes:
            if not mesmo_disco({'title': cutter.album or ''}, ed):
                self.log(f"   ℹ️  MusicBrainz {str(ed.get('release_id', '?'))[:8]} ('{ed.get('title')}'): "
                         f"outro disco - ignorada")
                continue
            nomes_ed = self._nomes_do_discogs_para(ed['tracks'], faixas_escolhida)
            if nomes_ed is None:
                self.log(f"   ℹ️  MusicBrainz {ed.get('release_id', '?')[:8]}: títulos não batem com o "
                         f"Discogs - ignorada")
                continue
            faixas = [{'title': n, 'duration_exact': ENC.segundos(t)} for n, t in zip(nomes_ed, ed['tracks'])]
            enc = ENC.nota_encaixe([ENC.segundos(t) for t in faixas], silencios, total, inicio)
            fontes.append({'rotulo': f"MusicBrainz {str(ed.get('release_id', '?'))[:8]}",
                           'origem': 'musicbrainz', 'cand': ed, 'faixas': faixas, 'enc': enc})
        return fontes

    def _fonte_na_ordem_do_video(self, discogs_data, faixas_escolhida, silencios, total, inicio):
        """As faixas do Discogs reordenadas como a descrição do vídeo lista (ou None)."""
        ordem = (discogs_data or {}).get('ordem_do_video')
        origem = 'descrição'
        if not ordem:
            ajuda = getattr(self, 'groq', None)
            desc = (discogs_data or {}).get('descricao_video')
            if ajuda is not None and ajuda.disponivel() and desc:
                ordem = ajuda.tracklist_da_descricao(desc)
                origem = 'descrição, lida pelo Groq'
                if ordem:
                    self.log(f"   🤖 Groq leu {len(ordem)} faixas na descrição (só pra conferir a ordem)")
        if not ordem or len(ordem) != len(faixas_escolhida):
            return None
        livres = list(range(len(faixas_escolhida)))
        nova = []
        for tit in ordem:
            j = next((k for k in livres if nomes.titulos_casam(tit, faixas_escolhida[k].get('title', ''))), None)
            if j is None:
                return None
            livres.remove(j)
            nova.append(faixas_escolhida[j])
        if [t.get('title') for t in nova] == [t.get('title') for t in faixas_escolhida]:
            return None                          # mesma ordem: nada novo a testar
        enc = ENC.nota_encaixe([ENC.segundos(t) for t in nova], silencios, total, inicio)
        return {'rotulo': f"Discogs na ordem do vídeo ({origem})", 'origem': 'discogs', 'cand': None,
                'faixas': [dict(t) for t in nova], 'enc': enc}

    def _desempate_musicbrainz(self, empatadas, cutter, faixas_escolhida, silencios, total, inicio):
        """Entre edições do Discogs com o mesmo encaixe, prefere a mais próxima do MusicBrainz."""
        mb = self._fontes_musicbrainz(cutter, faixas_escolhida, silencios, total, inicio)
        if not mb:
            return empatadas, mb

        def distancia(f):
            d1 = [ENC.segundos(t) for t in f['faixas']]
            melhor = None
            for m in mb:
                d2 = [ENC.segundos(t) for t in m['faixas']]
                if len(d1) == len(d2):
                    x = sum(abs(a - b) for a, b in zip(d1, d2)) / len(d1)
                    melhor = x if melhor is None else min(melhor, x)
            return melhor if melhor is not None else float('inf')
        ordenadas = sorted(empatadas, key=distancia)
        if ordenadas[0] is not empatadas[0]:
            self.log(f"   🧭 Desempate pelo MusicBrainz: {ordenadas[0]['rotulo']} tem as durações mais "
                     f"próximas das do MusicBrainz ({distancia(ordenadas[0]):.1f}s/faixa)")
        return ordenadas, mb

    def _cortar_pela_melhor_edicao(self, cutter, all_gaps, metadata, discogs_data, discogs_candidates):
        """
        Corta com a edição que melhor encaixa nos silêncios. Se a escolhida
        encaixa, usa ela; senão compara outras edições do mesmo álbum já
        trazidas pela busca, a ordem da descrição do vídeo e o MusicBrainz
        (também desempate). Nenhuma encaixa: tenta a escolhida mesmo assim.
        Devolve {'cuts', 'fonte', 'trocou', 'metadata'} ou None (motivo em _notas_corte).
        """
        base = self._novo_cortador(cutter, metadata, all_gaps)
        faixas_escolhida = [dict(t) for t in metadata['tracks']]
        n_front = max(0, len(faixas_escolhida) - 1)
        total = base._get_total_audio_duration() or 0
        inicio = base._get_initial_silence_offset() or 0
        silencios = self._silencios_para_encaixe(base, n_front)

        de_onde = (f" (escolhida, durações do {discogs_data['fonte_duracoes']})" if discogs_data.get('fonte_duracoes')
                   else " (escolhida)")
        escolhida = {'rotulo': f"Discogs {discogs_data.get('discogs_release_id') or '?'}{de_onde}",
                     'origem': 'discogs', 'cand': None, 'faixas': faixas_escolhida,
                     'enc': ENC.nota_encaixe([t['duration'] for t in faixas_escolhida], silencios, total, inicio)}
        fontes = [escolhida]
        ref = {'title': discogs_data.get('title'), 'artists': discogs_data.get('artists'),
               'master_id': discogs_data.get('discogs_master_id'),
               'release_id': discogs_data.get('discogs_release_id'), 'tracks': faixas_escolhida}
        for c in ENC.edicoes_do_mesmo_album(ref, discogs_candidates or []):
            faixas = [{'title': t.get('title'), 'duration': t.get('duration')} for t in c.get('tracks') or []]
            enc = ENC.nota_encaixe([ENC.segundos(t) for t in faixas], silencios, total, inicio)
            fontes.append({'rotulo': f"Discogs {c.get('release_id')}", 'origem': 'discogs', 'cand': c,
                           'faixas': faixas, 'enc': enc})

        self.log(f"\n🧩 Encaixe faixa a faixa ({len(silencios)} silêncios no áudio, janela "
                 f"±{ENC.JANELA_SEG:.0f}s):")
        for f in fontes:
            self.log(f"   • {f['rotulo']}: {len(f['faixas'])} faixas → {ENC.texto_encaixe(f['enc'])}")
        self._notas_corte = {'encaixe_escolhida': ENC.texto_encaixe(escolhida['enc'])}
        if not escolhida['enc']['sem_duracao']:
            self._notas_corte['encaixe_medido'] = (escolhida['enc']['acertos'], escolhida['enc']['fronteiras'])

        def passa(f):
            return not f['enc']['sem_duracao'] and f['enc']['nota'] >= ENC.ENCAIXE_BOM

        mb_buscado = []
        if not passa(escolhida):
            # a ordem do vídeo (descrição/chapters, ou lida pelo Groq) é só mais
            # uma opção: entra apenas se encaixar nos silêncios.
            fv = self._fonte_na_ordem_do_video(discogs_data, faixas_escolhida, silencios, total, inicio)
            if fv:
                self.log(f"   • {fv['rotulo']}: {len(fv['faixas'])} faixas → {ENC.texto_encaixe(fv['enc'])}")
                fontes.append(fv)
        if passa(escolhida):
            outras = sorted([f for f in fontes[1:] if passa(f)], key=lambda f: -f['enc']['nota'])
            ordem = [escolhida] + outras
        else:
            passam = sorted([f for f in fontes if passa(f)], key=lambda f: -f['enc']['nota'])
            if len(passam) > 1 and passam[0]['enc']['nota'] - passam[1]['enc']['nota'] <= ENC.DESEMPATE:
                empate = [f for f in passam if passam[0]['enc']['nota'] - f['enc']['nota'] <= ENC.DESEMPATE]
                empate, mb_buscado = self._desempate_musicbrainz(empate, cutter, faixas_escolhida,
                                                                 silencios, total, inicio)
                passam = empate + [f for f in passam if f not in empate]
            if not passam:
                self.log("   🔎 Nenhuma edição do Discogs encaixa - consultando o MusicBrainz...")
                mb_buscado = self._fontes_musicbrainz(cutter, faixas_escolhida, silencios, total, inicio)
                for f in mb_buscado:
                    self.log(f"   • {f['rotulo']}: {len(f['faixas'])} faixas → {ENC.texto_encaixe(f['enc'])}")
                passam = sorted([f for f in mb_buscado if passa(f)], key=lambda f: -f['enc']['nota'])
            if passam:
                self.log(f"   ✅ Melhor encaixe: {passam[0]['rotulo']} ({ENC.texto_encaixe(passam[0]['enc'])})")
                ordem = passam
            else:
                self.log("   ⚠️  Nenhuma edição encaixa - tentando o corte normal com a escolhida")
                ordem = [escolhida]

        for f in ordem[:3]:
            meta = dict(metadata)
            meta['tracks'] = self._faixas_para_corte(f['faixas'])
            if f is not escolhida:
                self.log(f"\n🔁 Cortando com {f['rotulo']} (encaixe {ENC.texto_encaixe(f['enc'])})")
            sc = self._novo_cortador(cutter, meta, all_gaps, base=base)
            cuts = sc.decide_and_cut(allow_cross_validation=False)
            if cuts:
                cuts = sc.ajustar_ao_inicio_da_proxima(cuts)
                self.log(f"\n📋 Resultado: {len(cuts)} faixas para cortar ({f['rotulo']})")
                self._notas_corte['encaixe_usada'] = f"{f['rotulo']}: {ENC.texto_encaixe(f['enc'])}"
                return {'cuts': cuts, 'fonte': f, 'trocou': f is not escolhida, 'metadata': meta}
            self.log(f"   ✗ {f['rotulo']}: o corte não confirmou")
        self._notas_corte['motivo'] = (
            f"Nenhuma edição serviu pra cortar (encaixe da escolhida: {ENC.texto_encaixe(escolhida['enc'])}; "
            f"{len(fontes) - 1} outra(s) edição(ões) do Discogs"
            + (f", {len(mb_buscado)} do MusicBrainz" if mb_buscado else '') + ")")
        return None

    def _reidentificar_pelo_audio(self, cutter, discogs_data, candidatos):
        """
        O disco escolhido não encaixou (outra coletânea com a mesma duração
        total, como "Forever Gold" no lugar de "Forever"). Procura, entre os
        candidatos da busca com EXATAMENTE o título do vídeo, um cujas
        durações casem com os pedaços do áudio (cortado só pelos silêncios),
        cada um dentro de 4s/3%. Aceita também o vídeo sem a(s) última(s)
        faixa(s) do cadastro, se a soma das primeiras fechar com o áudio.
        Devolve (candidato com as faixas na ordem do áudio, [faixas que faltam]) ou None.
        """
        buscado = ((discogs_data or {}).get('titulo_buscado') or '').strip()
        rid = (discogs_data or {}).get('discogs_release_id')
        if not buscado or not candidatos:
            return None
        opcoes = []
        for c in candidatos:
            tit = c.get('title') or c.get('album_title') or ''
            if c.get('release_id') == rid or not c.get('tracks'):
                continue
            if (album_title_similarity(buscado, tit) >= 0.99 and palavras_a_mais(buscado, tit)[0] >= 0.99
                    and artistas_parecidos((discogs_data or {}).get('artists'), c.get('artists'))):
                opcoes.append(c)
        if not opcoes:
            return None
        sc = SmartCutter({'tracks': []}, self._gaps_do_audio(cutter), cutter.audio_file,
                         log_func=lambda *a, **k: None)
        cuts = sc.cut_by_cross_validation()
        if not cuts:
            return None
        total = sc._get_total_audio_duration() or 0
        reais = [((c['end'] if c.get('end') is not None else total) - c['start']) for c in cuts]
        variantes = [reais]
        if any((c.get('votos') or 0) < 2 for c in cuts[:-1]):
            # sem as fronteiras achadas só por queda de volume (pausas dentro da música)
            juntos, acc = [], 0.0
            for c, d in zip(cuts, reais):
                acc += d
                if c is cuts[-1] or (c.get('votos') or 0) >= 2:
                    juntos.append(acc)
                    acc = 0.0
            variantes.append(juntos)
        melhor = None
        for c in opcoes:
            durs = [ENC.segundos(t) for t in c['tracks']]
            if any(d <= 0 for d in durs):
                continue
            for rs in variantes:
                n = len(rs)
                if len(durs) == n:
                    m, faltam = ENC.casar_por_duracao(rs, durs), []
                elif len(durs) > n and abs(sum(durs[:n]) - total) <= max(10.0, 0.02 * total):
                    m, faltam = ENC.casar_por_duracao(rs, durs[:n]), [t.get('title') for t in c['tracks'][n:]]
                else:
                    continue
                if m and (melhor is None or m['pior_erro'] < melhor[1]['pior_erro']):
                    melhor = (c, m, faltam)
        if not melhor:
            return None
        c, m, faltam = melhor
        return dict(c, tracks=[c['tracks'][j] for j in m['faixa_de']]), faltam

    def _nomes_por_ordem_sem_duracoes(self, base, cuts, reais, faixas):
        """
        Disco sem durações em lugar nenhum: junta os pedaços que sobram (os
        mais curtos, pela fronteira mais fraca - ENC.juntar_pedacos_curtos)
        até dar o nº de músicas e nomeia pela ORDEM do cadastro. É palpite:
        vai marcado "a conferir" no log, no arquivo da rodada e nas tags.
        Devolve os cortes ou None (sobra demais, ou pedaço longo demais pra juntar).
        """
        fronteiras = [{'votos': c.get('votos', 0), 'silencio': c.get('silencio', 0)} for c in cuts[:-1]]
        grupos = ENC.juntar_pedacos_curtos(reais, fronteiras, len(faixas))
        if not grupos:
            return None

        def mmss(s):
            return f"{int(s) // 60}:{int(s) % 60:02d}"

        self.log(f"   🤔 Sem durações em nenhuma fonte: {len(cuts)} pedaços → {len(faixas)} músicas, "
                 f"nomes pela ORDEM do Discogs (palpite - confira)")
        novos = []
        for i, g in enumerate(grupos):
            ultimo = cuts[g[-1]]
            titulo = (faixas[i].get('title') or '').strip()
            if not titulo or titulo == '?':
                titulo = f'Track {i + 1}'
            novos.append(dict(cuts[g[0]], track=i + 1, title=titulo, end=ultimo.get('end'),
                              votos=ultimo.get('votos', 0), silencio=ultimo.get('silencio', 0),
                              method='silencio+nome_por_ordem(palpite)', nome_palpite=True))
            if len(g) > 1:
                partes = ' + '.join(mmss(reais[j]) for j in g)
                self.log(f"      🔗 pedaços {'+'.join(str(j + 1) for j in g)} juntados ({partes}) → '{titulo}'")
        self._reg('AVISO', f"nomes por ordem, sem durações (conferir): {len(cuts)} pedaços → {len(faixas)} músicas; "
                           + '; '.join(f"{'+'.join(str(j + 1) for j in g)}={novos[i]['title']}"
                                       for i, g in enumerate(grupos) if len(g) > 1))
        novos = base.ajustar_ao_inicio_da_proxima(novos)
        self._notas_corte = dict(getattr(self, '_notas_corte', {}) or {},
                                 encaixe_usada="silêncios + nomes pela ordem (palpite, sem durações - conferir)")
        return novos

    def _cortar_pelos_silencios_com_nomes(self, cutter, all_gaps, metadata, discogs_data, discogs_candidates):
        """
        Último passo automático: corta só pelos silêncios e usa o Discogs só
        pros NOMES, casando cada pedaço com uma faixa pela duração (mesmo fora
        de ordem). Nº de pedaços diferente (duas músicas emendadas) ou durações
        que não casam: devolve None - nada sai com nome trocado.
        """
        self.log("\n🔇 Cortando só pelos silêncios e casando os nomes do Discogs pela duração...")
        # Só o NÚMERO de faixas do Discogs entra (completa fronteiras de LP com
        # chiado); sem durações, pois a conferência por posição recusaria
        # justamente faixas em outra ordem.
        meta_sil = dict(metadata, tracks=[dict(t, duration=0) for t in metadata['tracks']])
        base = self._novo_cortador(cutter, meta_sil, all_gaps)
        cuts = base.cut_by_cross_validation()
        if not cuts:
            self._notas_corte = dict(getattr(self, '_notas_corte', {}) or {},
                                     motivo="Os silêncios do áudio não deram pra separar as faixas")
            return None
        total = base._get_total_audio_duration() or 0
        reais = [((c['end'] if c.get('end') is not None else total) - c['start']) for c in cuts]
        ref = {'title': (discogs_data or {}).get('title'), 'artists': (discogs_data or {}).get('artists'),
               'master_id': (discogs_data or {}).get('discogs_master_id'),
               'release_id': (discogs_data or {}).get('discogs_release_id'),
               'tracks': metadata['tracks']}
        edicoes = [('Discogs (escolhida)', metadata['tracks'])] + [
            (f"Discogs {c.get('release_id')}", c.get('tracks') or [])
            for c in ENC.edicoes_do_mesmo_album(ref, discogs_candidates or [])]
        contagens = sorted({len(f) for _, f in edicoes})
        melhor = None
        for rot, faixas in edicoes:
            durs = [ENC.segundos(t) for t in faixas]
            m = ENC.casar_por_duracao(reais, durs)
            if m and (melhor is None or m['pior_erro'] < melhor[2]['pior_erro']):
                melhor = (rot, faixas, m)
        if melhor is None and not any(ENC.segundos(t) > 0 for _, f in edicoes for t in f):
            palpite = self._nomes_por_ordem_sem_duracoes(base, cuts, reais, metadata['tracks'])
            if palpite:
                return palpite
        if melhor is None:
            if not any(ENC.segundos(t) > 0 for t in metadata['tracks']):
                motivo = (f"O Discogs não informa as durações deste disco - sem elas não dá pra conferir "
                          f"o nome de cada pedaço (os silêncios dão {len(cuts)} faixas; o Discogs tem "
                          f"{len(metadata['tracks'])})")
            elif len(cuts) not in contagens:
                motivo = (f"O corte pelos silêncios achou {len(cuts)} faixas e o Discogs tem "
                          f"{'/'.join(map(str, contagens))} - pode haver duas músicas emendadas")
            else:
                motivo = (f"O corte pelos silêncios achou {len(cuts)} faixas, mas as durações não casam "
                          f"com as do Discogs (não dá pra saber o nome de cada uma)")
            self.log(f"   ✗ {motivo}")
            self._notas_corte = dict(getattr(self, '_notas_corte', {}) or {}, motivo=motivo)
            return None
        rot, faixas, m = melhor
        for i, c in enumerate(cuts):
            j = m['faixa_de'][i]
            c['title'] = faixas[j].get('title') or f'Track {i + 1}'
            c['track'] = i + 1
            c['method'] = f"silencio+nome_por_duracao({rot})"
        self.log(f"   ✅ {len(cuts)} pedaços = {len(faixas)} faixas de {rot}; cada nome casado pela duração "
                 f"(maior diferença {m['pior_erro']:.1f}s)")
        if m['fora_de_ordem']:
            self.log("   🔀 A ordem das faixas neste áudio é diferente da do cadastro - numeradas na ordem do áudio:")
            for i, c in enumerate(cuts):
                self.log(f"      {i + 1:2d}. {c['title']} (faixa {m['faixa_de'][i] + 1} no cadastro)")
        cuts = base.ajustar_ao_inicio_da_proxima(cuts)
        self._notas_corte = dict(getattr(self, '_notas_corte', {}) or {},
                                 encaixe_usada=f"silêncios + nomes por duração ({rot})")
        return cuts

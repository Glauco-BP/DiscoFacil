"""
SmartCutter: as 5 estratégias que decidem ONDE cortar (decide_and_cut tenta
nesta ordem e para na primeira que dá certo):
  1. MODO HÍBRIDO (cut_hybrid_with_validation): um silêncio por fronteira,
     conferido contra as durações do catálogo;
  2. PONTUAÇÃO (cut_directly_on_gaps): pontua os silêncios candidatos;
  3. COM DURAÇÕES (cut_with_durations): parte das durações e procura o
     silêncio real perto de cada fronteira (reataque local, "segunda opinião"
     do MusicBrainz pra uma faixa isolada; quando o usuário manda processar
     mesmo assim, até metade das fronteiras (no máximo 2 seguidas) vão pela
     duração, marcadas "conferir" - _estimar_fronteiras);
  4. ALINHAMENTO GLOBAL (cut_by_interval_alignment): compara INTERVALOS, não
     posições - resolve a deriva acumulada ao longo do disco;
  5. CONSENSO (cut_by_cross_validation): só o áudio, nomes "Track N" -
     último recurso, só quando o usuário manda processar mesmo assim (com o
     nº de músicas conhecido, nenhum pedaço < 60s). Disco COM durações só
     aceita o consenso se a contagem bater e os nomes entrarem.
Depois: ajustar_ao_inicio_da_proxima (corte no começo real da próxima faixa).
match_durations_to_tracks: casa pedaços cortados com faixas pela soma das
durações (faixas grudadas viram "A / B"). Limiares em ajustes.CutTuning.
"""
from typing import Dict, List, Optional

from ajustes import CutTuning
from audio_util import FFPROBE_PATH, _subprocess_no_window_kwargs
from corte_audio import AnaliseDeAudio, duracao_do_silencio
from util import segundos_da_faixa
from pontuacao import titles_similar

# Consenso com os nomes do cadastro: cada pedaço a até max(isto, 5%) da duração da sua faixa
CONSENSO_NOMES_FOLGA_SEC = 8.0


def match_durations_to_tracks(real_durations: List[float], expected_durations: List[float],
                               base_tolerance: float = 2.0, max_group_size: int = 5) -> Optional[List[List[int]]]:
    """
    Deduz quais faixas esperadas caíram em cada pedaço real já cortado, só
    pela soma das durações (ex.: pedaço de 6:00 = faixas 1+2+3 grudadas).

    Busca (com poda) uma partição EXATA e em ordem de `expected_durations`
    em grupos consecutivos cuja soma bate com cada `real_durations`, com
    tolerância `base_tolerance` + 0,3s por faixa agrupada (arredondamento
    das APIs). Partição parcial não vale: nome errado com cara de confiável
    é pior que "Track N". Devolve grupos de índices, ou None.
    """
    n_real = len(real_durations)
    n_exp = len(expected_durations)
    if n_real == 0 or n_exp == 0 or n_real > n_exp:
        return None
    
    def tolerance_for(group_size: int) -> float:
        return base_tolerance + 0.3 * (group_size - 1)
    
    def backtrack(real_idx: int, exp_idx: int, groups: List[List[int]]) -> Optional[List[List[int]]]:
        if real_idx == n_real and exp_idx == n_exp:
            return groups
        if real_idx == n_real or exp_idx == n_exp:
            return None
        
        cum = 0.0
        for k in range(exp_idx, min(exp_idx + max_group_size, n_exp)):
            cum += expected_durations[k]
            group_size = k - exp_idx + 1
            allowed = tolerance_for(group_size)
            diff = cum - real_durations[real_idx]
            
            if abs(diff) <= allowed:
                result = backtrack(real_idx + 1, k + 1, groups + [list(range(exp_idx, k + 1))])
                if result is not None:
                    return result
            
            if diff > allowed:
                # Durações são positivas: somar mais faixas só piora.
                break
        
        return None
    
    return backtrack(0, 0, [])


class SmartCutter(AnaliseDeAudio):
    """Decide onde cortar o disco a partir dos silêncios detectados.

    metadata: {'tracks': [{'title', 'duration'}, ...]} do catálogo.
    all_gaps: {método: [gaps]} vindos da detecção (corte_audio).
    Cada estratégia devolve uma lista de cortes ({'track', 'title', 'start',
    'end', 'gap_found', 'method', 'expected'}; 'end' None = até o fim) ou None.
    """

    def __init__(self, metadata: Dict, all_gaps: Dict[str, List[Dict]], audio_file: str, log_func=None,
                 catalogo=None, artist: str = None, album: str = None):
        self.metadata = metadata
        self.all_gaps = all_gaps
        self.audio_file = audio_file
        self.cuts = []
        # Opcionais: "segunda opinião" do MusicBrainz (_try_alt_source_duration).
        self.catalogo = catalogo
        self.artist = artist
        self.album = album
        # Cortes com silêncio real que cut_with_durations confirmou antes de
        # desistir; cut_by_cross_validation os poupa dos seus filtros.
        self._api_confirmed_gaps = []
        # Liga em decide_and_cut(allow_cross_validation=True): ver _estimar_fronteiras.
        self._permitir_estimativa = False
        # Log da interface (o console some no .exe); sem ele, usa print.
        self.log_func = log_func
        # Samples decodificados (mono, float) reutilizados por _find_rms_minimum.
        self._rms_audio_cache = None

    def _log(self, msg):
        """Envia a mensagem ao log da interface (ou ao console)."""
        if self.log_func:
            self.log_func(msg)
        else:
            print(msg)

    def cut_by_cross_validation(self) -> Optional[List[Dict]]:
        """
        CONSENSO (último recurso): corta só pelo áudio, sem usar durações.

        Clusters (±5s) -> consenso de votos -> silêncio mínimo -> descarta
        o início e espaçamentos curtos -> completa com quedas relativas.
        Usa os nomes do catálogo só se a contagem bater EXATAMENTE; senão
        "Track N". Rejeita com <4 ou >20 cortes, ou offsets ruins demais.
        """
        self._log("\n🎯 Estratégia CONSENSO: só o áudio (sem as durações do catálogo)")

        self._log("📊 Criando clusters com votação...")
        clusters = self.cluster_gaps(tolerance=5.0)
        clusters.sort(key=lambda c: c['position'])
        
        total_clusters = len(clusters)
        self._log(f"📊 {total_clusters} clusters detectados")
        
        # Clusters já confirmados por cut_with_durations (silêncio real perto
        # do esperado) escapam dos filtros de consenso/duração abaixo: é uma
        # confirmação melhor que esses critérios (ex.: "Buck", Nina Simone,
        # 4 votos mas silêncio <1s).
        confirmed_positions = getattr(self, '_api_confirmed_gaps', [])
        if confirmed_positions:
            self._log(f"🔁 Aproveitando {len(confirmed_positions)} corte(s) já confirmado(s) por outro método...")
        for c in clusters:
            c['pre_confirmed'] = any(abs(c['position'] - p) <= 5.0 for p in confirmed_positions)
        
        self._log(f"🔍 Filtrando por consenso (≥2 métodos)...")
        validated = [c for c in clusters if c['votes'] >= CutTuning.MIN_VOTES_TO_TRUST or c['pre_confirmed']]
        self._log(f"   ✅ {len(validated)} gaps validados ({total_clusters - len(validated)} descartados)")

        # Silêncio mínimo: descarta respirações e pausas curtas.
        self._log(f"🔍 Filtrando por duração mínima do silêncio (≥1.0s)...")
        before_duration_filter = len(validated)
        validated = [c for c in validated if duracao_do_silencio(c) >= CutTuning.MIN_SILENCE_DURATION_SEC or c['pre_confirmed']]
        removed = before_duration_filter - len(validated)
        self._log(f"   ✅ {len(validated)} gaps com silêncio ≥1.0s ({removed} muito curtos removidos)")
        
        self._log(f"🔍 Removendo falsos positivos...")

        # Gaps no começo do vídeo quase sempre são falsos positivos.
        validated = [g for g in validated if g['position'] >= CutTuning.EARLY_GAP_FILTER_SEC]
        self._log(f"   ✅ Após filtro <60s: {len(validated)} gaps")

        # Gaps muito próximos do anterior: fica só o primeiro.
        min_spacing = CutTuning.MIN_GAP_SPACING_SEC
        self._log(f"   🔍 Espaçamento mínimo: ≥{min_spacing}s")
        
        spaced = []
        removed_by_spacing = []
        
        for gap in validated:
            if not spaced:
                spaced.append(gap)
            else:
                distance = gap['position'] - spaced[-1]['position']
                if distance >= min_spacing:
                    spaced.append(gap)
                else:
                    removed_by_spacing.append({
                        'position': gap['position'],
                        'distance': distance,
                        'votes': gap['votes']
                    })
        
        if removed_by_spacing:
            self._log(f"   ⚠️  {len(removed_by_spacing)} gaps removidos por espaçamento <{min_spacing}s:")
            for g in removed_by_spacing[:5]:
                self._log(f"      • {g['position']/60:.1f}min (apenas {g['distance']:.1f}s do anterior, {g['votes']}v)")
        
        self._log(f"   ✅ Após espaçamento mínimo ({min_spacing}s): {len(spaced)} gaps")

        # Fronteiras que o detector de silêncio não vê (LP com chiado,
        # intervalos curtos), senão 2-3 músicas saem num só "Track N".
        # O nº de faixas do cadastro só vale como alvo se ele NÃO tem durações:
        # com durações, chegar aqui já mostra que o cadastro não serve (talvez
        # seja outro disco), e completar até o número dele inventa cortes.
        _faixas_cad = self.metadata.get('tracks', []) or []
        _n_alvo = 0 if any(segundos_da_faixa(t) > 0 for t in _faixas_cad) else len(_faixas_cad)
        spaced = self._completar_com_quedas_relativas(spaced, _n_alvo)

        # Corte perto demais do fim deixaria um último pedaço vazio e
        # estragaria a comparação de contagem com o catálogo logo abaixo
        # (Nico Assumpção 1981: 10 cortes contra 9 esperados).
        try:
            _total = self._get_total_audio_duration() or 0
        except Exception:
            _total = 0
        while spaced and _total > 0 and _total - spaced[-1]['position'] < CutTuning.ULTIMO_PEDACO_MIN_SEC:
            _ult = spaced.pop()
            self._log(f"   ✂️  Descartando o corte em {_ult['position']/60:.1f}min: deixaria só "
                      f"{_total - _ult['position']:.1f}s no fim (não é faixa)")
        
        # Com o nº de músicas conhecido, pedaço curto é pausa dentro de uma
        # música, não faixa: fica o corte mais forte de cada par.
        if _faixas_cad:
            spaced = self._tirar_pedacos_curtos(spaced, CutTuning.PEDACO_MIN_COM_N_SEC)
        
        num_gaps = len(spaced)
        
        if num_gaps < 4:
            self._log(f"\n❌ Muito poucos gaps ({num_gaps}) - mínimo: 4")
            return None
        
        if num_gaps > 20:
            self._log(f"\n❌ Muitos gaps ({num_gaps}) - máximo: 20")
            self._log(f"   Provavelmente muitos falsos positivos")
            return None
        
        self._log(f"\n✅ {num_gaps} gaps encontrados (cross-validation puro)")
        
        # Só informativo: nunca descarta gaps reais pra bater com o catálogo.
        expected_tracks = len(self.metadata.get('tracks', []))
        if expected_tracks > 0:
            expected_gaps = expected_tracks - 1
            if num_gaps == expected_gaps:
                self._log(f"   📋 Número bate exatamente com APIs ({num_gaps} = {expected_gaps})")
            else:
                self._log(f"   ⚠️  Número difere das APIs ({num_gaps} vs {expected_gaps})")
        
        num_tracks = num_gaps + 1
        self._log(f"\n✅ {num_tracks} faixas detectadas por consenso ({num_gaps} gaps)")
        
        self._log(f"\n🔍 Gaps selecionados:")
        for i, gap in enumerate(spaced, 1):
            silence_duration = duracao_do_silencio(gap)
            self._log(f"   {i}. {gap['position']/60:5.1f}min | silêncio: {silence_duration:.2f}s | votos: {gap['votes']}")

        # Nomes do catálogo só com contagem EXATA: com contagem "quase" certa
        # os nomes cairiam nas faixas erradas parecendo confiáveis.
        tracks_from_api = self.metadata.get('tracks', [])
        use_api_names = len(tracks_from_api) > 0 and num_gaps == len(tracks_from_api) - 1
        
        if use_api_names:
            self._log(f"✅ Usando nomes das APIs (número de faixas coincide)")
        else:
            self._log(f"⚠️  MODO DEGREDADO: Nomes genéricos (Track 1, Track 2...)")
        
        cuts = []
        current_pos = 0.0
        
        for i in range(num_gaps):
            gap = spaced[i]
            cut_pos = gap['position']

            if use_api_names and i < len(tracks_from_api):
                title = tracks_from_api[i].get('title', '').strip()
                if not title or title == '?':
                    title = f'Track {i+1}'
            else:
                title = f'Track {i+1}'
            
            cuts.append({
                'track': i + 1,
                'title': title,
                'start': current_pos,
                'end': cut_pos,
                'gap_found': True,
                'method': f"cross_validation({gap['votes']}v)",
                'expected': 0,  # Sem expectativa
                # força da fronteira no FIM deste pedaço (palpite de disco sem durações)
                'votos': gap.get('votes', 0),
                'silencio': duracao_do_silencio(gap),
            })
            
            current_pos = cut_pos
        
        # Última faixa
        if use_api_names and len(cuts) < len(tracks_from_api):
            last_title = tracks_from_api[len(cuts)].get('title', '').strip()
            if not last_title or last_title == '?':
                last_title = f'Track {num_tracks}'
        else:
            last_title = f'Track {num_tracks}'
        
        cuts.append({
            'track': num_tracks,
            'title': last_title,
            'start': current_pos,
            'end': None,
            'gap_found': False,
            'method': 'last',
            'expected': 0
        })
        
        self._log(f"✅ {num_tracks} faixas prontas para corte")
        
        # Última faixa < 30s é sobra vazia no fim do vídeo: descarta.
        if len(cuts) > 0:
            last_cut = cuts[-1]
            last_start = last_cut['start']
            last_end = last_cut.get('end')

            import subprocess
            try:
                result = subprocess.run([
                    FFPROBE_PATH, '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    self.audio_file
                ], capture_output=True, text=True, timeout=10, **_subprocess_no_window_kwargs())
                
                if result.returncode == 0 and result.stdout.strip():
                    total_duration = float(result.stdout.strip())

                    if not last_end:
                        last_end = total_duration

                    last_duration = last_end - last_start

                    if last_duration < 30:
                        self._log(f"\n⚠️  Última faixa muito curta ({last_duration:.1f}s) - removendo")
                        cuts.pop()
                        num_tracks -= 1
                        self._log(f"✅ {num_tracks} faixas finais (após filtro)")
            except Exception:
                pass
        
        # Tabela de offsets contra a soma das durações do catálogo; rejeita
        # se >50% ruins. Só com TODAS as durações: com soma zero ("DISCO SEM
        # DURAÇÕES") todo corte pareceria errado.
        tem_duracoes = bool(tracks_from_api) and all(
            (t.get('duration') or 0) > 0 for t in tracks_from_api)
        if use_api_names and len(tracks_from_api) > 0 and tem_duracoes:
            self._log(f"\n📊 Tabela de Offsets (Esperado vs Cortado):")
            self._log(f"   {'Faixa':<7} | {'Esperado':>10} | {'Cortado':>10} | {'Offset':>10}")
            self._log(f"   {'-'*7}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")
            
            cumulative_expected = 0.0
            bad_offsets = 0
            
            for i in range(min(num_gaps, len(tracks_from_api) - 1)):
                cumulative_expected += tracks_from_api[i].get('duration', 0)
                actual_cut = cuts[i]['end']
                offset = actual_cut - cumulative_expected
                
                if abs(offset) >= 30:
                    bad_offsets += 1
                
                status = "✅" if abs(offset) < 10 else "⚠️" if abs(offset) < 30 else "❌"
                
                self._log(f"   {status} {i+1:<3} | {cumulative_expected:>8.1f}s | {actual_cut:>8.1f}s | {offset:>+8.1f}s")
            
            if num_gaps > 0:
                bad_percentage = (bad_offsets / num_gaps) * 100
                self._log(f"\n   📊 Qualidade: {bad_offsets}/{num_gaps} offsets ruins ({bad_percentage:.0f}%)")
                
                if bad_percentage > 50:
                    self._log(f"\n❌ CROSS-VALIDATION REJEITADO: Muitos offsets ruins ({bad_percentage:.0f}%)")
                    self._log(f"   APIs não batem com os gaps detectados")
                    return None
        elif use_api_names and not tem_duracoes:
            self._log(f"\nℹ️  O Discogs não tem as durações deste disco - cortes conferidos só pelo áudio")
        elif len(tracks_from_api) > 0:
            self._log(f"\n⚠️  APIs disponíveis mas número de faixas difere - não validando offsets")

        # Avisa (sem rejeitar) pedaços bem maiores que a mediana do álbum:
        # quase sempre 2+ faixas grudadas, que "Track N" esconderia.
        if len(cuts) >= 3:
            durations_for_check = []
            for c in cuts:
                if c.get('end') is not None:
                    durations_for_check.append(c['end'] - c['start'])
                else:
                    total_audio = self._get_total_audio_duration()
                    durations_for_check.append((total_audio - c['start']) if total_audio > 0 else 0)
            
            valid_durations = [d for d in durations_for_check if d > 0]
            if len(valid_durations) >= 3:
                sorted_d = sorted(valid_durations)
                n = len(sorted_d)
                median_duration = sorted_d[n // 2] if n % 2 == 1 else (sorted_d[n // 2 - 1] + sorted_d[n // 2]) / 2
                
                any_flagged = False
                for i, d in enumerate(durations_for_check):
                    if d > 0 and median_duration > 0 and d > median_duration * CutTuning.SUSPICIOUS_LENGTH_VS_MEDIAN_MULTIPLIER and d > median_duration + CutTuning.SUSPICIOUS_LENGTH_VS_MEDIAN_MARGIN_SEC:
                        if not any_flagged:
                            self._log(f"\n⚠️  Pedaço(s) suspeitosamente longo(s) (mediana do álbum: {median_duration/60:.1f}min):")
                            any_flagged = True
                        self._log(f"   Faixa {i+1} ({cuts[i]['title'][:30]}): {d/60:.1f}min - "
                                 f"pode ter 2+ faixas grudadas aqui, vale conferir manualmente")
        
        return cuts

    @staticmethod
    def _forca_do_corte(gap: Dict) -> tuple:
        """Confirmado antes pelas durações > mais votos > silêncio mais longo."""
        return (bool(gap.get('pre_confirmed')), gap.get('votes', 0) or 0, duracao_do_silencio(gap))

    def _tirar_pedacos_curtos(self, cortes: List[Dict], minimo: float) -> List[Dict]:
        """
        Enquanto houver pedaço menor que `minimo` entre dois cortes vizinhos
        (do mais curto pro mais longo), tira o corte mais fraco do par
        (_forca_do_corte). O começo e o fim do disco já têm filtros próprios.
        """
        cortes = list(cortes)
        tirados = []
        while len(cortes) >= 2:
            pedacos = [(cortes[i + 1]['position'] - cortes[i]['position'], i) for i in range(len(cortes) - 1)]
            curto, i = min(pedacos)
            if curto >= minimo:
                break
            fraco = i if self._forca_do_corte(cortes[i]) < self._forca_do_corte(cortes[i + 1]) else i + 1
            tirados.append((cortes.pop(fraco), curto))
        if tirados:
            self._log(f"   ✂️  {len(tirados)} corte(s) tirado(s): deixavam pedaço menor que {minimo:.0f}s "
                      f"(pausa dentro de uma música, não faixa):")
            for g, curto in sorted(tirados, key=lambda t: t[0]['position']):
                self._log(f"      • {g['position']/60:.1f}min (pedaço de {curto:.0f}s, {g.get('votes', 0)}v)")
        return cortes

    def cut_directly_on_gaps(self) -> Optional[List[Dict]]:
        """PONTUAÇÃO: para cada fronteira prevista pelas durações, escolhe o
        cluster mais próximo (não o mais votado).

        Janela progressiva ±15 -> ±30 -> ±45s até achar todas as fronteiras;
        exige ≥2 votos e prefere um silêncio nitidamente mais longo por perto.
        Depois: checagem de delta, refinamento fino e validação por intervalo
        (com tentativa de alinhamento global). Exige durações.
        """
        self._log("\n🎯 Estratégia PONTUAÇÃO: silêncio mais próximo de cada fronteira (15→30→45s max)")

        tracks = self.metadata['tracks']
        num_tracks = len(tracks)
        gaps_needed = num_tracks - 1

        has_durations = any(t.get('duration', 0) > 0 for t in tracks)
        
        if not has_durations:
            self._log("❌ SEM DURAÇÕES - estratégia não aplicável")
            return None
        
        self._log("📊 Criando clusters com votação...")
        all_clusters = self.cluster_gaps(tolerance=5.0)
        all_clusters.sort(key=lambda c: c['position'])

        num_gaps = len(all_clusters)

        self._log(f"📊 {num_gaps} gaps detectados")
        self._log(f"📊 {num_tracks} faixas esperadas")
        self._log(f"📊 Gaps necessários: {gaps_needed}")

        self._log(f"\n🔍 FILTRO 1: Removendo gaps <60s (falsos positivos)...")
        filtered_gaps = [g for g in all_clusters if g['position'] >= CutTuning.EARLY_GAP_FILTER_SEC]
        removed = num_gaps - len(filtered_gaps)
        if removed > 0:
            self._log(f"   ❌ Removidos {removed} gaps muito cedo")
        self._log(f"   ✅ {len(filtered_gaps)} gaps restantes")
        
        if len(filtered_gaps) < gaps_needed - 2:
            self._log(f"\n❌ POUCOS GAPS após filtro!")
            self._log(f"   Gaps válidos: {len(filtered_gaps)}")
            self._log(f"   Gaps necessários: {gaps_needed}")
            return None
        
        # Posições esperadas = silêncio inicial + soma acumulada das durações.
        self._log(f"\n📍 Posições esperadas (durações das APIs):")
        initial_offset = self._get_initial_silence_offset()
        if initial_offset > 0:
            self._log(f"   (+ {initial_offset:.1f}s de silêncio detectado no início do arquivo, "
                      f"antes da faixa 1 - contado como ponto de partida da timeline)")
        expected_positions = []
        cumulative = initial_offset
        for i in range(gaps_needed):
            cumulative += tracks[i].get('duration', 0)
            expected_positions.append(cumulative)
            min_exp = int(cumulative // 60)
            sec_exp = int(cumulative % 60)
            self._log(f"   Gap {i+1}: {min_exp:2d}:{sec_exp:02d} ({cumulative:.0f}s) - após '{tracks[i]['title'][:30]}'")
        
        # Com durações confiáveis, nunca aceitar fronteira a mais de 45s.
        self._log(f"\n🔍 FILTRO 2: JANELA PROGRESSIVA (15→30→45s)...")

        windows = [15, 30, 45]
        selected_gaps = []
        
        for window in windows:
            selected_gaps = []
            filtered_gaps_copy = [g for g in all_clusters if g['position'] >= CutTuning.EARLY_GAP_FILTER_SEC]
            
            self._log(f"\n   Tentativa com janela ±{window}s...")
            
            for i, exp_pos in enumerate(expected_positions):
                candidates = []

                for gap in filtered_gaps_copy:
                    distance = abs(gap['position'] - exp_pos)
                    if distance <= window:
                        gap['distance'] = distance
                        candidates.append(gap)

                # 1 voto em ~13 detectores é praticamente ruído (pausa dentro
                # da faixa); fronteira real aparece em vários. Sem candidato
                # aqui, o disco segue para cut_with_durations, mais cauteloso.
                MIN_VOTES_TO_TRUST = CutTuning.MIN_VOTES_TO_TRUST
                candidates = [c for c in candidates if c.get('votes', 0) >= MIN_VOTES_TO_TRUST]
                
                if candidates:
                    # Proximidade manda (as durações são a referência).
                    candidates.sort(key=lambda g: g['distance'])
                    best = candidates[0]

                    # Exceção: um silêncio bem mais longo, pouco mais longe,
                    # ganha do mais próximo; o curto costuma ser pausa dentro
                    # da faixa e a fronteira real tem silêncio sustentado.
                    DURATION_PREFERENCE_MARGIN = CutTuning.LONGER_SILENCE_PREFERENCE_MARGIN_SEC
                    EXTRA_DISTANCE_TOLERANCE = CutTuning.LONGER_SILENCE_EXTRA_DISTANCE_TOLERANCE_SEC
                    for c in candidates:
                        c['avg_silence_duration'] = (
                            sum(g.get('duration', 0) for g in c.get('gaps', [])) / len(c['gaps'])
                            if c.get('gaps') else 0
                        )
                    nearby = [c for c in candidates if c['distance'] <= best['distance'] + EXTRA_DISTANCE_TOLERANCE]
                    longest = max(nearby, key=lambda c: c['avg_silence_duration'])
                    if (longest is not best and
                            longest['avg_silence_duration'] >= best['avg_silence_duration'] + DURATION_PREFERENCE_MARGIN):
                        self._log(f"      🔬 Preferindo silêncio mais longo "
                                 f"({longest['avg_silence_duration']:.1f}s, a {longest['distance']:.1f}s do "
                                 f"esperado) sobre o mais próximo ({best['avg_silence_duration']:.1f}s, a "
                                 f"{best['distance']:.1f}s) - mais provável de ser a fronteira real, não "
                                 f"uma pausa dentro da faixa")
                        best = longest
                    
                    min_pos = int(best['position'] // 60)
                    sec_pos = int(best['position'] % 60)
                    min_exp = int(exp_pos // 60)
                    sec_exp = int(exp_pos % 60)
                    
                    delta = best['position'] - exp_pos
                    sign = "+" if delta > 0 else ""
                    
                    self._log(f"      Gap {i+1}: {min_pos:2d}:{sec_pos:02d} (esperado {min_exp:2d}:{sec_exp:02d}) | "
                          f"{sign}{delta:+.0f}s | {best['votes']}v")
                    
                    selected_gaps.append(best)
                    filtered_gaps_copy.remove(best)
                else:
                    min_exp = int(exp_pos // 60)
                    sec_exp = int(exp_pos % 60)
                    self._log(f"      Gap {i+1}: NADA em ±{window}s de {min_exp:2d}:{sec_exp:02d}")
            
            if len(selected_gaps) >= gaps_needed:
                self._log(f"\n   ✅ Sucesso com janela ±{window}s: {len(selected_gaps)} gaps")
                break

        # Precisa de TODAS as fronteiras.
        if len(selected_gaps) < gaps_needed:
            self._log(f"\n❌ INSUFICIENTE mesmo com ±45s!")
            self._log(f"   Encontrados: {len(selected_gaps)}")
            self._log(f"   Necessários: {gaps_needed}")
            return None
        
        selected_gaps.sort(key=lambda g: g['position'])

        # Delta contra a timeline esperada acima do limite: rejeita ou só
        # avisa, conforme CutTuning.REJEITAR_QUANDO_DURACAO_DIVERGE.
        self._log(f"\n📏 Validando precisão dos cortes...")
        max_delta_allowed = CutTuning.MAX_DELTA_ALLOWED_SEC
        
        expected_timeline = initial_offset
        for i in range(len(selected_gaps)):
            expected_timeline += tracks[i].get('duration', 0)
            actual_gap = selected_gaps[i]['position']
            delta = abs(actual_gap - expected_timeline)

            silence_dur = duracao_do_silencio(selected_gaps[i])
            
            if delta > max_delta_allowed:
                if CutTuning.REJEITAR_QUANDO_DURACAO_DIVERGE:
                    self._log(f"   ❌ Faixa {i+1}: delta {delta:.1f}s (silêncio {silence_dur:.1f}s) MUITO GRANDE (limite: {max_delta_allowed}s)")
                    self._log(f"\n❌ DISCO REJEITADO: Delta muito grande na faixa {i+1}")
                    self._log(f"   APIs não confiáveis ou gaps mal detectados")
                    return None
                self._log(f"   ⚠️  Faixa {i+1}: delta {delta:.1f}s (silêncio {silence_dur:.1f}s) acima do "
                         f"limite de {max_delta_allowed}s - a duração do Discogs não bate bem com este "
                         f"áudio, mas o corte tem silêncio real; seguindo mesmo assim")
            else:
                self._log(f"   ✅ Faixa {i+1}: delta {delta:.1f}s (silêncio {silence_dur:.1f}s) OK")
        
        # Refinamento fino: ponto mais silencioso de cada gap.
        self._log(f"\n🔬 REFINAMENTO FINO dos gaps selecionados...")

        expected_positions = []
        cumulative = initial_offset
        for i in range(gaps_needed):
            cumulative += tracks[i].get('duration', 0)
            expected_positions.append(cumulative)
        
        for i, gap in enumerate(selected_gaps):
            original = gap['position']
            expected = expected_positions[i] if i < len(expected_positions) else None
            refined = self._refine_gap(original, expected)
            gap['position'] = refined
        
        self._log(f"\n🔍 Gaps finais selecionados:")
        for i, gap in enumerate(selected_gaps, 1):
            min_pos = int(gap['position'] // 60)
            sec_pos = int(gap['position'] % 60)
            silence = gap.get('avg_silence', 0)
            score = gap.get('score', 0)
            self._log(f"   {i}. {min_pos:2d}:{sec_pos:02d} ({gap['position']:6.1f}s) | "
                  f"{gap['votes']}v | {silence:.1f}s | score={score}")
        
        self._log(f"\n✂️  Criando cortes...")
        cuts = []
        current_pos = 0.0

        for i, gap in enumerate(selected_gaps):
            title = tracks[i].get('title', '')
            if not title or title == '?' or title.strip() == '':
                title = f'Track {i+1}'
            
            cuts.append({
                'track': i + 1,
                'title': title,
                'start': current_pos,
                'end': gap['position'],
                'gap_found': True,
                'votes': gap['votes'],
                'method': f"proximity(score={gap.get('score', 0)})",
                'expected': tracks[i].get('duration', 0)
            })
            current_pos = gap['position']
            self._log(f"   ✅ Faixa {i+1:2d}: {title[:40]:40s} → corte em {gap['position']/60:5.1f}min")
        
        last_title = tracks[len(cuts)].get('title', '') if len(cuts) < len(tracks) else tracks[-1].get('title', '')
        if not last_title or last_title == '?' or last_title.strip() == '':
            last_title = f'Track {len(cuts)+1}'
        
        cuts.append({
            'track': len(cuts) + 1,
            'title': last_title,
            'start': current_pos,
            'end': None,
            'gap_found': False,
            'votes': 0,
            'method': 'last_track',
            'expected': 0
        })
        self._log(f"   ✅ Faixa {len(cuts):2d}: {last_title[:40]:40s} → até o fim")
        
        self._log(f"\n✅ {len(cuts)} faixas prontas para cortar")
        
        # Validação por intervalo: se alguma faixa não cabe entre seus cortes,
        # tenta o alinhamento global e fica com ele se reduzir a pior falta
        # (pegava os cortes errados do "Julie Wilson - My Old Flame").
        faltas = self._validar_intervalos(cuts, "PROXIMIDADE")
        if faltas:
            pior = max(f[1] for f in faltas)
            if pior >= CutTuning.INTERVAL_ALIGNMENT_TRY_SEC:
                self._log(f"   🧩 Tentando o alinhamento global pra corrigir esses cortes...")
                melhores = self.cut_by_interval_alignment()
                if melhores:
                    faltas_novas = self._validar_intervalos(melhores, "ALINHAMENTO", silencioso=True)
                    pior_nova = max((f[1] for f in faltas_novas), default=0.0)
                    if pior_nova < pior:
                        self._log(f"   ✅ Alinhamento melhorou: pior falta caiu de "
                                 f"{pior:.1f}s para {pior_nova:.1f}s - usando os cortes dele")
                        self._log(f"✅ PROXIMIDADE + ALINHAMENTO SUCESSO!")
                        return melhores
                    self._log(f"   ↩️  Alinhamento não melhorou (pior falta {pior_nova:.1f}s) - "
                             f"mantendo os cortes originais")
                else:
                    self._log(f"   ↩️  Alinhamento não achou encaixe - mantendo os cortes originais")
        
        self._log(f"✅ PROXIMIDADE SUCESSO!")
        
        return cuts

    def _validar_intervalos(self, cuts, origem="", silencioso=False):
        """
        Confere se cada faixa cabe entre seus dois cortes.

        O intervalo entre cortes tem que ser >= duração da faixa; menor é
        impossível (um pedaço foi parar no arquivo vizinho). Compara faixa a
        faixa, então não sofre a deriva da soma de durações.
        Devolve [(nº da faixa, segundos faltando), ...].
        """
        tracks = self.metadata.get('tracks', [])
        if not cuts or not tracks:
            return []
        try:
            inicio = self._get_initial_silence_offset()
        except Exception:
            inicio = 0.0

        faltas = []
        pos_anterior = inicio
        for i, cut in enumerate(cuts):
            if i >= len(tracks) or cut.get('end') is None:
                if cut.get('end') is not None:
                    pos_anterior = cut['end']
                continue
            duracao = tracks[i].get('duration', 0) or 0
            if duracao <= 0:
                pos_anterior = cut['end']
                continue
            intervalo = cut['end'] - pos_anterior
            sobra = intervalo - duracao
            if sobra < -CutTuning.INTERVAL_SHORTFALL_TOLERANCE_SEC:
                faltas.append((i + 1, abs(sobra)))
            pos_anterior = cut['end']

        if faltas and not silencioso:
            self._log(f"\n📐 Conferindo intervalos ({origem})...")
            for numero, falta in faltas:
                self._log(f"   ❌ Faixa {numero}: faltam {falta:.1f}s - um pedaço dela ficou "
                         f"no arquivo vizinho (o começo no anterior ou o fim no seguinte)")
        elif not silencioso:
            self._log(f"\n📐 Intervalos conferidos ({origem}): todas as faixas cabem")
        return faltas

    def cut_with_durations(self) -> Optional[List[Dict]]:
        """COM DURAÇÕES: parte da posição prevista de cada fronteira e procura
        o silêncio real perto dela (cluster mais próximo -> cascata FFmpeg/RMS).

        Fronteiras sem confirmação são reatacadas depois, ancoradas nos
        vizinhos (_resolve_unresolved_boundaries). Valida delta e intervalos
        e avisa pedaços longos demais. Ao rejeitar, guarda os cortes bons em
        _api_confirmed_gaps.
        """
        self._log("\n🎯 Estratégia COM DURAÇÕES: silêncio real perto de cada fronteira")

        tracks = self.metadata['tracks']

        # Uma passada do FFmpeg no disco inteiro entra na votação como mais
        # um método ('ffmpeg_full_disk').
        self._log("🔍 FASE 1: Detectando TODOS os silêncios (FFmpeg disco inteiro)...")
        ffmpeg_gaps = self._detect_all_silences_full_disk()
        self._log(f"   ✅ {len(ffmpeg_gaps)} silêncios detectados por FFmpeg")

        if ffmpeg_gaps:
            formatted_gaps = []
            for gap in ffmpeg_gaps:
                formatted_gaps.append({
                    'position': gap['position'],  # já é o meio do silêncio
                    'start': gap.get('start', gap['position']),
                    'end': gap.get('end', gap['position'] + gap['duration']),
                    'duration': gap['duration'],
                    'method': 'ffmpeg_full_disk'
                })

            self.all_gaps['ffmpeg_full_disk'] = formatted_gaps

        self._log("📊 Criando clusters com votação...")
        clusters = self.cluster_gaps(tolerance=5.0)

        clusters.sort(key=lambda c: c['position'])
        
        self._log(f"📊 {len(clusters)} clusters com votação")
        if clusters:
            self._log(f"   Mínimo votos: {min(c['votes'] for c in clusters)}, Máximo votos: {max(c['votes'] for c in clusters)}")
        
        self._log(f"\n🔍 DEBUG - Primeiros 10 clusters:")
        for i, c in enumerate(clusters[:10], 1):
            self._log(f"   {i}. {c['position']/60:5.1f}min ({c['position']:6.1f}s) | {c['votes']:2d} votos")

        self._log(f"\n🔍 ANÁLISE DE OFFSET entre métodos:")
        self._analyze_method_offsets()

        # Um item por corte INTERNO (entre faixa i e i+1). Primeiro resolve
        # todas as fronteiras (algumas ficam 'unresolved'), reataca os buracos
        # pelos vizinhos e só então encadeia start/end: um corte ruim no meio
        # não derruba mais o álbum inteiro.
        boundaries = []
        initial_offset = self._get_initial_silence_offset()
        if initial_offset > 0:
            self._log(f"\n🔍 Silêncio inicial detectado: {initial_offset:.1f}s (antes da faixa 1) - "
                      f"contado como ponto de partida da timeline esperada")
        expected_timeline = initial_offset  # soma das durações a partir do início real do áudio

        for i, track in enumerate(tracks[:-1]):
            duration = track.get('duration', 0)

            if duration == 0:
                self._log(f"❌ Faixa {i+1}: sem duração!")
                self._log(f"❌ REJEITANDO DISCO (durações incompletas)")
                return None

            expected_timeline += duration
            
            track_title = track.get('title', '')
            if not track_title or track_title == '?' or track_title.strip() == '':
                track_title = f'Track {i+1}'
            self._log(f"\n🔍 DEBUG Faixa {i+1}: {track_title[:40]}")
            self._log(f"   Esperada em: {expected_timeline/60:.1f}min ({expected_timeline:.1f}s)")
            
            cut_pos = None
            gap_found = False
            method = None
            
            # Etapa 1: cluster mais próximo (janela adaptativa).
            self._log(f"   Etapa 1: Buscando gap MAIS PRÓXIMO (janela adaptativa)...")
            
            best = self.find_closest_gap(expected_timeline, clusters, adaptive=True)
            
            if best:
                candidate_pos = best['position']
                distance_from_api = abs(candidate_pos - expected_timeline)
                votes = best['votes']
                
                # Distância aceita depende dos votos: muitos detectores
                # concordando vencem uma duração de catálogo imprecisa ("What
                # Every Girl Should Know": 5 votos a 23,9s, correto); poucos
                # votos longe do esperado é achado duvidoso ("Gotta Groove").
                max_trust_distance = (CutTuning.TRUST_DISTANCE_HIGH_VOTES_SEC if votes >= CutTuning.HIGH_VOTES_THRESHOLD
                                       else CutTuning.TRUST_DISTANCE_LOW_VOTES_SEC)

                # Piso de votos: 1 voto é ruído mesmo perto do esperado
                # ("Into The Heaven": 1 voto a 7,7s, fronteira real a ~35s).
                MIN_VOTES_TO_TRUST = CutTuning.MIN_VOTES_TO_TRUST
                
                if votes < MIN_VOTES_TO_TRUST:
                    self._log(f"   ⚠️  Cluster mais próximo tem só {votes} voto(s) - evidência "
                             f"fraca demais pra confiar (mesmo a {distance_from_api:.1f}s do "
                             f"esperado) - tentando cascata antes de desistir...")
                elif distance_from_api <= max_trust_distance:
                    cut_pos = self._refine_gap(candidate_pos, expected_timeline)
                    gap_found = True
                    method = f"closest({votes}v,refined)"
                    delta = cut_pos - expected_timeline
                    self._log(f"   ✅ Faixa {i+1}: gap {cut_pos/60:5.1f}min (delta {delta:+5.1f}s, votos={votes}, REFINADO)")
                else:
                    # Longe demais: não rejeita, deixa a cascata tentar.
                    self._log(f"   ⚠️  Cluster mais próximo a {distance_from_api:.1f}s "
                             f"(limite: {max_trust_distance:.0f}s p/ {votes} voto(s)) - "
                             f"tentando cascata antes de desistir...")
            else:
                self._log(f"      ❌ Nenhum gap próximo encontrado")
            
            # Etapa 2: cascata de detectores mais sensíveis (FFmpeg + RMS),
            # aceita até 30s do esperado.
            if cut_pos is None:
                gap_fallback, method_fallback = self._find_gap_cascade(expected_timeline, window=90.0)
                
                if gap_fallback:
                    distance_from_expected = abs(gap_fallback - expected_timeline)
                    
                    if distance_from_expected <= 30.0:
                        cut_pos = self._refine_gap(gap_fallback, expected_timeline)
                        gap_found = True
                        method = f"{method_fallback}_refined"
                        delta = cut_pos - expected_timeline
                        self._log(f"   ✅ Faixa {i+1}: gap {cut_pos/60:5.1f}min (delta {delta:+5.1f}s, método={method})")
                    else:
                        self._log(f"   ⚠️  Cascata achou algo a {distance_from_expected:.1f}s (limite: 30s) - ainda sem confirmação")
            
            if cut_pos is None:
                # Nunca corta na posição só calculada (um erro de duração
                # vazaria pra frente): fica 'unresolved' para o reataque.
                self._log(f"   ⏳ Faixa {i+1}: sem corte confirmado por ora (reataque com base nos vizinhos vem a seguir)")
                method = 'unresolved'
            
            title = track.get('title', '')
            if not title or title == '?' or title.strip() == '':
                title = f'Track {i+1}'
            
            boundaries.append({
                'title': title,
                'pos': cut_pos,
                'gap_found': gap_found,
                'method': method,
                'expected_timeline': expected_timeline,
                'expected_duration': duration,
            })
        
        # Se a soma de TODAS as durações bate com a duração real do arquivo,
        # o fim do arquivo vira âncora para buracos que vão até a última
        # faixa (erros por faixa dificilmente se cancelam a ponto de fechar
        # o total em poucos segundos).
        total_expected = sum(t.get('duration', 0) for t in tracks)
        total_real = self._get_total_audio_duration()
        disc_end_anchor = None
        if total_real > 0:
            tolerance = max(3.0, 0.5 * len(tracks))
            diff = abs(total_expected - total_real)
            if diff <= tolerance:
                self._log(f"\n📐 Duração total bate: API soma {total_expected/60:.2f}min, "
                         f"áudio real tem {total_real/60:.2f}min (diferença {diff:.1f}s, "
                         f"limite {tolerance:.1f}s) - usando fim do arquivo como âncora extra")
                disc_end_anchor = total_real
            else:
                self._log(f"\n📐 Duração total NÃO bate de perto (API {total_expected/60:.2f}min vs "
                         f"real {total_real/60:.2f}min, diferença {diff:.1f}s > limite {tolerance:.1f}s) "
                         f"- fim do disco não vira âncora extra")
        
        self._resolve_unresolved_boundaries(boundaries, tracks, disc_end_anchor=disc_end_anchor)
        
        still_unresolved = [idx for idx, b in enumerate(boundaries) if b['pos'] is None]
        if still_unresolved and getattr(self, '_permitir_estimativa', False):
            if self._estimar_fronteiras(boundaries, tracks, still_unresolved, disc_end_anchor):
                still_unresolved = []
        if still_unresolved:
            self._log(f"\n❌ DISCO REJEITADO: {len(still_unresolved)} corte(s) sem nenhuma evidência de "
                     f"áudio confiável mesmo após o reataque local (faixa(s) {[idx+1 for idx in still_unresolved]})")
            # Guarda os cortes com silêncio real para cut_by_cross_validation.
            self._api_confirmed_gaps = [
                b['pos'] for b in boundaries
                if b['pos'] is not None and b['gap_found'] and not str(b['method']).startswith('math_fallback')
            ]
            return None
        
        # Encadeia start/end só agora, com todas as fronteiras resolvidas.
        cuts = []
        current_pos = 0.0
        for i, b in enumerate(boundaries):
            cuts.append({
                'track': i + 1,
                'title': b['title'],
                'start': current_pos,
                'end': b['pos'],
                'gap_found': b['gap_found'],
                'method': b['method'],
                'expected': b['expected_duration'],
            })
            current_pos = b['pos']
        
        # Checagem de delta contra a timeline do catálogo. Pula
        # 'math_fallback*' (estimativa, divergir é esperado) e
        # '*local_reattack' (ancorado nos vizinhos justamente porque a
        # timeline daquele trecho já se mostrou errada).
        self._log(f"\n📏 Validando precisão dos cortes...")
        max_delta_allowed = CutTuning.MAX_DELTA_ALLOWED_SEC
        
        expected_timeline = initial_offset
        for i, cut in enumerate(cuts):
            expected_timeline += tracks[i].get('duration', 0)
            method_str = str(cut['method'])
            
            if method_str.startswith('math_fallback'):
                self._log(f"   ~  Faixa {i+1}: estimativa por duração (sem checagem de delta - divergir é esperado)")
                continue
            
            if 'local_reattack' in method_str:
                self._log(f"   ✅ Faixa {i+1}: silêncio real confirmado por reataque local "
                         f"(ancorado nos vizinhos, não na timeline global da API)")
                continue
            
            actual_cut = cut['end']
            delta = abs(actual_cut - expected_timeline)
            
            if delta > max_delta_allowed:
                if CutTuning.REJEITAR_QUANDO_DURACAO_DIVERGE:
                    self._log(f"   ❌ Faixa {i+1}: delta {delta:.1f}s MUITO GRANDE (limite: {max_delta_allowed}s)")
                    self._log(f"\n❌ DISCO REJEITADO: Delta muito grande na faixa {i+1}")
                    self._log(f"   APIs não confiáveis ou gaps mal detectados")
                    self._api_confirmed_gaps = [
                        c['end'] for c in cuts
                        if c.get('gap_found') and not str(c.get('method', '')).startswith('math_fallback')
                    ]
                    return None
                self._log(f"   ⚠️  Faixa {i+1}: delta {delta:.1f}s acima do limite de "
                         f"{max_delta_allowed}s - a duração do Discogs não bate bem com este áudio, "
                         f"mas o corte tem silêncio real; seguindo mesmo assim")
            else:
                self._log(f"   ✅ Faixa {i+1}: delta {delta:.1f}s OK")
        
        # Validação por intervalo (mesma regra de _validar_intervalos, com log
        # detalhado): intervalo menor que a faixa = áudio no arquivo vizinho.
        self._log(f"\n📐 Conferindo intervalos (cada faixa cabe entre seus dois cortes?)...")
        faltas = []
        pos_anterior = initial_offset
        for i, cut in enumerate(cuts):
            duracao_esperada = tracks[i].get('duration', 0) or 0
            if duracao_esperada <= 0 or cut.get('end') is None:
                pos_anterior = cut.get('end') or pos_anterior
                continue
            intervalo = cut['end'] - pos_anterior
            sobra = intervalo - duracao_esperada
            if sobra < -CutTuning.INTERVAL_SHORTFALL_TOLERANCE_SEC:
                faltas.append((i + 1, abs(sobra)))
                self._log(f"   ❌ Faixa {i+1}: só {intervalo:.1f}s entre os cortes, mas a faixa "
                         f"tem {duracao_esperada:.0f}s - faltam {abs(sobra):.1f}s "
                         f"(um pedaço dela ficou no arquivo vizinho)")
            pos_anterior = cut['end']
        
        if faltas:
            pior = max(f[1] for f in faltas)
            numeros = [f[0] for f in faltas]
            if (CutTuning.REJEITAR_QUANDO_DURACAO_DIVERGE
                    and pior >= CutTuning.INTERVAL_SHORTFALL_REJECT_SEC):
                self._log(f"\n❌ DISCO REJEITADO: faixa(s) {numeros} com corte cedo demais "
                         f"(pior caso: {pior:.1f}s de áudio no arquivo errado)")
                self._log(f"   Isso é medida, não estimativa: não cabe a faixa inteira "
                         f"entre os dois cortes.")
                self._api_confirmed_gaps = [
                    c['end'] for c in cuts
                    if c.get('gap_found') and not str(c.get('method', '')).startswith('math_fallback')
                ]
                return None
            else:
                if pior >= CutTuning.INTERVAL_SHORTFALL_REJECT_SEC:
                    self._log(f"   ⚠️  Faixas {numeros} com corte cedo demais (até {pior:.1f}s "
                             f"de áudio no arquivo seguinte)")
                else:
                    self._log(f"   ⚠️  Faltas pequenas nas faixas {numeros} (até {pior:.1f}s)")
                # Tenta consertar com o alinhamento global, não só avisar.
                if pior >= CutTuning.INTERVAL_ALIGNMENT_TRY_SEC:
                    self._log(f"   🧩 Tentando o alinhamento global pra corrigir...")
                    melhores = self.cut_by_interval_alignment()
                    if melhores:
                        faltas_novas = self._validar_intervalos(melhores, silencioso=True)
                        pior_nova = max((f[1] for f in faltas_novas), default=0.0)
                        if pior_nova < pior:
                            self._log(f"   ✅ Alinhamento melhorou: pior falta caiu de {pior:.1f}s "
                                     f"para {pior_nova:.1f}s - usando os cortes dele")
                            return melhores
                        self._log(f"   ↩️  Alinhamento não melhorou (pior falta {pior_nova:.1f}s) "
                                 f"- mantendo os cortes originais")
                    else:
                        self._log(f"   ↩️  Alinhamento não achou encaixe - mantendo os originais")
        else:
            self._log(f"   ✅ Todos os intervalos comportam suas faixas")
        
        last = tracks[-1]
        last_title = last.get('title', '')
        if not last_title or last_title == '?' or last_title.strip() == '':
            last_title = f'Track {len(tracks)}'
        
        cuts.append({
            'track': len(tracks),
            'title': last_title,
            'start': current_pos,
            'end': None,
            'gap_found': False,
            'method': 'last',
            'expected': last.get('duration', 0)
        })
        # Fronteira estimada: as faixas dos DOIS lados podem ter um pedaço
        # da vizinha - ficam marcadas pra conferir (log, arquivo e tag).
        for i, b in enumerate(boundaries):
            if b.get('estimado'):
                cuts[i]['corte_estimado'] = True
                cuts[i + 1]['corte_estimado'] = True
        
        # Avisa (sem rejeitar nem recortar) pedaços bem mais longos que a
        # mediana do álbum ou que a duração esperada: provável 2+ faixas
        # grudadas que a checagem de delta não pega se o catálogo errou.
        real_durations_for_check = []
        for c in cuts:
            if c['end'] is not None:
                real_durations_for_check.append(c['end'] - c['start'])
            else:
                total_audio = self._get_total_audio_duration()
                if total_audio > 0:
                    real_durations_for_check.append(total_audio - c['start'])
        
        if len(real_durations_for_check) >= 3:
            sorted_durations = sorted(real_durations_for_check)
            n = len(sorted_durations)
            median_duration = sorted_durations[n // 2] if n % 2 == 1 else (sorted_durations[n // 2 - 1] + sorted_durations[n // 2]) / 2
            
            for i, real_dur in enumerate(real_durations_for_check):
                expected_dur = cuts[i].get('expected', 0)
                suspicious_vs_median = (median_duration > 0 and real_dur > median_duration * CutTuning.SUSPICIOUS_LENGTH_VS_MEDIAN_MULTIPLIER
                                         and real_dur > median_duration + CutTuning.SUSPICIOUS_LENGTH_VS_MEDIAN_MARGIN_SEC)
                suspicious_vs_expected = (expected_dur > 0 and real_dur > expected_dur * CutTuning.SUSPICIOUS_LENGTH_VS_EXPECTED_MULTIPLIER
                                           and real_dur > expected_dur + CutTuning.SUSPICIOUS_LENGTH_VS_EXPECTED_MARGIN_SEC)
                
                if suspicious_vs_median or suspicious_vs_expected:
                    self._log(f"   ⚠️  Faixa {i+1} ({cuts[i]['title'][:30]}): {real_dur/60:.1f}min - "
                             f"MUITO mais longa que o normal do álbum (mediana: {median_duration/60:.1f}min) - "
                             f"pode ter 2+ faixas grudadas aqui, vale conferir manualmente")
        
        gaps_found = sum(1 for c in cuts[:-1] if c['gap_found'])
        num_tracks = len(tracks)
        pct = (gaps_found / (num_tracks - 1) * 100) if num_tracks > 1 else 100
        
        self._log(f"\n✅ Sucesso! {gaps_found}/{num_tracks-1} gaps encontrados por silêncio real ({pct:.0f}%)")
        
        return cuts

    def cut_by_interval_alignment(self) -> Optional[List[Dict]]:
        """
        ALINHAMENTO GLOBAL: escolhe o CONJUNTO de cortes (programação
        dinâmica) comparando INTERVALOS entre cortes com as durações.

        A previsão por soma de durações deriva (não conta os silêncios entre
        faixas; ~30s num disco de 12), e aí o candidato "mais próximo" vira
        uma pausa dentro da música (caso "Julie Wilson - My Old Flame").
        Restrições: intervalo >= duração da faixa (com tolerância) e sobras
        parecidas entre si; o silêncio típico g é varrido de 0 a 12s.
        Exige todas as durações. Devolve os cortes ou None.
        """
        tracks = self.metadata.get('tracks', [])
        if len(tracks) < 2:
            return None

        duracoes = [t.get('duration', 0) or 0 for t in tracks]
        if sum(1 for d in duracoes if d > 0) < len(duracoes):
            self._log("   ⚠️  Alinhamento precisa da duração de TODAS as faixas - pulando")
            return None

        fim = self._get_total_audio_duration()
        if not fim or fim <= 0:
            self._log("   ⚠️  Não consegui medir a duração total do áudio - pulando alinhamento")
            return None

        inicio = self._get_initial_silence_offset()
        clusters = self.cluster_gaps()
        if not clusters:
            return None

        candidatos = sorted(c['position'] for c in clusters)
        por_posicao = {c['position']: c for c in clusters}

        self._log(f"\n🧩 ALINHAMENTO GLOBAL POR INTERVALOS")
        self._log(f"   {len(candidatos)} candidatos para {len(duracoes)-1} corte(s), "
                 f"áudio de {fim/60:.1f}min")

        n_cortes = len(duracoes) - 1
        tol = CutTuning.INTERVAL_SHORTFALL_TOLERANCE_SEC
        INF = float('inf')
        melhor = None

        # dp[k][j] = (custo, índice anterior) do melhor caminho com k cortes
        # terminando no candidato j; custo = soma de |sobra - g|.
        g = 0.0
        while g <= 12.0 + 1e-9:
            dp = [[(INF, None)] * len(candidatos) for _ in range(n_cortes + 1)]

            for j, c in enumerate(candidatos):
                sobra = (c - inicio) - duracoes[0]
                if sobra >= -tol:
                    dp[1][j] = (abs(sobra - g), None)

            for k in range(2, n_cortes + 1):
                for j, c in enumerate(candidatos):
                    melhor_j = (INF, None)
                    for p in range(j):
                        custo_ant, _ = dp[k - 1][p]
                        if custo_ant == INF:
                            continue
                        sobra = (c - candidatos[p]) - duracoes[k - 1]
                        if sobra < -tol:
                            continue
                        custo = custo_ant + abs(sobra - g)
                        if custo < melhor_j[0]:
                            melhor_j = (custo, p)
                    dp[k][j] = melhor_j

            for j, c in enumerate(candidatos):
                custo, _ = dp[n_cortes][j]
                if custo == INF:
                    continue
                sobra_final = (fim - c) - duracoes[-1]
                if sobra_final < -tol:
                    continue
                total = custo + abs(sobra_final - g)
                if melhor is None or total < melhor[0]:
                    caminho = []
                    k, idx = n_cortes, j
                    while idx is not None and k >= 1:
                        caminho.append(candidatos[idx])
                        _, idx = dp[k][idx]
                        k -= 1
                    melhor = (total, g, list(reversed(caminho)))
            g += 0.5

        if melhor is None:
            self._log("   ❌ Nenhum conjunto de candidatos comporta a sequência de faixas")
            self._log("      (sinal de que faltam fronteiras de verdade no áudio, "
                      "não de que a escolha foi ruim)")
            return None

        custo_total, g_melhor, posicoes = melhor
        erro_medio = custo_total / len(duracoes)
        self._log(f"   ✅ Encaixe achado: silêncio típico ~{g_melhor:.1f}s entre faixas, "
                 f"erro médio {erro_medio:.1f}s/faixa")

        cuts = []
        anterior = inicio
        for i, pos in enumerate(posicoes):
            cluster = por_posicao.get(pos, {})
            titulo = tracks[i].get('title', '') or f'Track {i+1}'
            sobra = (pos - anterior) - duracoes[i]
            self._log(f"      Faixa {i+1}: corte em {pos/60:.1f}min "
                     f"(sobra {sobra:+.1f}s, {cluster.get('votes', 0)} voto(s))")
            cuts.append({
                'track': i + 1,
                'title': titulo,
                'start': anterior,
                'end': cluster.get('end', pos),
                'gap_found': True,
                'method': 'interval_alignment',
                'expected': duracoes[i],
            })
            anterior = cluster.get('end', pos)

        titulo_final = tracks[-1].get('title', '') or f'Track {len(tracks)}'
        cuts.append({
            'track': len(tracks),
            'title': titulo_final,
            'start': anterior,
            'end': None,
            'gap_found': False,
            'method': 'last',
            'expected': duracoes[-1],
        })
        return cuts

    def _try_alt_source_duration(self, track_title: str) -> Optional[float]:
        """
        SEGUNDA OPINIÃO: quando não há silêncio real perto da posição que a
        duração do Discogs prevê pra uma faixa, pergunta ao MusicBrainz a
        duração dessa MESMA faixa (título parecido). Só devolve ONDE procurar
        de novo: quem chama continua exigindo um silêncio real ali.
        Devolve segundos, ou None (sem catálogo, sem rede, sem a faixa).
        """
        if not self.catalogo or not self.artist or not self.album or not track_title:
            return None
        try:
            result = self.catalogo.musicbrainz(self.artist, self.album)
        except Exception:
            result = None
        for alt_track in (result or {}).get('tracks') or []:
            alt_title = alt_track.get('title', '')
            alt_dur = alt_track.get('duration', 0)
            if alt_title and alt_dur and titles_similar(track_title, alt_title):
                self._log(f"      🔍 Segunda opinião (MusicBrainz): '{alt_title}' = "
                          f"{alt_dur}s (Discogs informava outra duração pra essa faixa)")
                return float(alt_dur)
        return None

    def _resolve_unresolved_boundaries(self, boundaries: List[Dict], tracks: List[Dict],
                                        disc_end_anchor: Optional[float] = None) -> None:
        """
        REATAQUE LOCAL: para cada "buraco" (fronteiras seguidas sem corte),
        procura silêncio real só no trecho entre os cortes vizinhos já
        confirmados, mirando a posição proporcional às durações.

        Preenche 'pos'/'gap_found'/'method' em `boundaries` (in-place); o
        que ficar com 'pos' None leva o chamador a rejeitar o disco. Nunca
        corta só por estimativa. `disc_end_anchor`: fim do arquivo usado
        como âncora final quando a soma das durações bateu com o áudio.
        """
        n = len(boundaries)
        idx = 0
        while idx < n:
            if boundaries[idx]['pos'] is not None:
                idx += 1
                continue
            
            hole_start = idx
            while idx < n and boundaries[idx]['pos'] is None:
                idx += 1
            hole_end = idx  # exclusivo - boundaries[hole_end] já resolvido (ou hole_end == n)
            hole_size = hole_end - hole_start
            
            anchor_before = boundaries[hole_start - 1]['pos'] if hole_start > 0 else 0.0
            anchor_after = boundaries[hole_end]['pos'] if hole_end < n else None
            using_disc_end_anchor = False
            
            if anchor_after is None and hole_end == n and disc_end_anchor is not None:
                anchor_after = disc_end_anchor
                using_disc_end_anchor = True
            
            self._log(f"\n🔧 REATAQUE LOCAL: faixa(s) {hole_start+1} a {hole_end} sem corte confirmado ainda")
            if anchor_after is None:
                self._log(f"   Âncora anterior: {anchor_before/60:.1f}min | Âncora seguinte: fim do disco (sem confirmação)")
            elif using_disc_end_anchor:
                self._log(f"   Âncora anterior: {anchor_before/60:.1f}min | Âncora seguinte: {anchor_after/60:.1f}min "
                         f"(fim REAL do arquivo, usado como âncora porque a duração total bateu de perto)")
            else:
                self._log(f"   Âncora anterior: {anchor_before/60:.1f}min | Âncora seguinte: {anchor_after/60:.1f}min "
                         f"(trecho confirmado de {(anchor_after-anchor_before)/60:.1f}min pra {hole_size} corte(s))")
            
            if anchor_after is None:
                # Buraco até o fim do disco sem âncora final: o erro não fica
                # contido, então só tenta se for 1 faixa (janela ampliada).
                if hole_size == 1:
                    target = boundaries[hole_start]['expected_timeline']
                    gap_pos, method = self._find_gap_cascade(target, window=CutTuning.LOCAL_REATTACK_NO_ANCHOR_WINDOW_SEC)
                    if gap_pos and gap_pos > anchor_before:
                        boundaries[hole_start]['pos'] = gap_pos
                        boundaries[hole_start]['gap_found'] = True
                        boundaries[hole_start]['method'] = f"{method}_local_reattack"
                        self._log(f"   ✅ Faixa {hole_start+1}: silêncio real achado em {gap_pos/60:.1f}min (janela ampliada)")
                    else:
                        self._log(f"   ⚠️  Sem âncora seguinte e nada de novo encontrado - deixando sem corte (revisão manual)")
                else:
                    self._log(f"   ⚠️  Buraco vai até o fim do disco e tem {hole_size} faixas - risco alto demais pra estimar, deixando sem corte")
                continue
            
            span = anchor_after - anchor_before
            durations_in_hole = [tracks[k].get('duration', 0) for k in range(hole_start, hole_end + 1)]
            total_relative = sum(durations_in_hole)
            
            # Faixa a faixa, avançando a âncora anterior (mantém a ordem).
            # O silêncio achado tem que ficar perto do alvo: a cascata alarga
            # a janela e, em discos com pouco silêncio entre faixas, pegaria
            # uma pausa dentro de outra faixa.
            MAX_TRUST_DISTANCE = CutTuning.LOCAL_REATTACK_MAX_TRUST_DISTANCE_SEC
            running_anchor = anchor_before
            cumulative = 0.0
            for offset, k in enumerate(range(hole_start, hole_end)):
                cumulative += durations_in_hole[offset]
                proportion = (cumulative / total_relative) if total_relative > 0 else (offset + 1) / (hole_size + 1)
                target = anchor_before + span * proportion
                
                local_window = max(CutTuning.LOCAL_REATTACK_WINDOW_MIN_SEC, min((anchor_after - running_anchor) / 2, CutTuning.LOCAL_REATTACK_WINDOW_MAX_SEC))
                self._log(f"   🔬 Faixa {k+1}: procurando silêncio perto de {target/60:.1f}min "
                         f"(janela ±{local_window:.0f}s, contida no trecho confirmado)...")
                gap_pos, method = self._find_gap_cascade(target, window=local_window)
                
                if gap_pos and running_anchor + CutTuning.LOCAL_REATTACK_MIN_GAP_FROM_PREVIOUS_SEC <= gap_pos < anchor_after:
                    distance_from_target = abs(gap_pos - target)
                    if distance_from_target <= MAX_TRUST_DISTANCE:
                        boundaries[k]['pos'] = gap_pos
                        boundaries[k]['gap_found'] = True
                        boundaries[k]['method'] = f"{method}_local_reattack"
                        self._log(f"   ✅ Faixa {k+1}: silêncio real achado em {gap_pos/60:.1f}min")
                        running_anchor = gap_pos
                    else:
                        self._log(f"   ⚠️  Faixa {k+1}: achou silêncio em {gap_pos/60:.1f}min, mas fica "
                                 f"{distance_from_target:.0f}s longe do esperado pela duração ({target/60:.1f}min) "
                                 f"- provavelmente não é a fronteira real dessa faixa (álbum com pouco silêncio "
                                 f"real entre faixas). Prefere confiar na duração informada.")
                else:
                    if gap_pos and gap_pos < running_anchor + CutTuning.LOCAL_REATTACK_MIN_GAP_FROM_PREVIOUS_SEC:
                        self._log(f"   ❌ Faixa {k+1}: achou algo em {gap_pos/60:.1f}min, mas muito perto "
                                 f"do corte anterior ({running_anchor/60:.1f}min) - provavelmente o mesmo "
                                 f"silêncio de novo, não uma faixa nova")
                    else:
                        self._log(f"   ❌ Faixa {k+1}: nenhum silêncio real dentro do trecho confirmado")
                
                # Segunda opinião (só buraco de 1 faixa, ancorado dos dois
                # lados): a duração do MusicBrainz muda ONDE procurar, mas
                # ainda exige silêncio real perto do novo alvo.
                if boundaries[k]['pos'] is None and hole_size == 1:
                    alt_duration = self._try_alt_source_duration(tracks[k].get('title', ''))
                    if alt_duration and alt_duration > 0:
                        alt_target = anchor_before + alt_duration
                        if anchor_before + 15.0 <= alt_target < anchor_after:
                            self._log(f"   🔬 Faixa {k+1}: tentando de novo com duração alternativa "
                                     f"({alt_duration:.0f}s) - nova posição esperada: {alt_target/60:.1f}min")
                            alt_gap_pos, alt_method = self._find_gap_cascade(alt_target, window=local_window)
                            if alt_gap_pos and running_anchor + CutTuning.LOCAL_REATTACK_MIN_GAP_FROM_PREVIOUS_SEC <= alt_gap_pos < anchor_after:
                                alt_distance = abs(alt_gap_pos - alt_target)
                                if alt_distance <= MAX_TRUST_DISTANCE:
                                    boundaries[k]['pos'] = alt_gap_pos
                                    boundaries[k]['gap_found'] = True
                                    boundaries[k]['method'] = f"{alt_method}_alt_source_reattack"
                                    self._log(f"   ✅ Faixa {k+1}: silêncio real achado em "
                                             f"{alt_gap_pos/60:.1f}min (confirmado com duração de fonte "
                                             f"alternativa)")
                                    running_anchor = alt_gap_pos
                            if boundaries[k]['pos'] is None:
                                self._log(f"   ❌ Faixa {k+1}: fonte alternativa também não achou "
                                         f"silêncio real confiável perto")
            
            # Sem silêncio real, o corte fica sem solução (álbum vai para
            # revisão manual): estimativa só pela duração já entregou corte
            # errado com cara de confiável ("Honi Gordon Sings", faixa 6).
            still_missing = [k for k in range(hole_start, hole_end) if boundaries[k]['pos'] is None]
            if still_missing:
                self._log(f"   ❌ {len(still_missing)} corte(s) do buraco sem confirmação de silêncio real - "
                         f"deixando sem corte (o álbum inteiro vai pra revisão manual em vez de usar uma "
                         f"estimativa sem confirmação de áudio)")

    def cut_at_positions(self, inicios: List[float], titulos: List[str], marcar_sem_silencio: bool = True,
                         conferir_com_pausas: bool = False, exato: bool = False):
        """
        Cortes nas POSIÇÕES informadas (tempos de um comentário do vídeo, ou
        digitados pelo usuário), sem depender de duração de catálogo. Cada
        fronteira vai pro silêncio real a até POSICAO_JANELA_SILENCIO_SEC; sem
        silêncio, pro ponto de menor energia a até POSICAO_JANELA_RMS_SEC;
        sem nada, fica no tempo informado. Com marcar_sem_silencio, as faixas
        de fronteira sem silêncio ficam 'corte_estimado' (conferir).
        exato (cortes marcados no ✂ Editar): cada fronteira fica no ponto
        marcado, sem procurar pausa perto.
        conferir_com_pausas (tempos de um comentário): se o áudio TEM pausas
        claras pra metade das trocas, mas os tempos acertam menos da metade
        delas, a lista é de outro upload (deslocada) - devolve None.
        """
        self._log(f"\n🎯 Corte nas posições informadas ({len(inicios)} faixas)")
        clusters = sorted(self.cluster_gaps(tolerance=5.0), key=lambda c: c['position'])
        fronteiras, anterior = [], 0.0
        for k, alvo in enumerate(inicios[1:], start=1):
            minimo = anterior + CutTuning.LOCAL_REATTACK_MIN_GAP_FROM_PREVIOUS_SEC
            perto = [c for c in clusters if abs(c['position'] - alvo) <= CutTuning.POSICAO_JANELA_SILENCIO_SEC
                     and c['position'] > minimo]
            if exato:
                minimo = anterior + 0.5             # o editor já não deixa duas marcas a menos de 1 s
                pos, como = alvo, ('silêncio' if any(abs(c['position'] - alvo) <= 2.0 for c in clusters)
                                   else 'marcado por você')
            elif perto:
                pos, como = min(perto, key=lambda c: abs(c['position'] - alvo))['position'], 'silêncio'
            else:
                rms = self._find_rms_minimum(alvo, CutTuning.POSICAO_JANELA_RMS_SEC)
                pos, como = (rms, 'menor energia') if rms and rms > minimo else (alvo, 'tempo informado')
            if pos <= minimo:
                self._log(f"   ❌ Faixa {k} → {k + 1}: o tempo informado ({alvo / 60:.2f}min) não vem depois do "
                          f"corte anterior - lista fora de ordem")
                return None
            fronteiras.append((pos, como))
            anterior = pos
            self._log(f"   Faixa {k} → {k + 1}: {pos / 60:.2f}min ({como}; informado {alvo / 60:.2f}min, "
                      f"{pos - alvo:+.1f}s)")
        cuts, ini = [], 0.0
        for i, titulo in enumerate(titulos):
            fim, como = fronteiras[i] if i < len(fronteiras) else (None, 'fim')
            cuts.append({'track': i + 1, 'title': titulo or f'Track {i + 1}', 'start': ini, 'end': fim,
                         'gap_found': como == 'silêncio', 'method': f'posicao({como})', 'expected': 0})
            ini = fim if fim is not None else ini
        if marcar_sem_silencio:
            for i, (_, como) in enumerate(fronteiras):
                if como != 'silêncio':
                    cuts[i]['corte_estimado'] = True
                    cuts[i + 1]['corte_estimado'] = True
        achadas = sum(1 for _, como in fronteiras if como == 'silêncio')
        claras = sum(1 for c in clusters if c.get('votes', 0) >= CutTuning.MIN_VOTES_TO_TRUST
                     and c['position'] >= CutTuning.EARLY_GAP_FILTER_SEC)
        if conferir_com_pausas and fronteiras and claras >= len(fronteiras) / 2 and achadas < len(fronteiras) / 2:
            self._log(f"   ❌ Só {achadas}/{len(fronteiras)} tempos caem numa das {claras} pausas claras do áudio - "
                      f"a lista deve ser de outro upload (deslocada); não vou usar")
            return None
        self._log(f"   ✅ {achadas}/{len(fronteiras)} fronteiras num silêncio real perto do tempo informado")
        return cuts

    def _estimar_fronteiras(self, boundaries: List[Dict], tracks: List[Dict], faltam: List[int],
                            disc_end_anchor: Optional[float] = None) -> bool:
        """
        Só quando o usuário manda processar mesmo assim (_permitir_estimativa):
        as poucas fronteiras sem silêncio real (músicas emendadas) vão pela
        proporção das durações entre os cortes confirmados vizinhos, no ponto
        de menor energia a até ESTIMATIVA_JANELA_SEC. Antes, o disco caía no
        consenso, que corta em toda pausa ("Tocando Victor Assis Brasil": 11
        "Track N" com pedaços de 30s, em vez de 7 músicas com 1 emenda).

        Limites: até metade das fronteiras, no máximo ESTIMATIVA_MAX_SEGUIDAS
        seguidas; cada buraco precisa de âncora dos dois lados (corte
        confirmado, início do disco, ou fim do arquivo quando a soma bateu).
        Preenche `boundaries` (método 'math_fallback_estimativa', 'estimado':
        True) só se TODAS couberem; devolve True nesse caso.
        """
        n = len(boundaries)
        limite = n // 2
        if len(faltam) > limite:
            self._log(f"\n   ✗ Estimativa pela duração: {len(faltam)} fronteira(s) sem silêncio - "
                      f"acima do limite de {limite} (metade) pra este disco")
            return False
        seguidas, maior = 0, 0
        for b in boundaries:
            seguidas = seguidas + 1 if b['pos'] is None else 0
            maior = max(maior, seguidas)
        if maior > CutTuning.ESTIMATIVA_MAX_SEGUIDAS:
            self._log(f"\n   ✗ Estimativa pela duração: {maior} fronteiras seguidas sem silêncio - acima de "
                      f"{CutTuning.ESTIMATIVA_MAX_SEGUIDAS} o erro não fica preso entre cortes confirmados")
            return False
        novas = {}
        idx = 0
        while idx < n:
            if boundaries[idx]['pos'] is not None:
                idx += 1
                continue
            ini = idx
            while idx < n and boundaries[idx]['pos'] is None:
                idx += 1
            antes = boundaries[ini - 1]['pos'] if ini > 0 else 0.0
            depois = boundaries[idx]['pos'] if idx < n else disc_end_anchor
            if depois is None:
                self._log(f"\n   ✗ Estimativa pela duração: a fronteira da faixa {ini + 1} não tem corte "
                          f"confirmado depois dela - não dá pra estimar")
                return False
            duracoes = [tracks[k].get('duration', 0) or 0 for k in range(ini, idx + 1)]
            total = sum(duracoes)
            if total <= 0:
                return False
            if abs((depois - antes) - total) > max(CutTuning.ESTIMATIVA_FOLGA_TRECHO_SEC, 0.08 * total):
                self._log(f"\n   ✗ Estimativa pela duração: o trecho entre os cortes confirmados "
                          f"({(depois - antes):.0f}s) não comporta as faixas ({total:.0f}s) - pode haver música a "
                          f"mais ou a menos no vídeo")
                return False
            corrido, ancora = 0.0, antes
            for desloc, k in enumerate(range(ini, idx)):
                corrido += duracoes[desloc]
                alvo = antes + (depois - antes) * corrido / total
                rms = self._find_rms_minimum(alvo, CutTuning.ESTIMATIVA_JANELA_SEC)
                minimo = ancora + CutTuning.LOCAL_REATTACK_MIN_GAP_FROM_PREVIOUS_SEC
                pos = rms if rms and minimo <= rms < depois else alvo
                if not (minimo <= pos < depois):
                    self._log(f"\n   ✗ Estimativa pela duração: a faixa {k + 1} não cabe entre os cortes vizinhos")
                    return False
                novas[k] = (pos, alvo, bool(rms and pos == rms))
                ancora = pos
        self._log(f"\n📏 ESTIMATIVA PELA DURAÇÃO (você mandou processar): {len(novas)} fronteira(s) sem "
                  f"silêncio, entre cortes confirmados")
        for k, (pos, alvo, pelo_rms) in sorted(novas.items()):
            boundaries[k].update(pos=pos, gap_found=False, method='math_fallback_estimativa', estimado=True)
            onde = "ponto de menor energia perto" if pelo_rms else "posição pela duração"
            self._log(f"   ~  Faixa {k + 1} → {k + 2}: corte em {pos / 60:.1f}min ({onde}; esperado "
                      f"{alvo / 60:.1f}min) - as duas faixas ficam marcadas pra conferir")
        return True

    def find_closest_gap(self, expected: float, clusters: List[Dict], adaptive: bool = True) -> Optional[Dict]:
        """
        Escolhe o melhor cluster perto de `expected` (segundos).

        Janela: com `adaptive`, depende do maior nº de votos do disco (≥3,
        ≥2 ou 1 -> CutTuning.WINDOW_*_CONFIDENCE_SEC); vazia, tenta a janela
        de último recurso. Entre os candidatos vence o maior score =
        silêncio + queda de energia + proximidade + votos. Devolve o cluster
        (com 'total_score') ou None.
        """
        if not clusters:
            return None

        if adaptive:
            max_votes = max(c['votes'] for c in clusters)
            
            if max_votes >= 3:
                window = CutTuning.WINDOW_HIGH_CONFIDENCE_SEC
                self._log(f"      → Janela ±{window:.0f}s (alta confiança, {max_votes} votos)")
            elif max_votes >= 2:
                window = CutTuning.WINDOW_MEDIUM_CONFIDENCE_SEC
                self._log(f"      → Janela ±{window:.0f}s (média confiança, {max_votes} votos)")
            else:
                window = CutTuning.WINDOW_LOW_CONFIDENCE_SEC
                self._log(f"      → Janela ±{window:.0f}s (baixa confiança, {max_votes} votos)")
        else:
            window = CutTuning.WINDOW_DEFAULT_SEC
        
        candidates = [c for c in clusters
                      if abs(c['position'] - expected) <= window]

        if not candidates:
            self._log(f"      → Nada em ±{window}s, tentando ±{CutTuning.WINDOW_LAST_RESORT_SEC:.0f}s...")
            candidates = [c for c in clusters 
                          if abs(c['position'] - expected) <= CutTuning.WINDOW_LAST_RESORT_SEC]
        
        if not candidates:
            return None
        
        # Score favorece silêncio real (longo e profundo), não só proximidade.
        for c in candidates:
            avg_silence = sum(g.get('duration', 0) for g in c['gaps']) / len(c['gaps']) if c['gaps'] else 0
            avg_energy = sum(g.get('energy_drop', 0) for g in c['gaps']) / len(c['gaps']) if c['gaps'] else 0

            distance = abs(c['position'] - expected)

            # Tiers em ordem decrescente: vale o primeiro atingido.
            silence_score = 0
            for min_duration, points in CutTuning.SILENCE_SCORE_TIERS:
                if avg_silence >= min_duration:
                    silence_score = points
                    break

            for min_energy, points in CutTuning.ENERGY_SCORE_TIERS:
                if avg_energy >= min_energy:
                    silence_score += points
                    break

            proximity_score = max(0, CutTuning.PROXIMITY_SCORE_MAX - distance)

            votes_score = min(CutTuning.VOTES_SCORE_MAX, c['votes'] * CutTuning.VOTES_SCORE_PER_VOTE)

            c['total_score'] = silence_score + proximity_score + votes_score

        candidates.sort(key=lambda c: -c['total_score'])
        best = candidates[0]
        
        distance = abs(best['position'] - expected)
        self._log(f"      → MELHOR GAP: {best['position']:.1f}s (distância: {distance:.1f}s, votos: {best['votes']}, score: {best.get('total_score', 0):.0f})")
        
        return best

    def _analyze_method_offsets(self):
        """Só diagnóstico: loga o deslocamento médio sistemático entre pares
        de métodos de detecção (primeiros 5 gaps de cada, até 3 pares)."""
        method_gaps = {}
        for method_name, gaps in self.all_gaps.items():
            if gaps and len(gaps) >= 3:
                method_gaps[method_name] = [g['position'] for g in gaps[:5]]

        if len(method_gaps) < 2:
            self._log("   Insuficiente para análise")
            return

        methods = list(method_gaps.keys())
        comparisons_shown = 0

        for i in range(len(methods)):
            if comparisons_shown >= 3:
                break
                
            method1 = methods[i]
            gaps1 = method_gaps[method1]
            
            for j in range(i+1, len(methods)):
                if comparisons_shown >= 3:
                    break
                    
                method2 = methods[j]
                gaps2 = method_gaps[method2]
                
                # Pareia cada gap com o mais próximo do outro método (±10s).
                diffs = []
                for g1 in gaps1:
                    closest = min(gaps2, key=lambda g2: abs(g2 - g1))
                    if abs(closest - g1) < 10:
                        diffs.append(closest - g1)

                if diffs and len(diffs) >= 2:
                    avg_diff = sum(diffs) / len(diffs)
                    if abs(avg_diff) > 0.5:
                        self._log(f"   {method1:20s} vs {method2:20s}: offset médio = {avg_diff:+5.1f}s")
                        comparisons_shown += 1

    def cut_hybrid_with_validation(self) -> Optional[List[Dict]]:
        """
        MODO HÍBRIDO: corta em cada cluster detectado e confere a duração
        resultante contra o catálogo.

        Só roda se o nº de clusters for EXATAMENTE o nº de fronteiras. Conta
        como erro faixa <30s, >30min ou com desvio >15%; rejeita se mais de
        20% das faixas tiverem erro.
        """
        self._log(f"\n🎯 Estratégia HÍBRIDA: Gaps + Validação de Durações")

        tracks = self.metadata['tracks']
        num_tracks = len(tracks)
        gaps_needed = num_tracks - 1

        has_durations = any(t.get('duration', 0) > 0 for t in tracks)

        if not has_durations:
            self._log("❌ Sem durações das APIs - não pode usar modo híbrido")
            return None

        self._log("📊 Criando clusters com votação...")
        all_clusters = self.cluster_gaps(tolerance=5.0)
        all_clusters.sort(key=lambda c: c['position'])
        
        num_gaps = len(all_clusters)
        
        self._log(f"📊 {num_gaps} gaps detectados")
        self._log(f"📊 {num_tracks} faixas esperadas")
        self._log(f"📊 Gaps necessários: {gaps_needed}")
        
        if num_gaps != gaps_needed:
            self._log(f"\n❌ VALIDAÇÃO RIGOROSA FALHOU:")
            self._log(f"   Gaps detectados: {num_gaps}")
            self._log(f"   Gaps necessários: {gaps_needed}")
            self._log(f"   Diferença: {abs(num_gaps - gaps_needed)}")
            self._log(f"   Modo híbrido requer número EXATO de gaps")
            return None
        
        self._log(f"✅ VALIDAÇÃO: {num_gaps} gaps = {gaps_needed} necessários (PERFEITO!)")
        
        # Prefere os clusters com silêncio mínimo; se faltarem, usa todos.
        gaps_with_duration = []
        for gap in all_clusters:
            avg_silence = sum(g.get('duration', 0) for g in gap['gaps']) / len(gap['gaps'])
            gap['avg_silence'] = avg_silence
            if avg_silence >= CutTuning.MIN_SILENCE_DURATION_SEC:
                gaps_with_duration.append(gap)
        
        if len(gaps_with_duration) >= gaps_needed:
            self._log(f"✅ Usando {len(gaps_with_duration)} gaps com silêncio ≥1.0s")
            selected_gaps = gaps_with_duration[:gaps_needed]
        else:
            self._log(f"⚠️  Só {len(gaps_with_duration)} gaps com ≥1.0s")
            self._log(f"   Usando todos os {num_gaps} gaps disponíveis")
            selected_gaps = all_clusters
        
        selected_gaps.sort(key=lambda c: c['position'])

        self._log(f"\n🔍 Gaps selecionados:")
        for i, gap in enumerate(selected_gaps[:10], 1):
            self._log(f"   {i:2d}. {gap['position']/60:5.1f}min ({gap['position']:6.1f}s) | "
                  f"{gap['votes']} votos | {gap.get('avg_silence', 0):.1f}s silêncio")

        cuts = []
        current_pos = 0.0
        validation_errors = 0

        for i, gap in enumerate(selected_gaps):
            cut_duration = gap['position'] - current_pos
            expected_duration = tracks[i].get('duration', 0)

            if expected_duration > 0:
                deviation = abs(cut_duration - expected_duration) / expected_duration
                deviation_pct = deviation * 100
            else:
                deviation = 0
                deviation_pct = 0
            
            if cut_duration < 30:
                self._log(f"   ⚠️  Faixa {i+1}: MUITO CURTA! {cut_duration:.0f}s (esperado: {expected_duration:.0f}s)")
                validation_errors += 1
            elif cut_duration > 1800:
                self._log(f"   ⚠️  Faixa {i+1}: MUITO LONGA! {cut_duration:.0f}s (esperado: {expected_duration:.0f}s)")
                validation_errors += 1
            elif deviation_pct > 15:
                self._log(f"   ⚠️  Faixa {i+1}: {deviation_pct:.0f}% diferença! "
                      f"Real: {cut_duration:.0f}s vs Esperado: {expected_duration:.0f}s")
                validation_errors += 1
            else:
                self._log(f"   ✅ Faixa {i+1:2d}: {tracks[i]['title'][:40]:40s} → "
                      f"{cut_duration:.0f}s (desvio: {deviation_pct:.0f}%)")
            
            cuts.append({
                'track': i + 1,
                'title': tracks[i]['title'],
                'start': current_pos,
                'end': gap['position'],
                'gap_found': True,
                'votes': gap['votes'],
                'method': f"hybrid({gap['votes']}v)",
                'expected': expected_duration,
                'actual': cut_duration,
                'deviation': deviation_pct
            })
            
            current_pos = gap['position']
        
        last_duration = None
        if tracks[-1].get('duration', 0) > 0:
            last_duration = tracks[-1]['duration']
        
        cuts.append({
            'track': len(cuts) + 1,
            'title': tracks[len(cuts)]['title'] if len(cuts) < len(tracks) else tracks[-1]['title'],
            'start': current_pos,
            'end': None,
            'gap_found': False,
            'votes': 0,
            'method': 'last_track',
            'expected': last_duration,
            'actual': None,
            'deviation': 0
        })
        
        self._log(f"   ✅ Faixa {len(cuts):2d}: {tracks[-1]['title'][:40]:40s} → até o fim")
        
        error_rate = validation_errors / (num_tracks - 1)

        self._log(f"\n📊 Validação Final:")
        self._log(f"   Erros de validação: {validation_errors}/{num_tracks-1} ({error_rate*100:.0f}%)")

        if error_rate > 0.20:
            self._log(f"\n❌ MODO HÍBRIDO REJEITADO:")
            self._log(f"   Taxa de erro: {error_rate*100:.0f}% (limite: 20%)")
            self._log(f"   Muitas faixas com durações incompatíveis")
            return None
        
        self._log(f"✅ MODO HÍBRIDO APROVADO!")
        self._log(f"   {len(cuts)} faixas validadas com sucesso")
        
        return cuts

    def decide_and_cut(self, allow_cross_validation: bool = False) -> Optional[List[Dict]]:
        """
        Tenta as estratégias em ordem e devolve os cortes da primeira que
        der certo: híbrido -> pontuação -> com durações -> alinhamento global
        -> consenso. Devolve None se todas falharem.

        allow_cross_validation: o consenso ignora o catálogo e pode sair com
        "Track N"; por isso só roda quando o usuário manda processar mesmo
        assim pela fila de pendentes. Senão, o álbum vai para revisão manual.
        """
        tracks = self.metadata['tracks']
        # "processar mesmo assim": COM DURAÇÕES pode estimar poucas fronteiras
        # emendadas (_estimar_fronteiras) antes de cair no consenso
        self._permitir_estimativa = bool(allow_cross_validation)

        self._log("\n🎯 Tentando MODO HÍBRIDO: Gaps com validação de durações...")
        cuts = self.cut_hybrid_with_validation()
        
        if cuts:
            # Mesma validação por intervalo das outras estratégias.
            faltas_h = self._validar_intervalos(cuts, "MODO HÍBRIDO")
            if faltas_h:
                pior_h = max(f[1] for f in faltas_h)
                if pior_h >= CutTuning.INTERVAL_ALIGNMENT_TRY_SEC:
                    self._log(f"   🧩 Tentando o alinhamento global pra corrigir...")
                    melhores_h = self.cut_by_interval_alignment()
                    if melhores_h:
                        novas_h = self._validar_intervalos(melhores_h, silencioso=True)
                        pior_nova_h = max((f[1] for f in novas_h), default=0.0)
                        if pior_nova_h < pior_h:
                            self._log(f"   ✅ Alinhamento melhorou: pior falta caiu de "
                                     f"{pior_h:.1f}s para {pior_nova_h:.1f}s")
                            self._log("✅ MODO HÍBRIDO + ALINHAMENTO SUCESSO!")
                            return melhores_h
                    self._log(f"   ↩️  Mantendo os cortes originais")
            self._log("✅ MODO HÍBRIDO SUCESSO!")
            return cuts
        
        self._log("\n⚠️  Modo híbrido falhou, tentando PONTUAÇÃO...")
        cuts = self.cut_directly_on_gaps()
        
        if cuts:
            self._log("✅ PONTUAÇÃO SUCESSO!")
            return cuts
        
        self._log("\n⚠️  Pontuação falhou, tentando método COM DURAÇÕES...")
        
        has_durations = any(t.get('duration', 0) > 0 for t in tracks)
        
        if has_durations:
            cuts = self.cut_with_durations()
            
            if cuts is None:
                # Alinhamento global só depois dos outros, para não mexer nos
                # discos que eles já cortam certo.
                self._log("\n⚠️  Método com durações falhou, tentando ALINHAMENTO GLOBAL...")
                cuts = self.cut_by_interval_alignment()
                if cuts is not None:
                    self._log("✅ ALINHAMENTO GLOBAL SUCESSO!")
                    return cuts
            
            if cuts is None:
                if not allow_cross_validation:
                    self._log("\n⚠️  Método com durações falhou.")
                    self._log("❌ NÃO vou usar nomes genéricos automaticamente - o número/posição "
                              "das faixas não bateu com o que o Discogs informou (pode ser uma "
                              "edição diferente). Álbum vai para revisão manual.")
                    return None
                
                # Consenso: só a pedido do usuário (fila de pendentes).
                self._log("\n⚠️  Método com durações falhou, tentando CROSS-VALIDATION...")
                self._log("⚠️  ÚLTIMO RECURSO (pedido manualmente): Ignorando APIs completamente")
                
                cuts = self.cut_by_cross_validation()
                
                if cuts is None:
                    self._log("\n❌ DISCO REJEITADO por todos os métodos")
                    return None
                # Com as durações na mão, "Track N" cortado só pelas pausas
                # corta no meio das músicas (Ray Charles "Ingredients": 6
                # pedaços, um de 13 min). Só serve se a contagem bateu e os
                # nomes do cadastro entraram (conferidos pela tabela de offsets).
                if any(not (c.get('title') or '').strip() or c['title'] == f"Track {c['track']}" for c in cuts):
                    self._log("\n❌ DISCO REJEITADO: o disco tem as durações, e cortar só pelas pausas daria "
                              "\"Track N\" com cortes no meio das músicas - fica em Precisam de você")
                    return None
                # nomes pela posição só se CADA pedaço tem a duração da sua faixa (sem isso, duas
                # músicas grudadas + um corte a mais no fim deslocam os nomes do meio)
                total = self._get_total_audio_duration() or 0
                reais = [((c['end'] if c.get('end') is not None else total) - c['start']) for c in cuts]
                durs = [segundos_da_faixa(t) for t in tracks]
                fora = [i + 1 for i, (r, d) in enumerate(zip(reais, durs))
                        if d > 0 and abs(r - d) > max(CONSENSO_NOMES_FOLGA_SEC, 0.05 * d)]
                if len(reais) != len(durs) or fora:
                    self._log(f"\n❌ DISCO REJEITADO: os pedaços não têm a duração das faixas do cadastro "
                              f"(faixa(s) {fora[:6]}) - dar os nomes pela posição arriscaria nome trocado; "
                              f"fica em Precisam de você")
                    return None
                
                self._log("✅ Cross-validation SUCESSO (nomes do cadastro)!")
                return cuts
            
            self._log("✅ Método com durações SUCESSO!")
            return cuts
        else:
            if not allow_cross_validation:
                self._log("\n⚠️  DISCO SEM DURAÇÕES (o Discogs não informou durações pra este "
                          "álbum).")
                self._log("❌ NÃO vou usar nomes genéricos automaticamente. Álbum vai para "
                          "revisão manual.")
                return None
            
            # Sem durações: direto para o consenso (pedido manualmente).
            self._log("\n⚠️  DISCO SEM DURAÇÕES - tentando CROSS-VALIDATION...")
            
            cuts = self.cut_by_cross_validation()
            
            if cuts is None:
                self._log("\n❌ DISCO REJEITADO - impossível processar")
                return None
            
            self._log("✅ Cross-validation SUCESSO (nomes genéricos)!")
            return cuts

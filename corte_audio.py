"""
Análise do áudio usada pelo corte (mixin AnaliseDeAudio): silêncios,
energia (RMS), envelope, início de nota. Só mede - quem decide onde cortar
é corte_estrategias.SmartCutter.

posicao_de_corte_no_silencio: o corte cai perto do FIM do silêncio, pra a
faixa seguinte não começar com segundos mudos.

Medidas que não dependem das faixas (áudio decodificado, envelope, duração,
silêncios do disco inteiro) são feitas UMA vez por arquivo e reaproveitadas
por todas as tentativas de corte do mesmo álbum (medidas_do_arquivo); só o
álbum atual fica na memória.
"""
import os
import subprocess
import threading
from typing import Dict, List, Optional

from ajustes import CutTuning
from audio_util import FFMPEG_PATH, FFPROBE_PATH, _subprocess_no_window_kwargs
from util import segundos_da_faixa


_MEDIDAS = {'chave': None, 'dados': {}}
_TRAVA_MEDIDAS = threading.Lock()


def medidas_do_arquivo(arquivo) -> Dict:
    """
    Dicionário de medidas já feitas neste arquivo de áudio (o mesmo objeto
    pra todas as tentativas de corte). Arquivo diferente (ou alterado)
    começa vazio e descarta o anterior.
    """
    try:
        st = os.stat(arquivo)
        chave = (os.path.abspath(str(arquivo)), st.st_size, st.st_mtime_ns)
    except (OSError, TypeError, ValueError):
        return {}
    with _TRAVA_MEDIDAS:
        if _MEDIDAS['chave'] != chave:
            _MEDIDAS['chave'], _MEDIDAS['dados'] = chave, {}
        return _MEDIDAS['dados']


def esquecer_medidas():
    """Libera a memória do álbum (chamado ao fim de cada álbum)."""
    with _TRAVA_MEDIDAS:
        _MEDIDAS['chave'], _MEDIDAS['dados'] = None, {}


def duracao_do_silencio(item) -> float:
    """
    Quanto dura o silêncio de um gap ou de um grupo de gaps (cluster).

    Usa o 'duration' guardado por cada detector. NÃO usar 'end' - 'position':
    'position' já fica no fim do silêncio, então a conta daria sempre ~0,5s.
    """
    if not item:
        return 0.0
    gaps = item.get('gaps')
    if gaps:
        return max((g.get('duration') or 0.0) for g in gaps) or \
               max(0.0, item.get('end', item.get('position', 0)) - item.get('position', 0))
    if item.get('duration'):
        return float(item['duration'])
    ini = item.get('start', item.get('position', 0))
    return max(0.0, item.get('end', ini) - ini)


def posicao_de_corte_no_silencio(inicio: float, fim: float) -> float:
    """
    Decide ONDE cortar dentro de um trecho de silêncio detectado.

    Corta perto do FIM do silêncio, SILENCE_CUT_LEAD_IN_SEC antes da música
    voltar, nunca menos de SILENCE_CUT_MIN_OFFSET_SEC após o início. Assim o
    silêncio fica no fim da faixa anterior, não no começo da seguinte.
    """
    if fim is None or fim <= inicio:
        return inicio + CutTuning.SILENCE_CUT_MIN_OFFSET_SEC
    return max(inicio + CutTuning.SILENCE_CUT_MIN_OFFSET_SEC,
               fim - CutTuning.SILENCE_CUT_LEAD_IN_SEC)


class AnaliseDeAudio:
    """
    Silêncios, volume e começo real de cada faixa (a parte do SmartCutter que
    lê o áudio). Espera na instância: audio_file, all_gaps, metadata,
    _rms_audio_cache e _log.
    """

    def _medida(self, nome, calcular):
        """Medida do arquivo, calculada só na primeira vez (ver medidas_do_arquivo)."""
        m = medidas_do_arquivo(self.audio_file)
        if nome not in m:
            m[nome] = calcular()
        return m[nome]

    def _get_total_audio_duration(self) -> float:
        """
        Duração total do arquivo de áudio, via ffprobe (com cache; 0.0 se
        falhar).
        """
        if getattr(self, '_cached_total_duration', None) is None:
            self._cached_total_duration = self._medida('duracao', self._medir_duracao_total)
        return self._cached_total_duration

    def _medir_duracao_total(self) -> float:
        try:
            result = subprocess.run([
                FFPROBE_PATH, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                self.audio_file
            ], capture_output=True, text=True, timeout=30, **_subprocess_no_window_kwargs())
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def cluster_gaps(self, tolerance: float = CutTuning.CLUSTER_TOLERANCE_SEC) -> List[Dict]:
        """
        Junta os gaps de todos os métodos a até `tolerance` segundos uns dos
        outros. Cada cluster: position (média), end (maior fim), gaps,
        votes (nº de gaps) e methods.
        """
        all_gaps_list = []
        for method, gaps in self.all_gaps.items():
            for gap in gaps:
                all_gaps_list.append({
                    'position': gap['position'],
                    'start': gap.get('start', gap['position']),  # Início do gap
                    'end': gap.get('end', gap['position']),      # Fim do gap
                    'method': method,
                    'duration': gap.get('duration', 0)
                })
        
        all_gaps_list.sort(key=lambda x: x['position'])
        
        # Clustering
        clusters = []
        for gap in all_gaps_list:
            added = False
            for cluster in clusters:
                if abs(gap['position'] - cluster['position']) <= tolerance:
                    cluster['gaps'].append(gap)
                    cluster['votes'] += 1
                    cluster['position'] = sum(g['position'] for g in cluster['gaps']) / len(cluster['gaps'])
                    # Atualiza 'end' para o fim do último gap (corte no fim do silêncio)
                    cluster['end'] = max(g.get('end', g['position']) for g in cluster['gaps'])
                    cluster['methods'].add(gap['method'])
                    added = True
                    break
            
            if not added:
                clusters.append({
                    'position': gap['position'],
                    'end': gap.get('end', gap['position']),  # Fim do gap
                    'gaps': [gap],
                    'votes': 1,
                    'methods': {gap['method']}
                })
        
        return clusters

    def _get_initial_silence_offset(self) -> float:
        """
        Segundos de silêncio no início do arquivo, antes da faixa 1 (comum
        em vídeos do YouTube). Sem esse offset a posição esperada (soma das
        durações do Discogs) fica adiantada em todas as faixas.

        Analisa só os primeiros 30s; 0.0 se o áudio já começa tocando. Com cache.
        """
        if not hasattr(self, '_initial_silence_offset_cache'):
            self._initial_silence_offset_cache = self._medida('offset_inicial', self._medir_offset_inicial)
        return self._initial_silence_offset_cache

    def _medir_offset_inicial(self) -> float:
        import subprocess
        import re
        
        offset = 0.0
        try:
            cmd = [
                FFMPEG_PATH, '-t', '30', '-i', self.audio_file,
                '-af', 'silencedetect=n=-40dB:d=0.3',
                '-f', 'null', '-'
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                                     **_subprocess_no_window_kwargs())
            output = result.stderr
            starts = re.findall(r'silence_start: ([\d.]+)', output)
            ends = re.findall(r'silence_end: ([\d.]+)', output)
            if starts and ends and float(starts[0]) < 0.5:
                # Silêncio a partir de ~0s: o offset é onde ele termina
                offset = float(ends[0])
        except Exception:
            offset = 0.0
        return offset

    def _detect_all_silences_full_disk(self) -> List[Dict]:
        """
        Todos os silêncios do disco inteiro, num só silencedetect com o limiar
        moderado de CutTuning.FFMPEG_FULL_DISK_*. Ignora os 5s iniciais.

        Devolve [{'position', 'start', 'end', 'duration'}] (vazia se falhar).
        Medido uma vez por arquivo; cada chamada recebe cópias.
        """
        return [dict(g) for g in self._medida('silencios_disco', self._medir_silencios_disco)]

    def _medir_silencios_disco(self) -> List[Dict]:
        import subprocess
        import re
        
        cmd = [
            FFMPEG_PATH,
            '-i', self.audio_file,
            '-af', f'silencedetect=n={CutTuning.FFMPEG_FULL_DISK_THRESHOLD_DB}dB:d={CutTuning.FFMPEG_FULL_DISK_MIN_DURATION_SEC}',
            '-f', 'null', '-'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=CutTuning.FFMPEG_FULL_DISK_TIMEOUT_SEC, **_subprocess_no_window_kwargs())
            output = result.stderr
            
            gaps = []
            
            if 'silence_start' in output:
                silence_starts = re.findall(r'silence_start: ([\d.]+)', output)
                silence_ends = re.findall(r'silence_end: ([\d.]+)', output)
                silence_durations = re.findall(r'silence_duration: ([\d.]+)', output)
                
                # Combina em lista de gaps
                for start, end, dur in zip(silence_starts, silence_ends, silence_durations):
                    start_f = float(start)
                    end_f = float(end)
                    duration = float(dur)
                    position = posicao_de_corte_no_silencio(start_f, end_f)
                    
                    # Ignora início do áudio (<5s)
                    if position < 5.0:
                        continue
                    
                    gaps.append({
                        'position': position,
                        'start': start_f,
                        'end': end_f,
                        'duration': duration
                    })
            
            return gaps
            
        except subprocess.TimeoutExpired:
            self._log("   ⚠️  FFmpeg timeout (disco muito longo)")
            return []
        except Exception as e:
            self._log(f"   ⚠️  Erro FFmpeg: {e}")
            return []

    def _ffmpeg_silence(self, position: float, window: float, threshold_db: int, min_duration: float) -> Optional[float]:
        """
        Silêncio (silencedetect a threshold_db, min_duration) em
        position ± window. Prefere silêncios de 1s ou mais ao mais próximo.
        Devolve a posição de corte nele, ou None.
        """
        import subprocess
        import re
        
        start = max(0, position - window)
        duration = window * 2
        
        cmd = [
            FFMPEG_PATH, '-ss', str(start), '-t', str(duration),
            '-i', self.audio_file,
            '-af', f'silencedetect=n={threshold_db}dB:d={min_duration}',
            '-f', 'null', '-'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10, **_subprocess_no_window_kwargs())
            output = result.stderr
            
            if 'silence_start' in output:
                silence_starts = re.findall(r'silence_start: ([\d.]+)', output)
                silence_durations = re.findall(r'silence_duration: ([\d.]+)', output)
                
                if silence_starts:
                    # Converte para float e ajusta offset
                    silences = [start + float(s) for s in silence_starts]
                    
                    # Silêncio cortado na borda da janela não tem
                    # 'silence_duration': assume a duração mínima pedida.
                    durations = [float(d) for d in silence_durations]
                    if len(durations) < len(silences):
                        durations += [min_duration] * (len(silences) - len(durations))
                    
                    candidates = [(s, d) for s, d in zip(silences, durations) if abs(s - position) <= window]
                    if not candidates:
                        return None
                    
                    # Prefere silêncios ≥1s (intervalo real entre faixas):
                    # uma pausa curta DENTRO da música não pode vencer só por
                    # estar mais perto (Otis Redding: 13s vazavam pra próxima).
                    long_candidates = [(s, d) for s, d in candidates if d >= 1.0]
                    pool = long_candidates if long_candidates else candidates
                    
                    closest_start, closest_duration = min(pool, key=lambda c: abs(c[0] - position))
                    return posicao_de_corte_no_silencio(closest_start, closest_start + closest_duration)
            
            return None
        except Exception:
            return None

    def _find_rms_minimum(self, position: float, window: float) -> Optional[float]:
        """
        Ponto de corte pelo RMS em position ± window: acha o platô de menor
        energia e escolhe uma posição dentro dele conforme a assimetria do
        entorno (fade out empurra pro fim do platô). Devolve segundos ou None.
        """
        try:
            import numpy as np
            
            samples, sample_rate = self._amostras_mono()     # decodificado uma vez por álbum
            
            start_sample = int(max(0, position - window) * sample_rate)
            end_sample = int(min(len(samples), (position + window) * sample_rate))
            
            # RMS em janelas deslizantes
            window_size = int(sample_rate * CutTuning.RMS_WINDOW_SIZE_SEC)
            hop_size = int(sample_rate * CutTuning.RMS_HOP_SIZE_SEC)
            
            rms_values = []
            positions = []
            
            for i in range(start_sample, end_sample - window_size, hop_size):
                window_samples = samples[i:i+window_size]
                rms = np.sqrt(np.mean(window_samples**2))
                rms_values.append(rms)
                # Posição = CENTRO da janela (o início puxava o resultado
                # meia janela pra trás).
                positions.append(i / sample_rate + (window_size / sample_rate) / 2)
            
            if rms_values:
                rms_arr = np.array(rms_values)
                min_rms = rms_arr.min()
                min_idx = int(np.argmin(rms_arr))
                
                # O silêncio é um PLATÔ de janelas no mesmo chão de ruído,
                # não um ponto (argmin daria só o começo dele): expande a
                # partir do mínimo enquanto os vizinhos estiverem na tolerância.
                tolerance = max(min_rms * CutTuning.RMS_PLATEAU_TOLERANCE_FACTOR, 1e-6)
                left = min_idx
                while left > 0 and rms_arr[left - 1] <= min_rms + tolerance:
                    left -= 1
                right = min_idx
                while right < len(rms_arr) - 1 and rms_arr[right + 1] <= min_rms + tolerance:
                    right += 1
                
                # Onde cortar dentro do platô: mede quanto cada lado demora
                # pra voltar ao volume normal. Fade out = lado esquerdo lento.
                # Uma porcentagem fixa sempre errava ou os discos com fade ou
                # os sem fade.
                recovery_threshold = min_rms * CutTuning.RMS_RECOVERY_THRESHOLD_FACTOR
                hop_seconds = hop_size / sample_rate
                max_search_hops = int(CutTuning.RMS_RECOVERY_MAX_SEARCH_SEC / hop_seconds)  # não procura além disso de cada lado
                
                left_recovery_dist = 0
                i = left
                while (i > 0 and left_recovery_dist < max_search_hops
                       and rms_arr[i - 1] < recovery_threshold):
                    i -= 1
                    left_recovery_dist += 1
                
                right_recovery_dist = 0
                i = right
                while (i < len(rms_arr) - 1 and right_recovery_dist < max_search_hops
                       and rms_arr[i + 1] < recovery_threshold):
                    i += 1
                    right_recovery_dist += 1
                
                total_recovery = left_recovery_dist + right_recovery_dist
                
                # Fração do platô onde cortar: BASE se simétrico, até MAX
                # com fade out, até MIN com fade-in (ver CutTuning.RMS_BIAS_*).
                BASE_BIAS = CutTuning.RMS_BIAS_BASE
                MAX_BIAS = CutTuning.RMS_BIAS_MAX
                MIN_BIAS = CutTuning.RMS_BIAS_MIN
                
                if total_recovery > 0:
                    # O lado lento é a cauda do fade: corta perto do lado rápido
                    raw_bias = left_recovery_dist / total_recovery  # 0-1, 0.5 = simétrico
                    if raw_bias >= 0.5:
                        t = (raw_bias - 0.5) / 0.5
                        bias_fraction = BASE_BIAS + t * (MAX_BIAS - BASE_BIAS)
                    else:
                        t = (0.5 - raw_bias) / 0.5
                        bias_fraction = BASE_BIAS - t * (BASE_BIAS - MIN_BIAS)
                else:
                    # Nenhum lado com rampa detectável: platô simétrico
                    bias_fraction = BASE_BIAS
                
                span = right - left
                middle_idx = left + round(span * bias_fraction)
                
                return positions[middle_idx]
            
            return None
        except Exception:
            return None

    def _refine_gap(self, gap_position: float, expected_position: float = None) -> float:
        """
        Refina um corte rodando _find_gap_cascade perto dele.

        Com expected_position: não tenta se o candidato estiver a mais de
        MAX_DELTA_ALLOWED_SEC dele, e só aceita o refinado se ficar mais perto
        do esperado. Sem: aceita se ficar a até 5s do original.
        Devolve a posição refinada ou a original.
        """
        if expected_position is not None:
            distance = abs(gap_position - expected_position)
            if distance > CutTuning.MAX_DELTA_ALLOWED_SEC:
                self._log(f"      ⚠️  Gap muito longe do esperado ({distance:.1f}s) - nem tenta refinar")
                return gap_position
        
        # A janela alcança a posição esperada (+ margem), até o teto. Seguro:
        # o resultado só é aceito se melhorar.
        if expected_position is not None:
            refine_window = min(max(CutTuning.REFINE_WINDOW_BASE_SEC,
                                     abs(gap_position - expected_position) + CutTuning.REFINE_WINDOW_BASE_SEC),
                                 CutTuning.REFINE_WINDOW_CAP_SEC)
        else:
            refine_window = CutTuning.REFINE_WINDOW_BASE_SEC
        
        self._log(f"      🔬 Refinamento fino em {gap_position/60:.1f}min (±{refine_window:.0f}s)...")
        
        refined, method = self._find_gap_cascade(gap_position, window=refine_window)
        
        if refined:
            if expected_position is not None:
                distance_from_expected = abs(refined - expected_position)
                distance_original = abs(gap_position - expected_position)
                # Aceita só se ficar pelo menos tão perto do esperado quanto
                # o original (nunca piora o resultado)
                if distance_from_expected <= distance_original:
                    delta = refined - gap_position
                    self._log(f"      ✅ Refinado: {refined/60:.1f}min ({delta:+.1f}s, {method}, dist_esperada: {distance_from_expected:.1f}s)")
                    return refined
                else:
                    self._log(f"      ⚠️  Refinamento não melhorou (ficaria a {distance_from_expected:.1f}s do "
                              f"esperado, candidato original já estava a {distance_original:.1f}s) - mantém original")
                    return gap_position
            else:
                # Sem posição esperada: aceita até 5s do original
                distance_from_cluster = abs(refined - gap_position)
                if distance_from_cluster <= 5.0:
                    delta = refined - gap_position
                    self._log(f"      ✅ Refinado: {refined/60:.1f}min ({delta:+.1f}s, {method})")
                    return refined
                else:
                    self._log(f"      ⚠️  Mantém posição original")
                    return gap_position
        else:
            self._log(f"      ⚠️  Mantém posição original")
            return gap_position

    def _find_gap_cascade(self, expected_pos: float, window: float = 90.0) -> tuple:
        """
        Procura um corte em expected_pos ± window, parando no primeiro que acha:
        RMS mínimo, depois ffmpeg -40dB/0.5s, -35dB/0.3s e -30dB/0.2s.

        RMS vem primeiro porque, num fade, o silencedetect acha um ponto
        arbitrário da rampa; o RMS mínimo cai no fundo dela e também acerta
        corte seco. Devolve (position, method) ou (None, None).
        """
        self._log(f"   🔄 CASCATA DE FALLBACKS (posição esperada: {expected_pos/60:.1f}min)...")
        
        # Nível 2: RMS mínimo (o nível 1, energia, é tentado antes de chamar isto)
        self._log(f"      Nível 2: RMS mínimo (ponto de menor energia)...")
        gap = self._find_rms_minimum(expected_pos, window)
        if gap:
            self._log(f"      ✅ Achou em {gap/60:.1f}min (delta: {gap-expected_pos:+.1f}s)")
            return gap, "rms_minimum"
        
        # Nível 3: FFmpeg moderado (-40dB)
        self._log(f"      Nível 3: FFmpeg -40dB, dur≥0.5s...")
        gap = self._ffmpeg_silence(expected_pos, window, -40, 0.5)
        if gap:
            self._log(f"      ✅ Achou em {gap/60:.1f}min (delta: {gap-expected_pos:+.1f}s)")
            return gap, "ffmpeg_-40dB"
        
        # Nível 4: FFmpeg sensível (-35dB)
        self._log(f"      Nível 4: FFmpeg -35dB, dur≥0.3s...")
        gap = self._ffmpeg_silence(expected_pos, window, -35, 0.3)
        if gap:
            self._log(f"      ✅ Achou em {gap/60:.1f}min (delta: {gap-expected_pos:+.1f}s)")
            return gap, "ffmpeg_-35dB"
        
        # Nível 5: FFmpeg muito sensível (-30dB)
        self._log(f"      Nível 5: FFmpeg -30dB, dur≥0.2s...")
        gap = self._ffmpeg_silence(expected_pos, window, -30, 0.2)
        if gap:
            self._log(f"      ✅ Achou em {gap/60:.1f}min (delta: {gap-expected_pos:+.1f}s)")
            return gap, "ffmpeg_-30dB"
        
        self._log(f"      ❌ Nenhum método encontrou gap")
        return None, None

    def _quedas_relativas(self):
        """
        Quedas de volume em relação à música AO REDOR (mediana de ±10s), no
        disco inteiro. Acha intervalos de LP com chiado ou curtos demais, que
        o detector de limiar fixo não vê.

        Devolve [{'inicio','fim','posicao','profundidade'}] em segundos.
        """
        import numpy as np
        env, dt = self._envelope_db()
        if len(env) < 200:
            return []
        por_bloco = max(1, int(round(1.0 / dt)))           # blocos de 1s
        nb = len(env) // por_bloco
        blocos = np.median(env[:nb * por_bloco].reshape(nb, por_bloco), axis=1)
        raio = 10
        local_bloco = np.array([np.median(blocos[max(0, k - raio):k + raio + 1]) for k in range(nb)])
        local = np.repeat(local_bloco, por_bloco)
        if len(local) < len(env):
            local = np.concatenate([local, np.full(len(env) - len(local), local[-1])])
        abaixo = env < (local - CutTuning.QUEDA_REL_DB)
        min_q = max(1, int(round(CutTuning.QUEDA_REL_MIN_SEC / dt)))
        quedas = []
        i = 0
        n = len(env)
        while i < n:
            if not abaixo[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and abaixo[j + 1]:
                j += 1
            if j - i + 1 >= min_q:
                prof = float(local[i] - env[i:j + 1].min())
                if prof >= CutTuning.QUEDA_REL_DB:
                    ini_t, fim_t = i * dt, (j + 1) * dt
                    quedas.append({'inicio': ini_t, 'fim': fim_t,
                                   'posicao': posicao_de_corte_no_silencio(ini_t, fim_t),
                                   'profundidade': prof})
            i = j + 1
        return quedas

    def _completar_com_quedas_relativas(self, gaps, n_faixas_esperadas=0):
        """
        Acrescenta fronteiras que o detector de silêncio perdeu.

        Só age dentro de trechos que não cabem numa faixa só:
          - com número de faixas conhecido (Discogs sem durações): completa
            até esse número, pelas quedas mais fundas, sem deixar pedaço
            menor que QUEDA_REL_PEDACO_MIN_COM_N_SEC;
          - sem número conhecido: divide trechos com mais de 5 min (ou 60%
            acima do comprimento típico do disco), pela queda mais funda,
            sem deixar pedaço menor que 90s.
        Discos com os intervalos já achados não mudam.
        """
        try:
            quedas = self._quedas_relativas()
        except Exception as e:
            self._log(f"   ⚠️  Busca por quedas de volume pulada ({str(e)[:60]})")
            return gaps
        if not quedas:
            return gaps
        total = self._get_total_audio_duration() or 0
        if total <= 0:
            return gaps
        esp = CutTuning.MIN_GAP_SPACING_SEC
        cedo = CutTuning.EARLY_GAP_FILTER_SEC
        resultado = sorted(gaps, key=lambda g: g['position'])
        usadas = []

        def cabe(pos, ref, minimo=esp):
            return (pos >= cedo and pos <= total - minimo and
                    all(abs(pos - g['position']) >= minimo for g in ref))

        def novo_gap(q):
            return {'position': q['posicao'], 'end': q['fim'], 'votes': 1, 'pre_confirmed': False,
                    'gaps': [{'duration': q['fim'] - q['inicio']}], 'queda_relativa': True,
                    'methods': {'queda_relativa'}}

        alvo = max(0, n_faixas_esperadas - 1)
        if not alvo:
            # sem o número de faixas, só quedas bem fundas
            quedas = [q for q in quedas if q['profundidade'] >= CutTuning.QUEDA_REL_PROFUNDA_DB]
        if alvo and len(resultado) < alvo:
            for q in sorted(quedas, key=lambda q: -q['profundidade']):
                if len(resultado) >= alvo:
                    break
                if cabe(q['posicao'], resultado, max(esp, CutTuning.QUEDA_REL_PEDACO_MIN_COM_N_SEC)):
                    g = novo_gap(q)
                    resultado.append(g); usadas.append(q)
                    resultado.sort(key=lambda g: g['position'])
        elif not alvo:
            for _ in range(30):
                pontos = [0.0] + [g['position'] for g in resultado] + [total]
                trechos = [(pontos[k], pontos[k + 1]) for k in range(len(pontos) - 1)]
                comps = sorted(b - a for a, b in trechos)
                mediana = comps[len(comps) // 2]
                limite = CutTuning.QUEDA_REL_TRECHO_LONGO_SEC
                if len(trechos) >= 5:
                    limite = min(limite, max(1.6 * mediana, 240.0))
                dividiu = False
                for a, b in sorted(trechos, key=lambda t: -(t[1] - t[0])):
                    if b - a <= limite:
                        break
                    dentro = [q for q in quedas
                              if q['posicao'] - a >= CutTuning.QUEDA_REL_PEDACO_MIN_SEC
                              and b - q['posicao'] >= CutTuning.QUEDA_REL_PEDACO_MIN_SEC
                              and cabe(q['posicao'], resultado)]
                    if dentro:
                        q = max(dentro, key=lambda q: q['profundidade'])
                        resultado.append(novo_gap(q)); usadas.append(q)
                        resultado.sort(key=lambda g: g['position'])
                        dividiu = True
                        break
                if not dividiu:
                    break
        if usadas:
            self._log(f"   🔉 {len(usadas)} fronteira(s) achada(s) por queda de volume "
                      f"(intervalo com chiado ou curto demais pro detector de silêncio):")
            for q in sorted(usadas, key=lambda q: q['posicao']):
                self._log(f"      • {int(q['posicao'] // 60)}:{q['posicao'] % 60:04.1f} "
                          f"(volume caiu {q['profundidade']:.0f}dB)")
        return resultado

    # ------------------------------------------------------------------
    # AJUSTE FINAL: cortar onde a próxima faixa COMEÇA A SOAR
    # ------------------------------------------------------------------
    def _amostras_mono(self):
        """Amostras do áudio inteiro em float (mono) e a taxa, decodificadas uma vez por álbum.
        float ANTES de elevar ao quadrado: em int16 o quadrado estoura e o RMS vira NaN."""
        if self._rms_audio_cache is None:
            self._rms_audio_cache = self._medida('amostras', self._decodificar_mono)
        return self._rms_audio_cache

    def _decodificar_mono(self):
        import numpy as np
        from pydub import AudioSegment
        audio = AudioSegment.from_file(self.audio_file)
        samples = np.array(audio.get_array_of_samples()).astype(np.float32)
        if audio.channels == 2:
            samples = samples.reshape((-1, 2)).mean(axis=1)
        return samples, audio.frame_rate

    def _envelope_db(self):
        """
        Volume do disco inteiro em dB, em quadros de 50ms (com cache).

        Os valores são RELATIVOS (não dBFS): todas as regras abaixo comparam
        um trecho com outro do mesmo arquivo, nunca com um valor absoluto.
        """
        if getattr(self, '_env_cache', None) is None:
            self._env_cache = self._medida('envelope', self._calcular_envelope)
        return self._env_cache

    def _calcular_envelope(self):
        import numpy as np
        samples, sr = self._amostras_mono()
        hop = max(1, int(sr * 0.05))
        n = len(samples) // hop
        if n < 10:
            return (np.zeros(0), 0.05)
        quadros = samples[:n * hop].reshape(n, hop)
        rms = np.sqrt(np.mean(quadros ** 2, axis=1))
        # Piso de 1 amostra: abaixo é silêncio digital. Sem ele, uma amostra
        # solta do decodificador partia um silêncio em dois.
        env = 20.0 * np.log10(np.maximum(rms, 1.0))
        # média móvel de 3 quadros (150ms): tira picos isolados
        k = np.ones(3) / 3.0
        env = np.convolve(env, k, mode='same')
        return (env, hop / float(sr))

    def _inicio_real_da_proxima(self, pos, limite_esq, limite_dir, max_recuo=None,
                                subida_db=None, corte_em_som_db=None):
        """
        Onde a PRÓXIMA faixa começa de fato a soar, perto de um corte.

        Devolve (nova_posição, motivo) ou (pos, None) quando não mexe.

        Por quê: introdução suave lida como "silêncio" põe o corte dentro da
        faixa seguinte (Gloria Lynne, faixa 1->2). Aqui o áudio decide: acha o
        trecho mais fundo perto do corte e o instante em que o som volta.
        Regras pra não estragar os discos que já saem certos:
          - só mexe se houver silêncio de verdade (20dB abaixo da música);
          - pra TRÁS (até 6s): só se o corte atual estiver em som, não em
            silêncio, e se tudo entre o começo real e o corte for SUAVE -
            um final alto de música (acorde final) bloqueia, pra não jogar
            o fim da faixa anterior na seguinte;
          - pra FRENTE: só atravessando silêncio (leva o corte pra logo
            antes da música, como nos outros discos);
          - diferenças abaixo de 0,8s não mexem.

        max_recuo / subida_db / corte_em_som_db: usados só pela segunda
        busca (ver ajustar_ao_inicio_da_proxima), quando a conferência de
        intervalos já mostrou que falta um pedaço da faixa seguinte.
        """
        import numpy as np
        env, dt = self._envelope_db()
        recuo = CutTuning.ONSET_BUSCA_ATRAS_SEC if max_recuo is None else max_recuo
        subida = CutTuning.ONSET_SUBIDA_DB if subida_db is None else subida_db
        em_som = CutTuning.ONSET_CORTE_EM_SOM_DB if corte_em_som_db is None else corte_em_som_db
        if len(env) == 0:
            return pos, None

        def idx(t):
            return int(min(max(t / dt, 0), len(env) - 1))

        ini = max(limite_esq, pos - recuo)
        fim = min(limite_dir, pos + CutTuning.ONSET_BUSCA_FRENTE_SEC)
        i0, i1 = idx(ini), idx(fim)
        if i1 - i0 < 10:
            return pos, None
        trecho = env[i0:i1 + 1]
        j_fundo = int(np.argmin(trecho))
        chao = float(trecho[j_fundo])
        g_fundo = i0 + j_fundo

        musica = float(np.median(env[idx(pos - 30):idx(pos + 30) + 1]))
        if musica - chao < CutTuning.ONSET_SILENCIO_MIN_DB:
            return pos, None                     # não há silêncio de verdade

        # platô fundo em volta do ponto mais baixo
        tol = CutTuning.ONSET_PLATO_DB
        a = g_fundo
        while a > i0 and env[a - 1] <= chao + tol:
            a -= 1
        b = g_fundo
        while b < i1 and env[b + 1] <= chao + tol:
            b += 1

        # onde o som volta: sobe ONSET_SUBIDA_DB acima do chão e se mantém
        sustenta = max(1, int(round(CutTuning.ONSET_SUSTENTA_SEC / dt)))
        limiar = chao + subida
        onset = None
        for j in range(b + 1, i1 - sustenta + 2):
            if all(env[j:j + sustenta] > limiar):
                onset = j
                break
        if onset is None:
            return pos, None

        t_onset = onset * dt
        novo = max(t_onset - CutTuning.SILENCE_CUT_LEAD_IN_SEC, a * dt)
        if abs(novo - pos) < CutTuning.ONSET_MUDANCA_MIN_SEC:
            return pos, None

        if novo < pos:
            nivel_corte = float(np.mean(env[idx(pos - 0.25):idx(pos + 0.25) + 1]))
            if nivel_corte < chao + em_som:
                return pos, None                 # o corte já está em silêncio
            pico_entre = float(np.max(env[onset:idx(pos) + 1]))
            # ...e o som CONTINUA depois do corte (começo de faixa segue
            # tocando; um acorde final isolado morre logo depois).
            depois = env[idx(pos):idx(pos + 1.5) + 1]
            continua = len(depois) > 0 and float(np.mean(depois)) >= pico_entre - 10.0
            separacao_clara = ((b - a + 1) * dt >= CutTuning.ONSET_PLATO_LONGO_SEC and
                               pos - t_onset <= CutTuning.ONSET_INVASAO_CURTA_SEC and
                               continua)
            if pico_entre > musica - CutTuning.ONSET_SUAVE_DB and not separacao_clara:
                return pos, None                 # há som alto no meio: não é introdução suave
            if separacao_clara and pico_entre > musica - CutTuning.ONSET_SUAVE_DB:
                return novo, (f"a faixa seguinte começa a soar {pos - novo:.1f}s antes "
                              f"(logo depois de {(b - a + 1) * dt:.1f}s de silêncio)")
            return novo, (f"a faixa seguinte começa a soar {pos - novo:.1f}s antes "
                          f"(introdução suave depois de um silêncio mais fundo)")

        # pra frente: só se todo o caminho for silêncio
        if np.all(env[idx(pos):onset] <= chao + tol):
            return novo, f"leva o corte pra logo antes da música ({novo - pos:.1f}s adiante, só silêncio no caminho)"
        return pos, None

    def _recuo_pela_falta(self, cuts, i, pos, esq, dir_, total):
        """
        Segunda busca pelo começo da faixa seguinte, só quando ela ficou
        CURTA em relação à duração informada.

        Pra introduções tão baixas que a trava "corte já em silêncio" barra o
        ajuste normal (Gloria Lynne, faixa 7->8). Exige as duas evidências: a
        DURAÇÃO diz que falta um pedaço e o ÁUDIO mostra silêncio seguido de
        som baixinho. O recuo nunca passa do que falta (+ folga).
        Devolve (nova_posição, motivo) ou (pos, None).
        """
        tracks = (self.metadata or {}).get('tracks') or []
        if i + 1 >= len(tracks):
            return pos, None
        esperada = segundos_da_faixa(tracks[i + 1])
        if esperada <= 0:
            return pos, None
        fim_seguinte = cuts[i + 1].get('end') or total
        if not fim_seguinte:
            return pos, None
        falta = esperada - (fim_seguinte - pos)
        if falta < CutTuning.ONSET_FALTA_MIN_SEC:
            return pos, None
        max_recuo = min(CutTuning.ONSET_BUSCA_ATRAS_SEC,
                        falta + CutTuning.ONSET_FALTA_FOLGA_SEC)
        novo, motivo = self._inicio_real_da_proxima(
            pos, esq, dir_, max_recuo=max_recuo,
            subida_db=CutTuning.ONSET_FALTA_SUBIDA_DB,
            corte_em_som_db=CutTuning.ONSET_FALTA_CORTE_DB)
        if not motivo or novo >= pos:
            return pos, None
        return novo, (f"a faixa {i + 2} estava {falta:.1f}s mais curta que o informado, e o "
                      f"áudio mostra que ela começa a soar {pos - novo:.1f}s antes "
                      f"(introdução bem baixinha)")

    def ajustar_ao_inicio_da_proxima(self, cuts):
        """
        Aplica _inicio_real_da_proxima (e, se nada mudar, _recuo_pela_falta) a
        cada corte, sem deixar faixa menor que ONSET_FAIXA_MIN_SEC. Altera e
        devolve `cuts`. Qualquer erro mantém os cortes: nunca falha o álbum.
        """
        if not cuts or len(cuts) < 2:
            return cuts
        try:
            total = self._get_total_audio_duration() or 0
            ajustes = []
            for i in range(len(cuts) - 1):
                pos = cuts[i].get('end')
                if pos is None:
                    continue
                esq = (cuts[i].get('start') or 0) + CutTuning.ONSET_FAIXA_MIN_SEC
                prox_fim = cuts[i + 1].get('end') or total or pos + 60
                dir_ = prox_fim - CutTuning.ONSET_FAIXA_MIN_SEC
                if dir_ <= esq:
                    continue
                novo, motivo = self._inicio_real_da_proxima(pos, esq, dir_)
                if not motivo:
                    novo, motivo = self._recuo_pela_falta(cuts, i, pos, esq, dir_, total)
                if motivo:
                    cuts[i]['end'] = novo
                    cuts[i + 1]['start'] = novo
                    ajustes.append((i + 1, pos, novo, motivo))
            if ajustes:
                self._log("\n🎚️  Ajuste fino pelo início real de cada faixa:")
                def mmss(t):
                    return f"{int(t // 60)}:{t % 60:04.1f}"
                for n, velho, novo, motivo in ajustes:
                    self._log(f"   • Corte após a faixa {n}: {mmss(velho)} → {mmss(novo)} - {motivo}")
        except Exception as e:
            self._log(f"   ⚠️  Ajuste fino pulado ({str(e)[:80]}) - mantendo os cortes")
        return cuts

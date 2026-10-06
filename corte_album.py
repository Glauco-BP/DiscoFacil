"""
AlbumCutter: o corte de um álbum de ponta a ponta.

detect_gaps (silêncios por vários limiares do ffmpeg) -> smart_cut (decide
onde cortar, via SmartCutter) -> cut_tracks (gera um MP3 por faixa, na taxa
da fonte) -> add_tags (título, artista, álbum, nº, ano, artista do álbum,
gênero).
"""
import os
import subprocess
from typing import Dict, List

from ajustes import CutTuning
from audio_util import FFMPEG_PATH, _subprocess_no_window_kwargs, duracao_do_arquivo, medir_bitrate_fonte, taxa_mp3_para
from corte_audio import posicao_de_corte_no_silencio
from corte_estrategias import SmartCutter
from metadata_manager import gravar_tags
from util import sanitize


class AlbumCutter:
    """Corta um álbum baixado em faixas MP3 com tags (detect_gaps -> smart_cut -> cut_tracks -> add_tags)."""
    
    def __init__(self, artist: str, album: str, audio_file: str, metadata: Dict, output_dir: str, log_func=None,
                 catalogo=None):
        self.artist = artist
        self.album = album
        self.audio_file = audio_file
        self.metadata = metadata
        self.output_dir = output_dir
        self.cuts = []
        self.log_func = log_func
        # Repassado ao SmartCutter em smart_cut()
        self.catalogo = catalogo
        
        os.makedirs(output_dir, exist_ok=True)
    
    def _log(self, msg):
        if self.log_func:
            self.log_func(msg)
        else:
            print(msg)
    
    def detect_gaps(self) -> Dict[str, List[Dict]]:
        """
        Roda o silencedetect do ffmpeg em paralelo, um por limiar de
        CutTuning.FFMPEG_THRESHOLDS_DB. Devolve {nome_do_método: [gaps]}, cada
        gap com start/end/duration e a position de corte já calculada.
        """
        self._log(f"\n🔍 FFMPEG DETECTOR: {len(CutTuning.FFMPEG_THRESHOLDS_DB)} thresholds paralelos...")
        
        import subprocess
        from concurrent.futures import ThreadPoolExecutor
        
        def detect_ffmpeg(threshold: int, min_duration: float = CutTuning.FFMPEG_MIN_SILENCE_DURATION_SEC) -> List[Dict]:
            """Silêncios de um limiar (lista vazia se o ffmpeg falhar)."""
            cmd = [
                FFMPEG_PATH, '-i', self.audio_file,
                '-af', f'silencedetect=noise={threshold}dB:d={min_duration}',
                '-f', 'null', '-'
            ]
            
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=CutTuning.FFMPEG_DETECT_TIMEOUT_SEC, **_subprocess_no_window_kwargs())
                gaps = []
                start = None
                
                for line in r.stderr.split('\n'):
                    if 'silence_start' in line:
                        try:
                            start = float(line.split('silence_start: ')[1])
                        except Exception:
                            pass
                    elif 'silence_end' in line and start is not None:
                        try:
                            end = float(line.split('silence_end: ')[1].split('|')[0].strip())
                            dur = end - start
                            if dur >= min_duration:
                                gaps.append({
                                    'start': start,
                                    'end': end,
                                    'position': posicao_de_corte_no_silencio(start, start + dur),
                                    'duration': dur
                                })
                            start = None
                        except Exception:
                            pass
                
                return gaps
            except Exception:
                return []
        
        # Cada limiar é um "método": a concordância entre eles vira votos
        thresholds = [(f'ffmpeg_{abs(db)}dB', db) for db in CutTuning.FFMPEG_THRESHOLDS_DB]
        
        all_gaps = {}
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(detect_ffmpeg, db, 1.0): name 
                      for name, db in thresholds}
            
            for future in futures:
                method_name = futures[future]
                try:
                    gaps = future.result()
                    all_gaps[method_name] = gaps
                    self._log(f"  ✓ {method_name:20s} → {len(gaps):3d} gaps")
                except Exception:
                    all_gaps[method_name] = []
                    self._log(f"  ✗ {method_name:20s} → erro")
        
        total = sum(len(g) for g in all_gaps.values())
        self._log(f"\n📊 Total: {total} gaps detectados ({len(CutTuning.FFMPEG_THRESHOLDS_DB)} métodos FFmpeg)")
        
        return all_gaps
    
    def smart_cut(self, all_gaps: Dict, allow_cross_validation: bool = False) -> bool:
        """
        Decide os cortes via SmartCutter e ajusta cada um ao início real da
        faixa seguinte. Guarda em self.cuts; False se o disco foi rejeitado.
        """
        self._log("\n✂️  SMART CUTTER: Decidindo estratégia...")
        
        cutter = SmartCutter(self.metadata, all_gaps, self.audio_file, log_func=self.log_func,
                              catalogo=self.catalogo, artist=self.artist, album=self.album)
        self.cuts = cutter.decide_and_cut(allow_cross_validation=allow_cross_validation)
        
        # Verifica se disco foi rejeitado
        if self.cuts is None:
            self._log("\n❌ Disco rejeitado")
            return False
        
        # Ajuste final pelo começo real de cada faixa
        self.cuts = cutter.ajustar_ao_inicio_da_proxima(self.cuts)

        self._log(f"\n📋 Resultado: {len(self.cuts)} faixas para cortar")
        
        gaps_found = sum(1 for c in self.cuts[:-1] if c.get('gap_found', False))
        total_gaps = len(self.cuts) - 1
        
        self._log(f"📊 Gaps encontrados: {gaps_found}/{total_gaps} ({gaps_found/total_gaps*100:.0f}%)")
        
        return True
    
    def cortar_nas_posicoes(self, all_gaps: Dict, inicios, titulos, marcar_sem_silencio=True,
                            conferir_com_pausas=False, exato=False) -> bool:
        """
        Cortes nas posições informadas (SmartCutter.cut_at_positions) + ajuste
        ao início real de cada faixa. exato (cortes marcados no ✂ Editar): vale
        o ponto marcado, sem procurar pausa perto nem ajustar.
        """
        cutter = SmartCutter(self.metadata, all_gaps, self.audio_file, log_func=self.log_func,
                             catalogo=self.catalogo, artist=self.artist, album=self.album)
        self.cuts = cutter.cut_at_positions(list(inicios), list(titulos), marcar_sem_silencio, conferir_com_pausas,
                                            exato=exato)
        if not self.cuts:
            return False
        if not exato:
            self.cuts = cutter.ajustar_ao_inicio_da_proxima(self.cuts)
        return bool(self.cuts)

    def cut_tracks(self) -> bool:
        """
        Gera um MP3 por faixa de self.cuts, na taxa que acompanha a fonte, e
        confere a duração de cada arquivo gravado. False no primeiro erro.
        """
        self._log("\n✂️  Cortando faixas...")
        
        # O corte sempre reencoda pra MP3: a taxa acompanha a fonte (audio_util.taxa_mp3_para)
        original_bitrate = medir_bitrate_fonte(self.audio_file)
        if original_bitrate:
            self._log(f"   📊 Fonte: {original_bitrate}kbps → MP3 {taxa_mp3_para(original_bitrate)}kbps")

        for cut in self.cuts:
            track_num = cut['track']
            title = cut['title']
            start = cut['start']
            end = cut.get('end')
            
            output_file = os.path.join(
                self.output_dir,
                f"{track_num:02d} - {sanitize(title)}.mp3"
            )
            
            # Comando FFmpeg
            cmd = [FFMPEG_PATH, '-i', self.audio_file, '-ss', str(start)]
            
            if end:
                cmd.extend(['-to', str(end)])
            
            # UMA saída só: '-ss'/'-to' depois do '-i' valem só pra primeira
            # saída do ffmpeg; uma segunda gravaria o álbum inteiro no arquivo.
            taxa = taxa_mp3_para(original_bitrate)
            cmd.extend([
                '-vn',
                '-c:a', 'libmp3lame',
                '-b:a', f'{taxa}k',
                '-y',
                output_file
            ])
            
            try:
                subprocess.run(cmd, capture_output=True, check=True, timeout=120, **_subprocess_no_window_kwargs())
            except Exception as e:
                self._log(f"   ✗ Faixa {track_num:02d}: ERRO - {e}")
                return False

            # Confere o que foi gravado: duração da faixa pronta vs. trecho pedido.
            esperado = (end - start) if end else None
            if esperado:
                real = duracao_do_arquivo(output_file)
                if real and abs(real - esperado) > max(5.0, esperado * 0.05):
                    self._log(f"   ✗ Faixa {track_num:02d}: saiu com {real/60:.1f}min, "
                              f"deveria ter {esperado/60:.1f}min - corte não funcionou")
                    try:
                        os.remove(output_file)
                    except Exception:
                        pass
                    return False
            self._log(f"   ✓ Faixa {track_num:02d}: {title[:40]}")
        
        return True
    
    @staticmethod
    def _nota_da_faixa(cut: Dict) -> str:
        """Aviso gravado na tag (TXXX:DISCOFACIL_NOTA) de faixa que precisa ser conferida."""
        if cut.get('nome_palpite'):
            return 'nome por palpite (disco sem durações) - conferir'
        if cut.get('corte_estimado'):
            return 'corte estimado pela duração (músicas emendadas, sem silêncio) - conferir'
        return ''

    def add_tags(self) -> bool:
        """
        Tags de cada faixa cortada (metadata_manager.gravar_tags): título,
        artista, álbum, nº/total, ano, artista do álbum e gênero. Devolve
        True se ao menos uma faixa recebeu.
        """
        self._log("\n🏷️  Adicionando tags...")
        ok = 0
        for cut in self.cuts:
            n = cut['track']
            arquivo = os.path.join(self.output_dir, f"{n:02d} - {sanitize(cut['title'])}.mp3")
            if not os.path.exists(arquivo):
                continue
            if gravar_tags(arquivo, cut['title'], self.artist, self.album, n, len(self.cuts),
                           ano=self.metadata.get('year', ''),
                           artista_album=self.metadata.get('album_artist') or self.artist,
                           genero=self.metadata.get('genre', ''),
                           nota=self._nota_da_faixa(cut)):
                ok += 1
            else:
                self._log(f"   ⚠️  Erro ao adicionar tags em faixa {n}")
        self._log(f"   ✓ Tags adicionadas ({ok}/{len(self.cuts)} faixas)")
        return ok > 0

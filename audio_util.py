"""
ffmpeg/ffprobe do programa e medições simples de áudio.

- Acha o ffmpeg/ffprobe embutido no .exe (ou no PATH) e faz a pydub usá-lo.
- No Windows, nenhum subprocesso abre janela de console (patch no Popen).
- duracao_do_arquivo, medir_bitrate_fonte, taxa_mp3_para (MP3 na taxa da
  fonte, nunca abaixo).
Deve ser o primeiro import de main.py: o patch precisa valer antes de tudo.
"""
import os
import sys
import subprocess
from pathlib import Path


# --- Windows: nenhum subprocesso abre janela de console ---------------------
# Empacotado com --noconsole, todo Popen sem CREATE_NO_WINDOW abre uma janela
# preta - inclusive os que o yt-dlp faz por dentro. Em vez de corrigir cada
# chamada, o __init__ do Popen passa a injetar a flag no processo inteiro.
if sys.platform == 'win32':
    _popen_init_original = subprocess.Popen.__init__

    def _popen_init_sem_janela(self, *args, **kwargs):
        kwargs['creationflags'] = kwargs.get('creationflags', 0) | subprocess.CREATE_NO_WINDOW
        if kwargs.get('startupinfo') is None:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs['startupinfo'] = si
        return _popen_init_original(self, *args, **kwargs)

    subprocess.Popen.__init__ = _popen_init_sem_janela


# --- Localização do ffmpeg/ffprobe (script ou .exe empacotado) --------------
def _resolve_ffmpeg_path() -> str:
    """
    Caminho do ffmpeg: no .exe do PyInstaller, o ffmpeg.exe embutido
    (_MEIPASS ou ao lado do executável); rodando como script, 'ffmpeg' (PATH).
    """
    if getattr(sys, 'frozen', False):
        base_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        candidate = base_dir / 'ffmpeg.exe'
        if candidate.exists():
            return str(candidate)
        # build --onedir: ao lado do .exe
        candidate2 = Path(sys.executable).parent / 'ffmpeg.exe'
        if candidate2.exists():
            return str(candidate2)
    return 'ffmpeg'


def _resolve_ffprobe_path() -> str:
    """Igual a _resolve_ffmpeg_path, para o ffprobe."""
    if getattr(sys, 'frozen', False):
        base_dir = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
        candidate = base_dir / 'ffprobe.exe'
        if candidate.exists():
            return str(candidate)
        candidate2 = Path(sys.executable).parent / 'ffprobe.exe'
        if candidate2.exists():
            return str(candidate2)
    return 'ffprobe'


FFMPEG_PATH = _resolve_ffmpeg_path()
FFPROBE_PATH = _resolve_ffprobe_path()


def _usar_ffmpeg_do_programa():
    """
    Faz o programa inteiro (inclusive bibliotecas) usar o ffmpeg embutido:
    põe a pasta dele no PATH e configura a pydub. Sem isso, num computador
    sem ffmpeg instalado, a pydub falha com "[WinError 2]".
    """
    try:
        pasta = os.path.dirname(FFMPEG_PATH) if os.path.isabs(FFMPEG_PATH) else ''
        if pasta:
            atual = os.environ.get('PATH', '')
            if pasta.lower() not in [p.lower() for p in atual.split(os.pathsep)]:
                os.environ['PATH'] = pasta + os.pathsep + atual
    except Exception:
        pass
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            from pydub import AudioSegment as _AS
        _AS.converter = FFMPEG_PATH
        _AS.ffmpeg = FFMPEG_PATH
        _AS.ffprobe = FFPROBE_PATH
    except Exception:
        pass


_usar_ffmpeg_do_programa()


def _subprocess_no_window_kwargs() -> dict:
    """Kwargs de subprocess que evitam janela de console no Windows ({} nos demais)."""
    if sys.platform == 'win32':
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        return {'startupinfo': si, 'creationflags': subprocess.CREATE_NO_WINDOW}
    return {}


TAXAS_MP3 = [32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320]


def duracao_do_arquivo(arquivo):
    """Duração em segundos (ffprobe), ou None se não der pra medir."""
    import subprocess as _sp
    try:
        r = _sp.run([FFPROBE_PATH, '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', str(arquivo)],
                    capture_output=True, text=True, timeout=15,
                    **_subprocess_no_window_kwargs())
        return float(r.stdout.strip())
    except Exception:
        return None


def medir_bitrate_fonte(arquivo):
    """
    Bitrate do áudio do arquivo em kbps (ffprobe), ou None.

    Prefere o bitrate do stream: o do contêiner superestima opus (128k é
    relatado como ~145k). Quando o stream não informa (opus/webm), usa o
    do contêiner sem desconto.
    """
    import subprocess as _sp
    def _ffprobe(args):
        try:
            r = _sp.run([FFPROBE_PATH, '-v', 'error'] + args +
                        ['-of', 'default=noprint_wrappers=1:nokey=1', str(arquivo)],
                        capture_output=True, text=True, timeout=15,
                        **_subprocess_no_window_kwargs())
            t = r.stdout.strip()
            return int(t) // 1000 if t.isdigit() else None
        except Exception:
            return None

    # 1) o stream de áudio - exato quando existe (aac/mp3)
    b = _ffprobe(['-select_streams', 'a:0', '-show_entries', 'stream=bit_rate'])
    if b:
        return b
    # 2) o contêiner (opus/webm não expõem o stream). Sem descontar overhead:
    #    o valor também escolhe a taxa do MP3, e errar pra baixo perde
    #    qualidade (53k viraria 48k); errar pra cima custa só alguns KB.
    b =_ffprobe(['-show_entries', 'format=bit_rate'])
    if b:
        return b
    return None


def taxa_mp3_para(fonte_kbps):
    """
    Taxa de MP3 (kbps, de TAXAS_MP3) para uma fonte de 'fonte_kbps'.

    Segue a fonte: subir não recupera o que não foi gravado (só gasta
    disco) e descer perde qualidade de vez. Sem fonte conhecida, 192.
    """
    if not fonte_kbps or fonte_kbps <= 0:
        return 192
    # Nunca abaixo da fonte, com tolerância de 5%: 129k vira 128k (inaudível),
    # não 160k (24% maior à toa). Fora da margem, sobe pra próxima taxa.
    abaixo = [t for t in TAXAS_MP3 if t <= fonte_kbps]
    if abaixo and abaixo[-1] >= fonte_kbps * 0.95:
        return abaixo[-1]
    acima = [t for t in TAXAS_MP3 if t >= fonte_kbps]
    return acima[0] if acima else TAXAS_MP3[-1]

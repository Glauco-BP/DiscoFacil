"""
DiscoFácil - ponto de entrada.

Baixa álbuns completos do YouTube e separa as faixas. O Discogs é a fonte de
metadados (artista, álbum, faixas, capa, master_id/release_id); o YouTube só
fornece o áudio e pistas (título, descrição, capítulos).

Este arquivo só prepara o ambiente e abre a janela. O mapa dos módulos está
em ARQUITETURA.md. Os nomes reexportados abaixo são os que os testes (e
quem lê o código pela primeira vez) procuram aqui.
"""
# 1. Primeiro: blindagem do subprocess no Windows e o ffmpeg que vem com o programa.
import audio_util  # noqa: F401 (o import já aplica a blindagem)
# 2. Antes de qualquer "import yt_dlp": usa a cópia atualizada do yt-dlp, se houver.
import dependencias
dependencias.YTDLP_LOCAL_ATIVO = dependencias.ativar_ytdlp_local()

import tkinter as tk  # noqa: E402

from versao import APP_VERSION, APP_TITULO  # noqa: E402,F401
from audio_util import (FFMPEG_PATH, FFPROBE_PATH, duracao_do_arquivo,  # noqa: E402,F401
                        medir_bitrate_fonte, taxa_mp3_para)
from util import onde_quebrou, sanitize, segundos_da_faixa  # noqa: E402,F401
from ajustes import CutTuning  # noqa: E402,F401
from corte_audio import duracao_do_silencio, posicao_de_corte_no_silencio  # noqa: E402,F401
from corte_estrategias import SmartCutter, match_durations_to_tracks  # noqa: E402,F401
from corte_album import AlbumCutter  # noqa: E402,F401
from ui_util import _menu_de_contexto, instalar_menu_contexto, tipo_do_link  # noqa: E402,F401
from downloader import YouTubeDownloader  # noqa: E402,F401
from metadata_manager import MetadataManager  # noqa: E402,F401
from janela_config import SettingsWindow  # noqa: E402,F401
from janela_principal import FullTracksDownloaderGUI  # noqa: E402


def main():
    root = tk.Tk()
    app = FullTracksDownloaderGUI(root)  # noqa: F841 (a janela segura a referência)
    root.mainloop()


if __name__ == "__main__":
    main()

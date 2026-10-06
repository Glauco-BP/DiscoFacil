# Programas e bibliotecas de terceiros

O DiscoFácil é distribuído sob a [GPL-3.0](LICENSE). O `.exe` inclui ou usa os componentes abaixo, cada um com a sua licença.

| Componente | Pra quê | Licença | Código-fonte |
|---|---|---|---|
| Python 3.12 (e Tcl/Tk) | a linguagem e as janelas | PSF / BSD | https://www.python.org |
| FFmpeg e FFprobe (build "win64-gpl" de BtbN), **embutidos no .exe** | decodificar, medir e cortar o áudio | GPL-3.0 | https://ffmpeg.org · https://github.com/BtbN/FFmpeg-Builds |
| yt-dlp | baixar o áudio do YouTube (atualizado sozinho pelo programa) | Unlicense (domínio público) | https://github.com/yt-dlp/yt-dlp |
| Deno (baixado pelo programa na primeira vez) | exigido pelo YouTube pra liberar o áudio de boa qualidade | MIT | https://github.com/denoland/deno |
| mutagen | tags ID3 dos MP3 | GPL-2.0 ou posterior | https://github.com/quodlibet/mutagen |
| NumPy | análise do áudio | BSD-3-Clause | https://github.com/numpy/numpy |
| requests | Discogs, MusicBrainz, Deezer, iTunes, capas | Apache-2.0 | https://github.com/psf/requests |
| certifi | certificados de segurança | MPL-2.0 | https://github.com/certifi/python-certifi |
| sounddevice (com PortAudio) | o som da tela "Conferir cortes" | MIT | https://github.com/spatialaudio/python-sounddevice · http://www.portaudio.com |
| pydub | leitura de áudio | MIT | https://github.com/jiaaro/pydub |
| groq (opcional) | sugestões de IA, só com chave | Apache-2.0 | https://github.com/groq/groq-python |
| PyInstaller | gerar o .exe | GPL-2.0 com exceção para o programa gerado | https://github.com/pyinstaller/pyinstaller |

Serviços consultados (cada usuário com a sua chave, quando há): Discogs (dados © Discogs, sob os termos da API), MusicBrainz (dados CC0), Deezer e iTunes (só durações das faixas), YouTube.

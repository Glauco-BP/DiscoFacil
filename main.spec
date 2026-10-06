# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
# DiscoFacil (versão em versao.py) - Especificação de build do PyInstaller
# ============================================================================
# Gera um único .exe portátil, com o FFmpeg embutido dentro dele.
#
# NÃO EDITE este arquivo manualmente a menos que saiba o que está fazendo.
# Para gerar o .exe, rode build_exe.bat (ele chama este arquivo sozinho).
# ============================================================================

from PyInstaller.utils.hooks import collect_submodules, collect_data_files
import os

block_cipher = None

# --------------------------------------------------------------------------
# Módulos que carregam coisas dinamicamente e por isso o PyInstaller não
# detecta sozinho - precisam ser listados manualmente (senão o .exe final
# dá erro de "ModuleNotFoundError" só quando tenta usar aquela função
# específica, mesmo funcionando bem na maior parte do tempo).
# --------------------------------------------------------------------------
hidden_imports = []
hidden_imports += collect_submodules('yt_dlp')          # extractors carregados dinamicamente
hidden_imports += collect_submodules('mutagen')         # formatos de áudio
hidden_imports += collect_submodules('groq')
# Gerenciador de dependências (yt-dlp atualizado e Deno automáticos) e o
# zipimport que ele usa pra carregar o yt-dlp baixado por cima do embutido.
hidden_imports += ['dependencias', 'zipimport', 'versao']
hidden_imports += ['certifi']   # plano B de certificados pra baixar o Deno num Windows novo
hidden_imports += ['sounddevice', '_cffi_backend']   # som da tela "Conferir cortes" (tocador.py)

# --------------------------------------------------------------------------
# Arquivos de dados que alguns desses pacotes precisam (certificados,
# templates internos, etc.)
# --------------------------------------------------------------------------
datas = []
datas += collect_data_files('yt_dlp')
datas += collect_data_files('certifi')              # cacert.pem (ver dependencias._abrir)
try:
    datas += collect_data_files('_sounddevice_data')  # a DLL do PortAudio que vem com o sounddevice
except Exception:
    pass

# Ícone de disco de vinil: também incluído como dado (não só como ícone do
# .exe) para o programa conseguir carregá-lo em tempo de execução via
# root.iconbitmap() e usar no ícone da janela/taskbar, não só no arquivo
# .exe em si.
if os.path.exists('icone.ico'):
    datas.append(('icone.ico', '.'))
if os.path.exists('icone_vinil.png'):
    datas.append(('icone_vinil.png', '.'))

# --------------------------------------------------------------------------
# FFmpeg embutido: o build_exe.bat baixa ffmpeg.exe e ffprobe.exe para a
# pasta ffmpeg_bin\ antes de chamar o PyInstaller. Aqui só apontamos pra lá.
# --------------------------------------------------------------------------
ffmpeg_binaries = []
if os.path.exists(os.path.join('ffmpeg_bin', 'ffmpeg.exe')):
    ffmpeg_binaries.append(('ffmpeg_bin/ffmpeg.exe', '.'))
if os.path.exists(os.path.join('ffmpeg_bin', 'ffprobe.exe')):
    ffmpeg_binaries.append(('ffmpeg_bin/ffprobe.exe', '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='DiscoFacil',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # False = não abre janela de terminal preta junto
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icone.ico',       # ícone de disco de vinil (gerado em icone.ico)
)

@echo off
chcp 65001 > nul
title DiscoFacil - Gerador do Executavel
color 0B

echo.
echo ================================================================================
echo  YOUTUBE ALBUM RIPPER - GERADOR DO EXECUTAVEL (.exe)
echo ================================================================================
echo.
echo Este script cria o arquivo DiscoFacil.exe, que voce depois pode
echo distribuir para os seus amigos. Eles NAO vao precisar instalar Python
echo nem FFmpeg - so vao rodar o .exe direto.
echo.
echo  Isso e feito UMA VEZ (por voce). Depois de gerado, o .exe fica pronto
echo  para ser copiado e enviado quantas vezes quiser.
echo.
echo  Tempo estimado: 10-20 minutos (a primeira vez e mais demorada)
echo.
pause

REM ============================================================================
REM ETAPA 1: Verifica Python
REM ============================================================================
echo.
echo ================================================================================
echo ETAPA 1/5: VERIFICANDO PYTHON
echo ================================================================================
echo.

python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo [ERRO] Python nao esta instalado ou nao esta no PATH!
    echo.
    echo Baixe em: https://www.python.org/downloads/
    echo Durante a instalacao, MARQUE: "Add python.exe to PATH"
    echo.
    pause
    exit /b 1
)
python --version
echo [OK] Python encontrado!

REM ============================================================================
REM ETAPA 2: Verifica se todos os arquivos necessarios estao presentes
REM ============================================================================
echo.
echo ================================================================================
echo ETAPA 2/5: VERIFICANDO ARQUIVOS DO PROJETO
echo ================================================================================
echo.

if not exist main.py (
    echo [ERRO] main.py nao encontrado nesta pasta!
    echo        Rode este .bat de dentro da pasta do projeto.
    pause
    exit /b 1
)
if not exist main.spec (
    echo [ERRO] main.spec nao encontrado nesta pasta!
    pause
    exit /b 1
)
if not exist requirements.txt (
    echo [ERRO] requirements.txt nao encontrado nesta pasta!
    pause
    exit /b 1
)
echo [OK] Arquivos principais encontrados.

REM ============================================================================
REM ETAPA 3: Instala PyInstaller e as dependencias do projeto
REM ============================================================================
echo.
echo ================================================================================
echo ETAPA 3/5: INSTALANDO DEPENDENCIAS DE BUILD
echo ================================================================================
echo.
echo  Isso pode demorar varios minutos...
echo.

python -m pip install --upgrade pip > nul 2>&1
python -m pip install numpy
python -m pip install -r requirements.txt
python -m pip install pyinstaller

if %errorlevel% neq 0 (
    echo.
    echo [AVISO] Algo pode ter falhado na instalacao. Tentando continuar mesmo assim...
    echo.
)
echo.
echo [OK] Dependencias instaladas.

REM ============================================================================
REM ETAPA 4: Baixa o FFmpeg (so baixa se ainda nao tiver)
REM ============================================================================
echo.
echo ================================================================================
echo ETAPA 4/5: PREPARANDO O FFMPEG (sera embutido dentro do .exe)
echo ================================================================================
echo.

if exist ffmpeg_bin\ffmpeg.exe if exist ffmpeg_bin\ffprobe.exe (
    echo [OK] FFmpeg ja esta preparado em ffmpeg_bin\ - pulando download.
    goto ffmpeg_pronto
)

echo Baixando FFmpeg automaticamente (isso pode demorar alguns minutos,
echo o arquivo tem cerca de 100 MB)...
echo.

if not exist ffmpeg_bin mkdir ffmpeg_bin
if not exist ffmpeg_temp mkdir ffmpeg_temp

REM Gera um script PowerShell temporario (mais confiavel do que rodar
REM comandos PowerShell multi-linha direto dentro do .bat)
> ffmpeg_temp\baixar.ps1 echo $ProgressPreference = 'SilentlyContinue'
>> ffmpeg_temp\baixar.ps1 echo try {
>> ffmpeg_temp\baixar.ps1 echo     Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'ffmpeg_temp\ffmpeg.zip'
>> ffmpeg_temp\baixar.ps1 echo     Write-Host '[OK] Download concluido'
>> ffmpeg_temp\baixar.ps1 echo } catch {
>> ffmpeg_temp\baixar.ps1 echo     Write-Host '[ERRO] Falha ao baixar o FFmpeg automaticamente'
>> ffmpeg_temp\baixar.ps1 echo     Write-Host $_.Exception.Message
>> ffmpeg_temp\baixar.ps1 echo     exit 1
>> ffmpeg_temp\baixar.ps1 echo }

powershell -NoProfile -ExecutionPolicy Bypass -File ffmpeg_temp\baixar.ps1

if %errorlevel% neq 0 (
    echo.
    echo [ERRO] Nao foi possivel baixar o FFmpeg automaticamente.
    echo.
    echo SOLUCAO MANUAL:
    echo    1. Baixe em: https://github.com/BtbN/FFmpeg-Builds/releases
    echo       arquivo: ffmpeg-master-latest-win64-gpl.zip
    echo    2. Extraia o ZIP
    echo    3. Va na pasta "bin" dentro do que voce extraiu
    echo    4. Copie ffmpeg.exe e ffprobe.exe para a pasta ffmpeg_bin\ aqui do projeto
    echo    5. Rode este build_exe.bat novamente
    echo.
    pause
    exit /b 1
)

echo Extraindo FFmpeg...
> ffmpeg_temp\extrair.ps1 echo Expand-Archive -Path 'ffmpeg_temp\ffmpeg.zip' -DestinationPath 'ffmpeg_temp' -Force
powershell -NoProfile -ExecutionPolicy Bypass -File ffmpeg_temp\extrair.ps1

REM Procura ffmpeg.exe e ffprobe.exe dentro da pasta extraida (o nome da
REM subpasta muda de versao pra versao, entao procuramos recursivamente)
for /r ffmpeg_temp %%f in (ffmpeg.exe) do copy "%%f" ffmpeg_bin\ffmpeg.exe > nul
for /r ffmpeg_temp %%f in (ffprobe.exe) do copy "%%f" ffmpeg_bin\ffprobe.exe > nul

if not exist ffmpeg_bin\ffmpeg.exe (
    echo [ERRO] Nao encontrei ffmpeg.exe apos extrair. Veja a SOLUCAO MANUAL acima.
    pause
    exit /b 1
)
if not exist ffmpeg_bin\ffprobe.exe (
    echo [ERRO] Nao encontrei ffprobe.exe apos extrair. Veja a SOLUCAO MANUAL acima.
    pause
    exit /b 1
)

rmdir /s /q ffmpeg_temp > nul 2>&1
echo [OK] FFmpeg pronto em ffmpeg_bin\

:ffmpeg_pronto

REM ============================================================================
REM ETAPA 5: Gera o .exe com PyInstaller
REM ============================================================================
echo.
echo ================================================================================
echo ETAPA 5/5: GERANDO O EXECUTAVEL (.exe)
echo ================================================================================
echo.
echo  Isso pode demorar de 5 a 15 minutos. Nao feche esta janela.
echo.

if exist build rmdir /s /q build > nul 2>&1
if exist dist rmdir /s /q dist > nul 2>&1

python -m PyInstaller main.spec --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo ================================================================================
    echo [ERRO] A GERACAO DO .EXE FALHOU
    echo ================================================================================
    echo.
    echo Copie TODO o erro acima e cole numa IA (ChatGPT, Claude, Gemini) junto
    echo com este script (build_exe.bat) pedindo ajuda para resolver.
    echo.
    pause
    exit /b 1
)

if not exist dist\DiscoFacil.exe (
    echo.
    echo [ERRO] O PyInstaller rodou mas o .exe nao foi encontrado em dist\
    echo        Algo inesperado aconteceu.
    pause
    exit /b 1
)

REM ============================================================================
REM Organiza a pasta final de entrega
REM ============================================================================
if not exist EXE_PRONTO mkdir EXE_PRONTO
copy dist\DiscoFacil.exe EXE_PRONTO\DiscoFacil.exe > nul
if exist MANUAL_COMPLETO.txt copy MANUAL_COMPLETO.txt EXE_PRONTO\ > nul

echo.
echo ================================================================================
echo [OK] EXECUTAVEL GERADO COM SUCESSO!
echo ================================================================================
echo.
echo  O arquivo esta em:
echo    EXE_PRONTO\DiscoFacil.exe
echo.
echo  PROXIMOS PASSOS:
echo.
echo    1. Teste o .exe voce mesmo antes de enviar (da um duplo-clique nele)
echo    2. Na primeira vez que abrir, clique em "Configuracoes" (canto
echo       superior direito) e cole suas chaves de API e a pasta de saida
echo    3. Envie a pasta EXE_PRONTO inteira (ou so o .exe) para os seus amigos
echo    4. Eles so precisam dar duplo-clique - nao precisam instalar nada!
echo.
echo  AVISO SOBRE O WINDOWS DEFENDER / SMARTSCREEN:
echo    Como o .exe nao tem uma assinatura digital paga, o Windows pode
echo    mostrar um aviso "Windows protegeu seu PC" na primeira vez que
echo    alguem abrir. Isso e normal para programas nao-assinados, nao
echo    significa que ha virus. Basta clicar em "Mais informacoes" e depois
echo    em "Executar assim mesmo".
echo.
echo ================================================================================
echo.
pause

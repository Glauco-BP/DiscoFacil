"""
dependencias.py - mantém atualizadas as peças externas, sem ação do usuário.

- yt-dlp: o YouTube muda e versões velhas baixam mal. Guarda uma cópia
  atualizada na pasta do usuário e a usa no lugar da embutida (que vira
  reserva).
- Deno: o yt-dlp precisa dele pros desafios JavaScript do YouTube; sem ele
  só o cliente android funciona e o áudio cai pra ~48kbps. Baixa uma cópia
  só pro programa se o computador não tiver.

Roda ao abrir o programa e depois de falhas de download, nunca por faixa.
A versão vem do redirecionamento de .../releases/latest, não da API do
GitHub (limite de 60 consultas/hora por IP). Sem rede ou permissão, segue
com o que já tem e avisa no log.
"""

import os
import sys
import json
import time
import shutil
import zipfile
import platform
import threading
import urllib.request
from pathlib import Path


URL_YTDLP_ULTIMA = "https://github.com/yt-dlp/yt-dlp/releases/latest"
URL_YTDLP_BAIXAR = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
URL_DENO_ULTIMA = "https://github.com/denoland/deno/releases/latest"
URL_DENO_BAIXAR = "https://github.com/denoland/deno/releases/latest/download/{arquivo}"

TEMPO_LIMITE = 30          # segundos por requisição
AGENTE = "DiscoFacil (+https://github.com/yt-dlp/yt-dlp)"


# --------------------------------------------------------------------------
# Onde guardar
# --------------------------------------------------------------------------

def pasta_ferramentas() -> Path:
    """
    Pasta gravável do usuário pras ferramentas (criada se não existir).

    Windows: %LOCALAPPDATA%\\DiscoFacil\\ferramentas; fora da pasta do
    programa porque "Arquivos de Programas" exige administrador.
    """
    if os.name == 'nt':
        base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~\\AppData\\Local')
    else:
        base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    p = Path(base) / 'DiscoFacil' / 'ferramentas'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _estado_arquivo() -> Path:
    return pasta_ferramentas() / 'estado.json'


def _ler_estado() -> dict:
    """Lê estado.json (versões baixadas); {} se não existir ou estiver inválido."""
    try:
        return json.loads(_estado_arquivo().read_text(encoding='utf-8'))
    except Exception:
        return {}


def _gravar_estado(estado: dict):
    """Grava estado.json de forma atômica; erros são ignorados."""
    try:
        tmp = _estado_arquivo().with_suffix('.tmp')
        tmp.write_text(json.dumps(estado, indent=2), encoding='utf-8')
        os.replace(tmp, _estado_arquivo())
    except Exception:
        pass


# --------------------------------------------------------------------------
# Rede
# --------------------------------------------------------------------------

ULTIMO_ERRO = {'deno': None}      # motivo da última falha, pra aparecer no log


def _abrir(req):
    """
    urlopen com plano B de certificados.

    Num Windows recém-instalado a lista de certificados raiz vem incompleta
    e o GitHub pode falhar com CERTIFICATE_VERIFY_FAILED. Nesse caso tenta
    de novo com os certificados do certifi (ainda verificando).
    """
    import ssl
    try:
        return urllib.request.urlopen(req, timeout=TEMPO_LIMITE)
    except Exception as e:
        motivo = str(getattr(e, 'reason', '') or e)
        if 'CERTIFICATE' not in motivo.upper() and 'SSL' not in motivo.upper():
            raise
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=TEMPO_LIMITE, context=ctx)


def _ultima_versao(url_latest: str):
    """
    Última versão publicada (ex.: '2026.09.01'), ou None.

    /releases/latest redireciona para .../releases/tag/<versão>; basta ler
    o destino, sem gastar o limite da API.
    """
    req = urllib.request.Request(url_latest, method='HEAD',
                                 headers={'User-Agent': AGENTE})
    with _abrir(req) as r:
        final = r.geturl()
    if '/tag/' not in final:
        return None
    return final.rsplit('/tag/', 1)[1].strip('/')


def _baixar(url: str, destino: Path, log=None, rotulo=''):
    """
    Baixa 'url' para 'destino' via arquivo temporário (nunca fica pela
    metade). Com 'log', informa o progresso a cada 25%.
    """
    tmp = destino.with_suffix(destino.suffix + '.baixando')
    req = urllib.request.Request(url, headers={'User-Agent': AGENTE})
    with _abrir(req) as r, open(tmp, 'wb') as f:
        total = int(r.headers.get('Content-Length') or 0)
        feito, ultimo_aviso = 0, 0
        while True:
            bloco = r.read(256 * 1024)
            if not bloco:
                break
            f.write(bloco)
            feito += len(bloco)
            # Sem sinal de vida, um arquivo grande (Deno ~40MB) parece travado.
            if log and total and feito * 4 // total > ultimo_aviso:
                ultimo_aviso = feito * 4 // total
                log(f"      {rotulo}: {min(100, ultimo_aviso * 25)}%")
    os.replace(tmp, destino)


# --------------------------------------------------------------------------
# yt-dlp
# --------------------------------------------------------------------------

def arquivo_ytdlp_local() -> Path:
    """Caminho da cópia baixada do yt-dlp (zip importável)."""
    return pasta_ferramentas() / 'yt-dlp.zip'


def versao_ytdlp_em_uso():
    """Versão do yt-dlp importável agora, ou None."""
    try:
        import yt_dlp
        return yt_dlp.version.__version__
    except Exception:
        return None


class _PreferirYtdlpLocal:
    """
    Localizador que faz 'import yt_dlp' carregar a cópia baixada.

    sys.path não basta no PyInstaller: o importador dele vem antes e acharia
    a cópia embutida. Este entra em sys.meta_path[0] e responde só por
    yt_dlp e submódulos.
    """

    def __init__(self, caminho_zip: Path):
        import zipimport
        self._imp = zipimport.zipimporter(str(caminho_zip))

    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'yt_dlp' or fullname.startswith('yt_dlp.'):
            try:
                return self._imp.find_spec(fullname)
            except Exception:
                return None
        return None


# True se o yt-dlp em uso é a cópia baixada (main.py grava ao abrir).
YTDLP_LOCAL_ATIVO = False


def ativar_ytdlp_local() -> bool:
    """
    Usa a cópia baixada do yt-dlp, se houver e importar. Chamar ANTES de
    qualquer 'import yt_dlp'. Se falhar, apaga a cópia e segue com a
    embutida. Devolve True se a cópia baixada ficou ativa.
    """
    zp = arquivo_ytdlp_local()
    if not zp.exists():
        return False
    try:
        if not zipfile.is_zipfile(zp):
            raise ValueError('arquivo não é zip')
        localizador = _PreferirYtdlpLocal(zp)
        if localizador.find_spec('yt_dlp') is None:
            raise ValueError('yt_dlp não encontrado dentro do arquivo')
        sys.meta_path.insert(0, localizador)
        # Importa já, dentro do try: uma versão que exija Python mais novo
        # quebraria depois, no downloader, e o programa não abriria.
        import yt_dlp  # noqa: F401
        return True
    except Exception:
        for k in [m for m in sys.modules if m == 'yt_dlp' or m.startswith('yt_dlp.')]:
            sys.modules.pop(k, None)
        sys.meta_path[:] = [f for f in sys.meta_path
                            if not isinstance(f, _PreferirYtdlpLocal)]
        try:
            zp.unlink()
        except Exception:
            pass
        return False


def atualizar_ytdlp(log=None, forcar=False) -> str:
    """
    Garante a cópia local do yt-dlp na última versão.

    Devolve 'atualizado', 'em_dia', 'sem_rede' ou 'erro'. A versão nova só
    vale na próxima abertura (o módulo já carregado não é trocado em uso).
    """
    estado = _ler_estado()
    try:
        ultima = _ultima_versao(URL_YTDLP_ULTIMA)
    except Exception:
        return 'sem_rede'
    if not ultima:
        return 'erro'

    local_ok = arquivo_ytdlp_local().exists()
    # Mesma versão não é baixada de novo, nem com 'forcar'.
    if local_ok and estado.get('ytdlp_versao') == ultima:
        return 'em_dia'
    if not local_ok and versao_ytdlp_em_uso() == ultima:
        return 'em_dia'

    try:
        if log:
            log(f"🔧 Atualizando o componente do YouTube (yt-dlp {ultima})...")
        _baixar(URL_YTDLP_BAIXAR, arquivo_ytdlp_local(), log, 'yt-dlp')
        if not zipfile.is_zipfile(arquivo_ytdlp_local()):
            arquivo_ytdlp_local().unlink()
            return 'erro'
        estado['ytdlp_versao'] = ultima
        estado['ytdlp_quando'] = time.time()
        _gravar_estado(estado)
        return 'atualizado'
    except Exception:
        return 'erro'


# --------------------------------------------------------------------------
# Deno
# --------------------------------------------------------------------------

def _nome_arquivo_deno():
    """O zip certo pra este computador, ou None se não houver."""
    s = platform.system().lower()
    m = platform.machine().lower()
    braco = m in ('arm64', 'aarch64')
    if s == 'windows':
        # Só há build x86_64; Windows ARM roda por emulação.
        return 'deno-x86_64-pc-windows-msvc.zip'
    if s == 'darwin':
        return 'deno-aarch64-apple-darwin.zip' if braco else 'deno-x86_64-apple-darwin.zip'
    if s == 'linux':
        return 'deno-aarch64-unknown-linux-gnu.zip' if braco else 'deno-x86_64-unknown-linux-gnu.zip'
    return None


def executavel_deno_local() -> Path:
    """Caminho da cópia do Deno instalada pelo programa."""
    return pasta_ferramentas() / ('deno.exe' if os.name == 'nt' else 'deno')


def localizar_deno():
    """Caminho do Deno: primeiro o do sistema (PATH), depois a cópia local; ou None."""
    no_sistema = shutil.which('deno')
    if no_sistema:
        return no_sistema
    local = executavel_deno_local()
    if local.exists():
        return str(local)
    return None


def garantir_deno(log=None) -> str:
    """
    Instala uma cópia do Deno só pro programa, se o computador não tiver.

    Devolve 'ja_tinha', 'instalado', 'sem_rede', 'nao_suportado' ou 'erro'
    (motivo em ULTIMO_ERRO['deno']). Não mexe no PATH: o caminho vai pro
    yt-dlp via opcoes_js_runtimes().
    """
    if localizar_deno():
        return 'ja_tinha'
    arquivo = _nome_arquivo_deno()
    if not arquivo:
        return 'nao_suportado'
    zp = pasta_ferramentas() / arquivo
    try:
        if log:
            log("🔧 Instalando o Deno (necessário pra baixar do YouTube na melhor "
                "qualidade). É só na primeira vez - cerca de 40 MB...")
        _baixar(URL_DENO_BAIXAR.format(arquivo=arquivo), zp, log, 'Deno')
    except Exception as e:
        ULTIMO_ERRO['deno'] = f"{type(e).__name__}: {str(getattr(e, 'reason', '') or e)[:120]}"
        return 'sem_rede'
    try:
        with zipfile.ZipFile(zp) as z:
            nome = next(n for n in z.namelist() if n.split('/')[-1] in ('deno', 'deno.exe'))
            destino = executavel_deno_local()
            tmp = destino.with_suffix('.tmp')
            with z.open(nome) as origem, open(tmp, 'wb') as saida:
                shutil.copyfileobj(origem, saida)
            os.replace(tmp, destino)
        if os.name != 'nt':
            destino.chmod(0o755)
        zp.unlink()
        return 'instalado'
    except Exception as e:
        ULTIMO_ERRO['deno'] = f"{type(e).__name__}: {str(e)[:120]}"
        return 'erro'


def opcoes_js_runtimes():
    """O que passar pro yt-dlp em 'js_runtimes'. {} se não houver Deno."""
    caminho = localizar_deno()
    if not caminho:
        return {}
    return {'js_runtimes': {'deno': {'path': caminho}}}


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------

class GerenciadorDeDependencias:
    """
    Garante Deno e yt-dlp em segundo plano, pra janela não congelar.

    O trabalhador de downloads chama esperar_pronto() antes de começar:
    sem o Deno, os primeiros álbuns sairiam em ~48kbps.
    """

    def __init__(self, log=None):
        self._log_real = log or (lambda m: None)
        self._pronto = threading.Event()
        self._lock = threading.Lock()
        self._ultima_verificacao_por_falha = 0.0

    def log(self, msg):
        """Mensagem pro usuário que nunca derruba a verificação."""
        try:
            self._log_real(msg)
        except Exception:
            pass

    def verificar_ao_abrir(self):
        """Dispara a verificação inicial numa thread."""
        threading.Thread(target=self._verificar, args=(False,), daemon=True).start()

    def verificar_apos_falha(self):
        """
        Reverifica após falha de download, no máximo a cada 30 min (não
        adianta insistir a cada faixa se o GitHub está fora).
        """
        agora = time.time()
        if agora - self._ultima_verificacao_por_falha < 1800:
            return
        self._ultima_verificacao_por_falha = agora
        threading.Thread(target=self._verificar, args=(True,), daemon=True).start()

    def esperar_pronto(self, limite=180):
        """Espera a verificação terminar (até 'limite' s); True se terminou."""
        return self._pronto.wait(timeout=limite)

    def _verificar(self, por_falha):
        """Instala o Deno (até 3 tentativas) e atualiza o yt-dlp; sempre libera esperar_pronto()."""
        with self._lock:
            try:
                # 3 tentativas (0, 15 e 45 s): falha passageira não exige reabrir.
                r = 'erro'
                for tentativa, espera in enumerate((0, 15, 45), 1):
                    if espera:
                        self.log(f"   🔁 Tentando instalar o Deno de novo em {espera}s "
                                 f"(tentativa {tentativa} de 3)...")
                        time.sleep(espera)
                    r = garantir_deno(self.log)
                    if r not in ('sem_rede', 'erro'):
                        break
                    self.log(f"   ⚠️  Falhou: {ULTIMO_ERRO.get('deno') or 'motivo desconhecido'}")
                if r == 'instalado':
                    self.log("✅ Deno instalado.")
                elif r in ('sem_rede', 'erro'):
                    self.log("⚠️  Não consegui instalar o Deno agora (sem internet?). "
                             "Os downloads funcionam, mas podem sair em qualidade menor. "
                             "Vou tentar de novo na próxima abertura.")

                r = atualizar_ytdlp(self.log, forcar=por_falha)
                if r == 'atualizado':
                    self.log("✅ Componente do YouTube atualizado. A versão nova passa "
                             "a valer quando o programa for aberto de novo.")
                elif r == 'erro':
                    self.log("⚠️  Não consegui atualizar o componente do YouTube agora.")
            finally:
                self._pronto.set()

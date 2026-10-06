"""
Arquivo de log por rodada: <pasta de saída>/logs/DiscoFacil_<data_hora>.log,
um por abertura do programa, pra anexar quando algo der errado.

Tem tudo o que vai pro log da tela (com hora) e linhas de diagnóstico com
etiqueta pra busca: [RODADA] [CONFIG] [DISCO] [FONTE] [NOTAS] [PENDENTE]
[REJEITADO] [FILA] [PRONTO] [ERRO] (com arquivo:linha e traceback) [AVISO].

Segurança: chaves aparecem só como "configurada"/"não configurada", e
qualquer valor de chave que surja numa linha é trocado por "***".
"""
import os
import sys
import time
import threading
import traceback

ETIQUETAS = ('RODADA', 'CONFIG', 'DISCO', 'FONTE', 'NOTAS', 'PENDENTE',
             'REJEITADO', 'PRONTO', 'ERRO', 'AVISO', 'FILA')

# Chaves de API: caminho(s) no config.json -> nome mostrado no log
CHAVES = (
    (('api_keys.discogs_token',), 'Discogs'),
    (('api_keys.groq',), 'Groq'),
    (('api_keys.youtube_data', 'api_keys.google_custom_search'), 'YouTube Data API'),
)


def _valor(config, chave, padrao=None):
    """config.get() tolerante a falha."""
    try:
        return config.get(chave, padrao)
    except Exception:
        return padrao


def valores_secretos(config):
    """Todos os valores de chave/token presentes na config (pra mascarar)."""
    segredos = set()
    try:
        api = _valor(config, 'api_keys', {}) or {}

        def _varrer(x):
            if isinstance(x, dict):
                for v in x.values():
                    _varrer(v)
            elif isinstance(x, str) and len(x.strip()) >= 6:
                segredos.add(x.strip())
        _varrer(api)
    except Exception:
        pass
    return segredos


def resumo_configuracoes(config, versao, confianca_minima=None, navegador_cookies=None):
    """
    Linhas com as configurações que importam pra diagnóstico.
    As chaves aparecem só como "configurada"/"não configurada".
    """
    def sim_nao(chaves):
        for chave in chaves:
            v = _valor(config, chave, '')
            if isinstance(v, dict):
                v = v.get('api_key', '')
            if isinstance(v, str) and v.strip():
                return 'configurada'
        return 'não configurada'

    pasta = ''
    try:
        pasta = config.get_output_directory()
    except Exception:
        pass
    bitrate = _valor(config, 'settings.min_bitrate_kbps', 80)
    if confianca_minima is None:
        confianca_minima = _valor(config, 'settings.auto_process_min_confidence_pct', 80)
    nav = navegador_cookies or _valor(config, 'settings.cookies_browser', '') or 'automático'
    linhas = [
        f"Versão: {versao}",
        f"Pasta de saída: {pasta or '(não configurada)'}",
        f"Bitrate mínimo: {bitrate} kbps",
        f"Confiança mínima pra baixar sem perguntar: {confianca_minima}%",
        f"Navegador dos cookies: {nav}",
        "Correções do ✂ Editar: " + ("guardadas em logs/correcoes_do_editor.txt"
                                     if _valor(config, 'settings.gravar_correcoes_editor', True) else "não guardadas"),
        "Chaves: " + " · ".join(f"{nome} {sim_nao(ch)}" for ch, nome in CHAVES),
    ]
    return linhas


class RegistroDaRodada:
    """
    Um arquivo por abertura do programa; seguro pra chamar de qualquer thread.
    Linhas escritas antes de abrir() (sem pasta de saída) ficam em memória e
    são gravadas quando o arquivo abre.
    """

    def __init__(self, versao, config=None):
        self.versao = versao
        self.config = config
        self.caminho = None
        self._arq = None
        self._trava = threading.Lock()
        self._antes_de_abrir = []        # linhas escritas antes de haver pasta de saída
        self._inicio = time.strftime('%Y-%m-%d_%H-%M-%S')
        self._segredos = valores_secretos(config) if config is not None else set()

    # ------------------------------------------------------------------
    def abrir(self, pasta_saida):
        """Abre (ou troca) o arquivo, na subpasta logs da pasta de saída."""
        if not pasta_saida:
            return None
        pasta_logs = os.path.join(pasta_saida, 'logs')
        novo = os.path.join(pasta_logs, f"DiscoFacil_{self._inicio}.log")
        with self._trava:
            if self.caminho == novo and self._arq:
                return self.caminho
            try:
                os.makedirs(pasta_logs, exist_ok=True)
                arq = open(novo, 'a', encoding='utf-8', newline='\n')
            except Exception:
                return None
            if self._arq:
                try:
                    self._arq.close()
                except Exception:
                    pass
            self._arq = arq
            self.caminho = novo
            pendentes, self._antes_de_abrir = self._antes_de_abrir, []
            for linha in pendentes:
                self._gravar(linha)
        return self.caminho

    def atualizar_segredos(self, config=None):
        """Relê da config os valores a mascarar (após salvar Configurações)."""
        if config is not None:
            self.config = config
        if self.config is not None:
            self._segredos = valores_secretos(self.config)

    def _mascarar(self, texto):
        """Troca por *** qualquer valor de chave presente no texto."""
        for s in self._segredos:
            if s and s in texto:
                texto = texto.replace(s, '***')
        return texto

    def _gravar(self, linha):
        """Escreve uma linha já formatada (chamar com a trava). Sem arquivo, acumula (até ~5000)."""
        if self._arq is None:
            self._antes_de_abrir.append(linha)
            if len(self._antes_de_abrir) > 5000:
                del self._antes_de_abrir[:1000]
            return
        try:
            self._arq.write(linha + '\n')
            self._arq.flush()
        except Exception:
            pass

    # ------------------------------------------------------------------
    def linha(self, texto, etiqueta=None):
        """Grava uma linha (ou várias) com hora e etiqueta opcional."""
        try:
            texto = self._mascarar(str(texto))
        except Exception:
            return
        hora = time.strftime('%H:%M:%S')
        prefixo = f"{hora} " + (f"[{etiqueta}] " if etiqueta else "")
        partes = texto.split('\n')
        with self._trava:
            for p in partes:
                if not p.strip() and len(partes) > 1:
                    continue
                self._gravar(prefixo + p)

    def erro(self, exc, contexto=''):
        """[ERRO] com o local (arquivo:linha) e o traceback inteiro. Devolve o local."""
        try:
            quadro = traceback.extract_tb(exc.__traceback__)[-1]
            onde = f"{os.path.basename(quadro.filename)}:{quadro.lineno} em {quadro.name}"
        except Exception:
            onde = 'local desconhecido'
        msg = f"{contexto + ': ' if contexto else ''}{type(exc).__name__}: {exc} @ {onde}"
        self.linha(msg, 'ERRO')
        try:
            tb = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            self.linha('    ' + tb.rstrip().replace('\n', '\n    '))
        except Exception:
            pass
        return onde

    def cabecalho(self, linhas_config):
        """Início da rodada: versão, Python/plataforma e as linhas [CONFIG]."""
        self.linha('=' * 70)
        self.linha(f"DiscoFácil {self.versao} - rodada iniciada em {time.strftime('%d/%m/%Y %H:%M:%S')}", 'RODADA')
        self.linha(f"Python {sys.version.split()[0]} · {sys.platform}"
                   f"{' · executável' if getattr(sys, 'frozen', False) else ''}", 'RODADA')
        for l in linhas_config or []:
            self.linha(l, 'CONFIG')

    def fechar(self):
        with self._trava:
            if self._arq:
                try:
                    self._arq.close()
                except Exception:
                    pass
                self._arq = None

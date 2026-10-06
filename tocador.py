"""
Tocador de áudio da tela "Conferir cortes" (janela_editor.py).

O Tkinter não toca som: aqui o ffmpeg decodifica o disco a partir de um
ponto (sem carregar o arquivo inteiro na memória) e a biblioteca
`sounddevice` (PortAudio) manda pro alto-falante. Sem a biblioteca (ou sem
placa de som), `disponivel` fica False e `motivo` diz por quê - a tela
continua funcionando, só sem som.

Uso: t = Tocador(); t.tocar(arquivo, 125.0, fim=135.0); t.posicao(); t.pausar()
"""
import collections
import subprocess
import threading
import time

from audio_util import FFMPEG_PATH, _subprocess_no_window_kwargs

TAXA = 44100
CANAIS = 2
BYTES_QUADRO = 2 * CANAIS                # s16le estéreo
BLOCO_LEITURA = 8192


def _carregar_sounddevice():
    """O módulo sounddevice, ou (None, motivo) se não der pra usar."""
    try:
        import sounddevice
        return sounddevice, None
    except ImportError:
        return None, "a biblioteca de som (sounddevice) não está instalada"
    except OSError as e:                  # PortAudio ausente (Linux sem libportaudio)
        return None, f"o sistema de som não está disponível ({str(e)[:60]})"


class _Sessao:
    """Um "tocar": o seu ffmpeg, a sua fila e o seu fim. Ao tocar de novo nasce outra, e o que a
    anterior ainda ler (a thread dela demora um instante pra morrer) não se mistura com a nova."""

    def __init__(self, inicio, fim):
        self.inicio, self.fim = inicio, fim
        self.fila = collections.deque()
        self.pendente = b''
        self.fim_dos_dados = False
        self.quadros = 0
        self.proc = None
        self.stream = None
        self.ativa = True


class Tocador:
    """Toca um trecho do arquivo; a posição é contada pelos quadros que já saíram."""

    def __init__(self, sd=None):
        if sd is None:
            sd, motivo = _carregar_sounddevice()
        else:
            motivo = None
        self._sd = sd
        self.disponivel = sd is not None
        self.motivo = motivo
        self._trava = threading.Lock()
        self._sessao = None
        self.tocando = False
        self._parado_em = 0.0
        self.ao_terminar = None          # chamado (sem argumentos) quando o trecho acaba sozinho

    # ------------------------------------------------------------------ comandos
    def tocar(self, arquivo, inicio=0.0, fim=None):
        """Começa a tocar `arquivo` em `inicio` (s) até `fim` (s) ou o fim do disco."""
        self.pausar()
        if not self.disponivel:
            return False
        se = _Sessao(max(0.0, float(inicio)), fim)
        cmd = [FFMPEG_PATH, '-v', 'error', '-ss', f'{se.inicio:.3f}', '-i', str(arquivo)]
        if fim is not None:
            cmd += ['-t', f'{max(0.05, fim - se.inicio):.3f}']
        cmd += ['-f', 's16le', '-acodec', 'pcm_s16le', '-ac', str(CANAIS), '-ar', str(TAXA), '-']
        try:
            se.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                       **_subprocess_no_window_kwargs())
            threading.Thread(target=self._ler, args=(se,), daemon=True).start()
            se.stream = self._sd.RawOutputStream(samplerate=TAXA, channels=CANAIS, dtype='int16',
                                                 callback=lambda *a: self._callback(se, *a),
                                                 finished_callback=lambda: self._acabou(se))
            self._sessao = se
            self.tocando = True
            se.stream.start()
            return True
        except Exception as e:
            # sem saída de som (fone tirado, placa ocupada...): a tela continua, sem som
            self._encerrar(se)
            self._sessao, self.tocando = None, False
            self.disponivel = False
            self.motivo = f"não consegui abrir a saída de som ({str(e)[:60]})"
            return False

    def pausar(self):
        """Para e guarda onde parou (posicao() continua valendo)."""
        if self.tocando:
            self._parado_em = self.posicao()
        self.tocando = False
        se, self._sessao = self._sessao, None
        if se is not None:
            self._encerrar(se)

    @staticmethod
    def _encerrar(se):
        se.ativa = False
        if se.stream is not None:
            try:
                se.stream.abort()
                se.stream.close()
            except Exception:
                pass
        if se.proc is not None:
            try:
                se.proc.kill()
                se.proc.wait(timeout=2)       # no Windows, o arquivo só fica livre quando o ffmpeg sai de vez
            except Exception:
                pass

    def posicao(self):
        """Segundo do disco que está saindo agora (ou onde parou)."""
        se = self._sessao
        if not self.tocando or se is None:
            return self._parado_em
        return se.inicio + se.quadros / float(TAXA)

    def fechar(self):
        self.ao_terminar = None
        self.pausar()

    # ------------------------------------------------------------------ por dentro
    def _ler(self, se):
        """Thread: lê o PCM do ffmpeg da sessão e enfileira; o callback do som só consome."""
        try:
            while se.ativa:
                bloco = se.proc.stdout.read(BLOCO_LEITURA)
                if not bloco:
                    break
                with self._trava:
                    se.fila.append(bloco)
                while len(se.fila) > 64 and se.ativa:          # ~3s adiantado basta
                    time.sleep(0.01)
        except Exception:
            pass
        se.fim_dos_dados = True

    def _callback(self, se, saida, quadros, info, status):
        """Chamado pelo PortAudio: preenche `saida` com `quadros` quadros."""
        precisa = quadros * BYTES_QUADRO
        partes, tem = [se.pendente], len(se.pendente)
        with self._trava:
            while tem < precisa and se.fila:
                b = se.fila.popleft()
                partes.append(b)
                tem += len(b)
        dados = b''.join(partes)
        usar, se.pendente = dados[:precisa], dados[precisa:]
        if len(usar) < precisa:
            if se.fim_dos_dados and not se.fila:
                saida[:len(usar)] = usar
                saida[len(usar):] = b'\x00' * (precisa - len(usar))
                se.quadros += len(usar) // BYTES_QUADRO
                raise self._sd.CallbackStop()
            # atraso na leitura: um instante de silêncio, que não conta como disco tocado
            inteiros = len(usar) // BYTES_QUADRO * BYTES_QUADRO      # meio quadro espera o resto chegar
            usar, se.pendente = usar[:inteiros], usar[inteiros:]
            se.quadros += inteiros // BYTES_QUADRO
            saida[:] = usar + b'\x00' * (precisa - len(usar))
            return
        saida[:] = usar
        se.quadros += quadros

    def _acabou(self, se):
        """O trecho terminou sozinho (fim do disco ou do intervalo) - só vale pra sessão atual."""
        if self.tocando and self._sessao is se and se.ativa:
            self._parado_em = se.inicio + se.quadros / float(TAXA)
            self.tocando = False
            cb = self.ao_terminar
            if cb:
                try:
                    cb()
                except Exception:
                    pass


class TocadorFalso:
    """Pros testes (sem placa de som): finge que toca, a posição anda com o relógio."""

    def __init__(self):
        self.disponivel, self.motivo = True, None
        self.tocando = False
        self.chamadas = []
        self._inicio, self._t0, self._fim, self._parado_em = 0.0, 0.0, None, 0.0
        self.ao_terminar = None
        self.velocidade = 1.0

    def tocar(self, arquivo, inicio=0.0, fim=None):
        self.chamadas.append(('tocar', round(float(inicio), 2), None if fim is None else round(float(fim), 2)))
        self._inicio, self._fim, self._t0, self.tocando = float(inicio), fim, time.time(), True
        return True

    def posicao(self):
        if not self.tocando:
            return self._parado_em
        p = self._inicio + (time.time() - self._t0) * self.velocidade
        if self._fim is not None and p >= self._fim:
            self.tocando, self._parado_em = False, self._fim
            return self._fim
        return p

    def pausar(self):
        if self.tocando:
            self._parado_em = self.posicao()
            self.chamadas.append(('pausar', round(self._parado_em, 2)))
        self.tocando = False

    def fechar(self):
        self.pausar()

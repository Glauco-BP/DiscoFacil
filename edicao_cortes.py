"""
Conferir e editar os cortes de um disco à mão (a parte sem janela; a tela é
janela_editor.py).

Duas origens:
  - disco em "Precisam de você": o áudio fica guardado em
    <pasta dos discos>/.audios_pasta_pendencia/<id do vídeo>.<ext> (ou é
    baixado ao abrir); ao salvar, os cortes viram "tempos informados"
    exatos (#exato) e o disco vai pra fila;
  - disco já cortado (uma pasta com os MP3): os MP3 são juntados num arquivo
    só, e ao salvar o disco é recortado e regravado com as mesmas tags; os
    arquivos de antes vão pra .audios_pasta_pendencia/antes_da_edicao/.

Edicao guarda o estado: duração, volume (envelope) pra desenhar, silêncios,
marcas de corte ('silencio' | 'estimado' | 'usuario') e os nomes.
"""
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from audio_util import FFMPEG_PATH, _subprocess_no_window_kwargs, duracao_do_arquivo
from corte_audio import posicao_de_corte_no_silencio
from util import sanitize, segundos_da_faixa

PASTA_AUDIOS = '.audios_pasta_pendencia'
PASTA_ANTES = 'antes_da_edicao'
ENVELOPE_PASSO_SEC = 0.05
ENVELOPE_TAXA = 8000
SILENCIO_MIN_DESENHO_SEC = 0.4        # silêncios mais curtos não aparecem
JANELA_SILENCIO_PERTO_SEC = 15.0      # "levar ao silêncio mais perto"
MARCA_MIN_DISTANCIA_SEC = 2.0         # duas marcas mais perto que isso viram uma
_ID_VIDEO = re.compile(r'(?:v=|youtu\.be/|/shorts/|/live/)([A-Za-z0-9_-]{11})')


# ------------------------------------------------------------------ áudio guardado dos pendentes
def pasta_audios(base) -> Path:
    return Path(base) / PASTA_AUDIOS


def id_do_video(url: str) -> Optional[str]:
    m = _ID_VIDEO.search(url or '')
    return m.group(1) if m else None


def audio_guardado(base, url) -> Optional[Path]:
    """O áudio guardado deste vídeo, se existir."""
    vid = id_do_video(url)
    pasta = pasta_audios(base)
    if not vid or not pasta.exists():
        return None
    achados = [p for p in pasta.glob(f"{vid}.*") if p.is_file() and not p.name.endswith('.part')]
    return achados[0] if achados else None


def guardar_audio(base, url, arquivo) -> Optional[Path]:
    """Copia o áudio baixado pra pasta dos pendentes (pra Editar sem baixar de novo)."""
    vid = id_do_video(url)
    if not vid or not arquivo or not Path(arquivo).exists():
        return None
    pasta = pasta_audios(base)
    pasta.mkdir(parents=True, exist_ok=True)
    for velho in pasta.glob(f"{vid}.*"):
        try:
            velho.unlink()
        except OSError:
            pass
    destino = pasta / f"{vid}{Path(arquivo).suffix or '.m4a'}"
    shutil.copy2(arquivo, destino)
    try:
        (pasta / PASTA_MEDIDAS / f"{vid}.npz").unlink(missing_ok=True)     # medidas do áudio de antes
    except OSError:
        pass
    return destino


def esquecer_audio(base, url) -> bool:
    m = arquivo_de_medidas(base, url)
    if m is not None:
        try:
            m.unlink(missing_ok=True)
        except OSError:
            pass
    a = audio_guardado(base, url)
    if a:
        try:
            a.unlink()
            return True
        except OSError:
            return False
    return False


def limpar_audios(base, urls_ativas) -> int:
    """Apaga os áudios guardados de vídeos que não estão mais em "Precisam de você"."""
    pasta = pasta_audios(base)
    if not pasta.exists():
        return 0
    ativos = {id_do_video(u) for u in urls_ativas or []} - {None}
    n = 0
    for p in pasta.iterdir():
        # só os <id do vídeo>.<ext>; os de trabalho começam com "_" (_editando_..., _baixando_...)
        if (p.is_file() and not p.name.startswith('_') and re.fullmatch(r'[A-Za-z0-9_-]{11}', p.stem)
                and p.stem not in ativos):
            try:
                p.unlink()
                n += 1
            except OSError:
                pass
    medidas = pasta / PASTA_MEDIDAS
    if medidas.is_dir():
        for p in medidas.glob('*.npz'):
            if p.stem not in ativos:
                try:
                    p.unlink()
                except OSError:
                    pass
    return n


def limpar_sobras(base, em_uso=()) -> int:
    """Apaga o que ficou de trabalhos interrompidos (_editando_, _novos_, _baixando_), menos os `em_uso`."""
    pasta = pasta_audios(base)
    if not pasta.exists():
        return 0
    usados = {Path(u).name for u in em_uso or ()}
    n = 0
    for p in pasta.iterdir():
        if p.name.startswith(('_editando_', '_novos_', '_baixando')) and p.name not in usados:
            try:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                n += 1
            except OSError:
                pass
    return n


def nome_unico(prefixo) -> str:
    """Um nome de trabalho que não colide com outro aberto ao mesmo tempo."""
    return f"{prefixo}{time.strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:6]}"


# ------------------------------------------------------------------ medidas pra desenhar
SOM_QUADRO_SEC = 0.5                  # um vetor de "cor do som" a cada meio segundo
SOM_JANELA_SEC = 8.0                  # compara os 8 s antes com os 8 s depois
SOM_DISTANCIA_MIN_SEC = 30.0          # duas sugestões nunca mais perto que isso
SOM_LIMIAR = 4.0                      # quantas vezes acima do normal do disco (mediana/desvio)
SOM_MUDANCA_MIN = 6.0                 # e uma mudança de verdade: ~0,6 desvio em cada faixa de frequência


def medir_audio(arquivo):
    """
    Lê o áudio uma vez (8 kHz mono, aos pedaços - um vídeo de 3 horas não precisa caber na memória) e
    devolve (envelope, sugestões):
      - envelope: volume (RMS, 0..1) a cada ENVELOPE_PASSO_SEC, pra desenhar;
      - sugestões: segundos onde a "cor" do som muda de repente (outro instrumento, outro andamento,
        outra música emendada sem pausa). É só sugestão pro editor; o corte automático não usa.
    """
    import numpy as np
    passo = int(ENVELOPE_TAXA * ENVELOPE_PASSO_SEC)
    quadro = int(ENVELOPE_TAXA * SOM_QUADRO_SEC)
    bloco = quadro * 2 * 200                      # 100 s por leitura (múltiplo dos dois passos)
    proc = subprocess.Popen([FFMPEG_PATH, '-v', 'error', '-i', str(arquivo), '-ac', '1', '-ar', str(ENVELOPE_TAXA),
                             '-f', 's16le', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            **_subprocess_no_window_kwargs())
    janela = np.hanning(quadro).astype(np.float32)
    freqs = np.fft.rfftfreq(quadro, 1.0 / ENVELOPE_TAXA)
    bordas = np.geomspace(60, ENVELOPE_TAXA / 2 - 1, 17)
    faixas = [(freqs >= a) & (freqs < b) for a, b in zip(bordas, bordas[1:])]
    partes_env, partes_som, resto = [], [], b''
    try:
        while True:
            dados = proc.stdout.read(bloco)
            if not dados:
                break
            dados = resto + dados
            n = len(dados) // (quadro * 2)
            resto = dados[n * quadro * 2:]
            if not n:
                continue
            x = np.frombuffer(dados[:n * quadro * 2], dtype=np.int16).astype(np.float32)
            v = x.reshape(-1, passo)
            partes_env.append(np.sqrt(np.mean(v * v, axis=1)))
            q = x.reshape(n, quadro) * janela
            esp = np.abs(np.fft.rfft(q, axis=1)) ** 2
            partes_som.append(np.stack([np.log10(esp[:, f].sum(axis=1) + 1.0) for f in faixas], axis=1))
        if resto:
            x = np.frombuffer(resto[:len(resto) // (passo * 2) * passo * 2], dtype=np.int16).astype(np.float32)
            if len(x):
                v = x.reshape(-1, passo)
                partes_env.append(np.sqrt(np.mean(v * v, axis=1)))
    finally:
        proc.stdout.close()
        proc.wait()
    if not partes_env:
        return np.zeros(0, dtype=np.float32), []
    rms = np.concatenate(partes_env)
    topo = float(np.percentile(rms, 99)) or 1.0
    env = np.minimum(1.0, rms / topo).astype(np.float32)
    return env, (mudancas_no_som(np.concatenate(partes_som), rms) if partes_som else [])


def mudancas_no_som(bandas, rms=None) -> List[float]:
    """
    Onde a "cor" do som muda de repente: para cada instante, a diferença entre o som médio dos 8 s
    antes e dos 8 s depois (só a forma do espectro, não o volume - uma parte mais alta da mesma
    música não conta). Picos bem acima do normal DESTE disco viram sugestões.
    """
    import numpy as np
    F = np.asarray(bandas, dtype=np.float64)
    if len(F) < 4 * SOM_JANELA_SEC / SOM_QUADRO_SEC:
        return []
    quieto = F.max(axis=1) < np.percentile(F.max(axis=1), 5) + 0.3     # trechos de silêncio
    F = F - F.mean(axis=1, keepdims=True)                              # só a forma, sem o volume
    F = (F - F.mean(axis=0)) / (F.std(axis=0) + 1e-6)
    w = int(SOM_JANELA_SEC / SOM_QUADRO_SEC)
    c = np.vstack([np.zeros((1, F.shape[1])), np.cumsum(F, axis=0)])
    T = len(F)
    nov = np.zeros(T)
    idx = np.arange(w, T - w)
    antes = (c[idx] - c[idx - w]) / w
    depois = (c[idx + w] - c[idx]) / w
    nov[idx] = ((antes - depois) ** 2).sum(axis=1)
    nov[quieto] = 0.0
    base = nov[w:T - w]
    if not len(base):
        return []
    med = float(np.median(base))
    desvio = float(np.median(np.abs(base - med))) * 1.4826 or 1e-6
    z = (nov - med) / desvio
    minimo = int(SOM_DISTANCIA_MIN_SEC / SOM_QUADRO_SEC)
    picos = []
    for t in np.argsort(-z):
        if z[t] < SOM_LIMIAR or nov[t] < SOM_MUDANCA_MIN:
            break
        if all(abs(t - p) >= minimo for p in picos):
            picos.append(int(t))
    return sorted(round(t * SOM_QUADRO_SEC, 1) for t in picos)


def envelope_do_audio(arquivo):
    """Só o volume (ver medir_audio)."""
    return medir_audio(arquivo)[0]


# ------------------------------------------------------------------ medidas guardadas (abrir de novo é rápido)
PASTA_MEDIDAS = '_medidas'


def arquivo_de_medidas(base, url) -> Optional[Path]:
    vid = id_do_video(url)
    return pasta_audios(base) / PASTA_MEDIDAS / f"{vid}.npz" if vid else None


def _assinatura(arquivo) -> str:
    st = os.stat(arquivo)
    return f"{st.st_size}:{int(st.st_mtime)}"


def ler_medidas(destino, arquivo) -> Dict:
    """As medidas guardadas deste áudio ({} se não há, ou se o áudio mudou)."""
    import json
    import numpy as np
    try:
        with np.load(str(destino), allow_pickle=False) as z:
            if str(z['assinatura']) != _assinatura(arquivo):
                return {}
            r = {'gaps': json.loads(str(z['gaps'])) if 'gaps' in z.files else None}
            if 'envelope' in z.files and len(z['envelope']):
                r['envelope'] = z['envelope'].astype(np.float32)
                r['sugestoes'] = [float(x) for x in z['sugestoes']] if 'sugestoes' in z.files else []
            return r
    except Exception:
        return {}


def gravar_medidas(destino, arquivo, envelope=None, sugestoes=None, gaps=None) -> bool:
    """Guarda as medidas (o que não vier, fica o que já estava guardado)."""
    import json
    import numpy as np
    try:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        velho = ler_medidas(destino, arquivo) if destino.exists() else {}
        env = envelope if envelope is not None else velho.get('envelope')
        dados = {'assinatura': np.array(_assinatura(arquivo))}
        g = gaps if gaps is not None else velho.get('gaps')
        if g is not None:
            dados['gaps'] = np.array(json.dumps(g, default=float))
        if env is not None:
            dados['envelope'] = np.asarray(env, dtype=np.float32)
            dados['sugestoes'] = np.asarray(sugestoes if sugestoes is not None else velho.get('sugestoes') or [],
                                            dtype=np.float64)
        tmp_ = destino.with_name(destino.stem + '.tmp.npz')
        np.savez_compressed(str(tmp_), **dados)
        os.replace(tmp_, destino)
        return True
    except Exception:
        return False


def silencios_dos_gaps(clusters) -> List[tuple]:
    """Clusters de silêncio (corte_audio.cluster_gaps) -> [(início, fim, votos)] pra desenhar."""
    saida = []
    for c in clusters:
        ini = min(g.get('start', g['position']) for g in c.get('gaps') or [c])
        fim = max(g.get('end', g['position']) for g in c.get('gaps') or [c])
        if fim - ini >= SILENCIO_MIN_DESENHO_SEC:
            saida.append((float(ini), float(fim), int(c.get('votes', 1))))
    return sorted(saida)


# ------------------------------------------------------------------ o estado da edição
class Edicao:
    """
    oficiais: faixas do Discogs [{'title', 'duration'(s ou 'M:SS')}] (pode ser vazio);
    nomes_fixos: nomes atuais (disco já cortado, um por arquivo).

    Os nomes acompanham os cortes: cada marca sabe qual faixa começa nela
    ('faixas'). Apagar um corte junta as faixas ("A / B"); um corte novo no
    meio de uma faixa dá "A (2)". Assim o nome não se perde quando o número
    de pedaços muda.
    """

    def __init__(self, arquivo, oficiais=None, titulo='', nomes_fixos=None, origem='pendencia', duracoes_fixas=None):
        self.arquivo = str(arquivo)
        self.titulo = titulo
        self.origem = origem
        self.oficiais = [{'title': (t.get('title') or '').strip() or f'Track {i + 1}',
                          'duracao': segundos_da_faixa(t)} for i, t in enumerate(oficiais or [])]
        self.nomes_fixos = list(nomes_fixos or [])
        # disco já cortado: onde começava cada faixa de antes (capa/artista de cada pedaço)
        self.inicios_fixos = []
        if duracoes_fixas and len(duracoes_fixas) == len(self.nomes_fixos):
            acc = 0.0
            for d in duracoes_fixas:
                self.inicios_fixos.append(acc)
                acc += float(d)
        self.duracao = 0.0
        self.envelope = None
        self.silencios: List[tuple] = []
        self.sugestoes_som: List[float] = []   # possíveis trocas de música sem pausa (mudança no som)
        self.marcas: List[Dict] = []           # {'pos', 'tipo': 'silencio'|'estimado'|'usuario', 'faixas': [k]}
        self.nomes_base: Optional[List[str]] = None
        self.faixas_inicio: Optional[List[int]] = None
        self.nomes_editados: Dict[int, str] = {}
        self._nomes_guardados: Dict[tuple, str] = {}  # nome editado de um pedaço que foi juntado a outro
        self.candidatos: Dict[str, List[str]] = {}    # fonte -> nomes (sugestões no duplo clique)
        self.sugestao_inicial = None
        self.mudou = False

    # --- carga
    def carregar(self, marcas=None, log=None, medidas=None):
        """Mede o áudio (duração, volume, silêncios, mudanças no som) e acha as marcas iniciais (ou usa
        `marcas`). `medidas`: arquivo .npz pra guardar/reaproveitar as medidas (abrir de novo é rápido)."""
        from corte_album import AlbumCutter
        from corte_estrategias import SmartCutter
        quieto = log or (lambda *a, **k: None)
        self.duracao = float(duracao_do_arquivo(self.arquivo) or 0.0)
        guardado = ler_medidas(medidas, self.arquivo) if medidas else {}
        if guardado.get('envelope') is not None:
            self.envelope, self.sugestoes_som = guardado['envelope'], list(guardado.get('sugestoes') or [])
        else:
            self.envelope, self.sugestoes_som = medir_audio(self.arquivo)
        meta = {'tracks': [{'title': o['title'], 'duration': o['duracao']} for o in self.oficiais], 'title': self.titulo}
        ac = AlbumCutter('', self.titulo, self.arquivo, meta, str(Path(self.arquivo).parent), log_func=quieto)
        gaps = guardado.get('gaps') or ac.detect_gaps()
        if medidas:
            gravar_medidas(medidas, self.arquivo, envelope=self.envelope, sugestoes=self.sugestoes_som, gaps=gaps)
        sc = SmartCutter(meta, gaps, self.arquivo, log_func=quieto)
        clusters = sc.cluster_gaps(tolerance=5.0)
        self.silencios = silencios_dos_gaps(clusters)
        if marcas is not None:
            self.marcas = [dict(m) for m in marcas]
        else:
            self.marcas = self._marcas_iniciais(ac, gaps, sc, clusters)
        self.marcas.sort(key=lambda m: m['pos'])
        # mudança no som perto de um silêncio ou de um corte já marcado não é sugestão nova
        self.sugestoes_som = [p for p in self.sugestoes_som
                              if not any(a - 4 <= p <= b + 4 for a, b, _ in self.silencios)
                              and not any(abs(m['pos'] - p) < 6 for m in self.marcas)]
        self.rotular()
        return self

    def rotular(self):
        """Dá a cada marca a faixa que começa nela (quando se sabe os nomes de todos os pedaços) e
        guarda a sugestão inicial (pro arquivo de correções)."""
        self.nomes_base, self.faixas_inicio = None, None
        for m in self.marcas:
            m.pop('faixas', None)
        self._ligar_identidade()
        self.sugestao_inicial = {'marcas': [{'pos': round(m['pos'], 3), 'tipo': m['tipo']} for m in self.marcas],
                                 'nomes': self.nomes()}
        return self

    def _ligar_identidade(self) -> bool:
        """Os nomes passam a acompanhar os cortes assim que o nº de pedaços bate com o Discogs (ou com
        os arquivos de antes) - na abertura ou depois, quando você marca o corte que faltava."""
        if self._identidade():
            return True
        n = len(self.marcas) + 1
        if self.oficiais and len(self.oficiais) == n:
            self.nomes_base = [o['title'] for o in self.oficiais]
        elif self.nomes_fixos and len(self.nomes_fixos) == n:
            self.nomes_base = list(self.nomes_fixos)
        else:
            return False
        self.faixas_inicio = [0]
        for k, m in enumerate(self.marcas):
            m['faixas'] = [k + 1]
        return True

    def _marcas_iniciais(self, ac, gaps, sc, clusters):
        """As marcas que o próprio programa faria ("processar mesmo assim"); senão, pelas durações."""
        try:
            if ac.smart_cut(gaps, allow_cross_validation=True) and ac.cuts:
                marcas = []
                for c in ac.cuts[:-1]:
                    if c.get('end') is None:
                        continue
                    # o MÉTODO diz como ESTA fronteira (o fim do pedaço) foi achada; 'corte_estimado'
                    # marca as duas faixas vizinhas, não serve aqui
                    estimada = str(c.get('method', '')).startswith('math_fallback')
                    forte = c.get('gap_found') and (c.get('votos') is None or c.get('votos', 0) >= 2)
                    tipo = 'estimado' if estimada or not forte else 'silencio'
                    marcas.append({'pos': float(c['end']), 'tipo': tipo})
                return marcas
        except Exception:
            pass
        return self._marcas_pelas_duracoes(clusters)

    def _marcas_pelas_duracoes(self, clusters):
        marcas = []
        guias = self.guias_discogs()
        if guias:
            for acc in guias:
                perto = [c for c in clusters if c.get('votes', 1) >= 2 and abs(c['position'] - acc) <= 10.0]
                if perto:
                    c = min(perto, key=lambda c: abs(c['position'] - acc))
                    marcas.append({'pos': float(c['position']), 'tipo': 'silencio'})
                else:
                    marcas.append({'pos': acc, 'tipo': 'estimado'})
            return marcas
        return [{'pos': float(c['position']), 'tipo': 'silencio'} for c in clusters
                if c.get('votes', 1) >= 2 and 30 < c['position'] < self.duracao - 15]

    def marcas_dos_tempos(self, inicios, janela=3.0):
        """Marcas a partir de tempos de início (capítulos, comentário): no silêncio se houver um perto,
        senão 'estimado' no tempo escrito."""
        marcas = []
        for t in sorted(float(x) for x in inicios if 1.0 < float(x) < self.duracao - 1.0):
            perto = [(a, b) for a, b, _ in self.silencios if a - janela <= t <= b + janela]
            m = {'pos': t, 'tipo': 'estimado'}
            if perto:
                a, b = min(perto, key=lambda s: abs((s[0] + s[1]) / 2 - t))
                m = {'pos': posicao_de_corte_no_silencio(a, b), 'tipo': 'silencio'}
            anterior = marcas[-1]['pos'] if marcas else 0.0
            if m['pos'] - anterior < MARCA_MIN_DISTANCIA_SEC:
                # dois tempos na mesma pausa: o segundo fica no tempo escrito (ou some, se colado no anterior)
                m = {'pos': t, 'tipo': 'estimado'}
                if t - anterior < MARCA_MIN_DISTANCIA_SEC:
                    continue
            marcas.append(m)
        return marcas

    # --- leitura
    def pecas(self) -> List[tuple]:
        lim = [0.0] + [m['pos'] for m in self.marcas] + [self.duracao]
        return list(zip(lim, lim[1:]))

    def guias_discogs(self) -> List[float]:
        """Onde o Discogs poria cada corte, somando as durações (ajustadas à duração do áudio se a soma
        estiver perto dela). Vazio sem durações."""
        durs = [o['duracao'] for o in self.oficiais]
        if len(durs) < 2 or not all(d > 0 for d in durs) or self.duracao <= 0:
            return []
        razao = self.duracao / sum(durs)
        escala = razao if 0.85 < razao < 1.15 else 1.0
        guias, acc = [], 0.0
        for d in durs[:-1]:
            acc += d * escala
            if acc < self.duracao:
                guias.append(acc)
        return guias

    def _identidade(self) -> bool:
        return self.nomes_base is not None and self.faixas_inicio is not None and \
            all('faixas' in m for m in self.marcas)

    def faixas_da_peca(self, i) -> Optional[List[int]]:
        """Quais faixas (dos nomes de base) estão no pedaço i: [k], [k, k+1] (juntas) ou [] (pedaço novo)."""
        if not self._identidade():
            return None
        return list(self.faixas_inicio if i == 0 else self.marcas[i - 1]['faixas'])

    def faixa_de_antes(self, t) -> int:
        """Índice da faixa de antes (disco já cortado) que contém o segundo t."""
        k = 0
        for i, ini in enumerate(self.inicios_fixos):
            if ini <= t:
                k = i
        return k

    def _nomes_por_identidade(self) -> List[str]:
        """fx = [k, ...]: as faixas que começam no pedaço; vazio ou -1 = continuação da faixa anterior
        ("A (2)"; "A (2) / B" quando o resto de A foi juntado com B)."""
        nomes, ultima, parte = [], None, 1
        for i in range(len(self.marcas) + 1):
            fx = self.faixas_da_peca(i) or [-1]
            partes = []
            for k in fx:
                if k < 0:
                    parte += 1
                    partes.append(f"{self.nomes_base[ultima] if ultima is not None else 'Track 1'} ({parte})")
                else:
                    partes.append(self.nomes_base[k])
                    ultima, parte = k, 1
            nomes.append(' / '.join(partes))
        return nomes

    def nomes(self) -> List[str]:
        n = len(self.marcas) + 1
        if self._identidade():
            base = self._nomes_por_identidade()
        elif self.oficiais and len(self.oficiais) == n:
            base = [o['title'] for o in self.oficiais]
        elif self.nomes_fixos and len(self.nomes_fixos) == n:
            base = list(self.nomes_fixos)
        else:
            base = [f'Track {i + 1}' for i in range(n)]
        return [self.nomes_editados.get(i, base[i]) for i in range(n)]

    def duracoes_oficiais(self) -> List[float]:
        n = len(self.marcas) + 1
        if self._identidade() and self.oficiais and len(self.oficiais) == len(self.nomes_base):
            durs = []
            for i in range(n):
                fx = self.faixas_da_peca(i)
                # pedaço com resto de outra faixa: duração esperada desconhecida
                durs.append(sum(self.oficiais[k]['duracao'] for k in fx) if fx and min(fx) >= 0 else 0.0)
            return durs
        if self.oficiais and len(self.oficiais) == n:
            return [o['duracao'] for o in self.oficiais]
        return [0.0] * n

    def situacao_pecas(self) -> List[str]:
        """Por pedaço: 'ok', 'estimado' (uma das pontas não foi confirmada) ou 'longo' (2 músicas?)."""
        pecas = self.pecas()
        durs = sorted(b - a for a, b in pecas)
        mediana = durs[len(durs) // 2] if durs else 0
        faltam = self.faltam()
        oficiais = self.duracoes_oficiais()
        sit = []
        for i, (a, b) in enumerate(pecas):
            pontas = [self.marcas[k]['tipo'] for k in (i - 1, i) if 0 <= k < len(self.marcas)]
            d, esperado = b - a, oficiais[i]
            longo = (faltam > 0 and mediana > 0 and d > 1.6 * mediana and d > mediana + 60) or \
                    (esperado > 0 and d > esperado * 1.5 and d > esperado + 45)
            sit.append('longo' if longo else ('estimado' if 'estimado' in pontas else 'ok'))
        return sit

    def faltam(self) -> int:
        """Quantos cortes faltam pro nº de músicas do Discogs (0 sem Discogs ou se sobram)."""
        return max(0, len(self.oficiais) - (len(self.marcas) + 1)) if self.oficiais else 0

    def sobram(self) -> int:
        return max(0, (len(self.marcas) + 1) - len(self.oficiais)) if self.oficiais else 0

    def estimadas(self) -> List[int]:
        return [i for i, m in enumerate(self.marcas) if m['tipo'] == 'estimado']

    def sugestoes_dentro(self, i) -> List[float]:
        a, b = self.pecas()[i]
        return [p for p in self.sugestoes_som if a + 20 < p < b - 20]

    # --- nomes candidatos
    def adicionar_candidatos(self, fonte, nomes):
        nomes = [' '.join(str(n).split()) for n in nomes or [] if str(n or '').strip()]
        if nomes:
            self.candidatos[fonte] = nomes

    def candidatos_da_faixa(self, i) -> List[tuple]:
        """[(fonte, nome)] pra faixa i: primeiro os de cada fonte na mesma posição, depois os outros."""
        n = len(self.marcas) + 1
        fx = self.faixas_da_peca(i)
        primeiro, resto, vistos = [], [], set()
        for fonte, lista in self.candidatos.items():
            if fx and min(fx) >= 0 and self.nomes_base and len(lista) == len(self.nomes_base):
                idx = fx
            elif len(lista) == n:
                idx = [i]
            else:
                idx = []
            if idx:
                nome = ' / '.join(lista[k] for k in idx if k < len(lista))
                if nome and nome.lower() not in vistos:
                    primeiro.append((fonte, nome))
                    vistos.add(nome.lower())
        for fonte, lista in self.candidatos.items():
            for nome in lista:
                if nome.lower() not in vistos:
                    resto.append((fonte, nome))
                    vistos.add(nome.lower())
        return primeiro + resto

    def colar_nomes(self, texto) -> int:
        """Uma lista de nomes (um por linha, com ou sem número e tempo) vira os nomes das faixas, em
        ordem. Devolve quantos nomes foram usados."""
        nomes = nomes_de_lista(texto)
        n = len(self.marcas) + 1
        for i, nome in enumerate(nomes[:n]):
            self.renomear(i, nome)
        if nomes:
            self.adicionar_candidatos('colados', nomes)
        return min(len(nomes), n)

    # --- edição
    def marca_mais_perto(self, pos, ate=None) -> Optional[int]:
        if not self.marcas:
            return None
        i = min(range(len(self.marcas)), key=lambda k: abs(self.marcas[k]['pos'] - pos))
        if ate is not None and abs(self.marcas[i]['pos'] - pos) > ate:
            return None
        return i

    def marcar(self, pos) -> int:
        """Marca um corte em `pos` (ou move a marca que já estiver a menos de 2s). Devolve o índice."""
        pos = min(max(1.0, float(pos)), self.duracao - 1.0)
        i = self.marca_mais_perto(pos, MARCA_MIN_DISTANCIA_SEC)
        if i is not None:
            self.marcas[i].update(pos=pos, tipo='usuario')
        else:
            self._ligar_identidade()
            nova = {'pos': pos, 'tipo': 'usuario'}
            if self._identidade():
                nova['faixas'] = self._dividir_faixas(pos)
            self.marcas.append(nova)
            self.marcas.sort(key=lambda m: m['pos'])
            i = next(k for k, m in enumerate(self.marcas) if m is nova)
            # o pedaço i virou dois: os nomes editados dos pedaços depois dele andam uma casa
            self.nomes_editados = {(k + 1 if k > i else k): v for k, v in self.nomes_editados.items()}
            guardado = self._nomes_guardados.pop(tuple(nova.get('faixas') or ()), None)
            if guardado and nova.get('faixas'):
                self.nomes_editados[i + 1] = guardado      # você tinha dado esse nome antes de juntar
        self.mudou = True
        return i

    def _dividir_faixas(self, pos) -> List[int]:
        """Corte novo em `pos`: se o pedaço tinha várias faixas juntas ("A / B"), as que (pelas durações
        do Discogs, ou só a 1ª, sem durações) ficam depois do corte passam pro pedaço novo; senão o pedaço
        novo é parte da mesma faixa ("A (2)")."""
        k = sum(1 for m in self.marcas if m['pos'] < pos)
        fx = self.faixas_inicio if k == 0 else self.marcas[k - 1]['faixas']
        if len(fx) < 2:
            return []
        inicio = 0.0 if k == 0 else self.marcas[k - 1]['pos']
        esquerda = 1
        if self.oficiais and len(self.oficiais) == len(self.nomes_base or []) and min(fx) >= 0 and \
                all(self.oficiais[f]['duracao'] > 0 for f in fx):
            acc, esquerda = inicio, 0
            for f in fx:
                if acc >= pos - 1.0:
                    break
                esquerda += 1
                acc += self.oficiais[f]['duracao']
            esquerda = min(max(1, esquerda), len(fx) - 1)
        direita = fx[esquerda:]
        del fx[esquerda:]
        return direita

    def mover(self, i, pos) -> float:
        """Move a marca i (sem passar das vizinhas). Devolve a posição final."""
        ant = self.marcas[i - 1]['pos'] + 1.0 if i > 0 else 1.0
        prox = self.marcas[i + 1]['pos'] - 1.0 if i + 1 < len(self.marcas) else self.duracao - 1.0
        self.marcas[i].update(pos=min(max(ant, float(pos)), prox), tipo='usuario')
        self.mudou = True
        return self.marcas[i]['pos']

    def apagar(self, i):
        self._ligar_identidade()
        m = self.marcas.pop(i)
        if self._identidade() or (self.faixas_inicio is not None and 'faixas' in m):
            # as faixas que começavam nesse corte passam pro pedaço da esquerda ("A / B")
            destino = self.faixas_inicio if i == 0 else self.marcas[i - 1].setdefault('faixas', [])
            if not destino and m.get('faixas'):
                destino.append(-1)                         # o pedaço da esquerda era resto de outra faixa
            destino.extend(m.get('faixas') or [])
            if m.get('faixas') and (i + 1) in self.nomes_editados:
                self._nomes_guardados[tuple(m['faixas'])] = self.nomes_editados[i + 1]
        # os pedaços i e i+1 viraram um (fica o nome editado do i, se houver); os de depois voltam uma casa
        self.nomes_editados = {(k - 1 if k > i + 1 else k): v for k, v in self.nomes_editados.items() if k != i + 1}
        self.mudou = True

    def silencio_mais_perto(self, pos) -> Optional[float]:
        """Ponto de corte do silêncio mais perto de `pos` (a até 15s), ou None."""
        perto = [(a, b) for a, b, _ in self.silencios
                 if min(abs(a - pos), abs(b - pos)) <= JANELA_SILENCIO_PERTO_SEC or a <= pos <= b]
        if not perto:
            return None
        a, b = min(perto, key=lambda s: 0 if s[0] <= pos <= s[1] else min(abs(s[0] - pos), abs(s[1] - pos)))
        return posicao_de_corte_no_silencio(a, b)

    def renomear(self, i, nome):
        nome = (nome or '').strip()
        if nome:
            self.nomes_editados[i] = nome
            self.mudou = True

    # --- saída
    def texto_tempos(self) -> str:
        """Os cortes como "tempos informados" EXATOS (o corte não procura pausa perto)."""
        linhas = ['#exato']
        for (a, _), nome in zip(self.pecas(), self.nomes()):
            ms = int(round(a * 1000))                  # em milissegundos inteiros: nunca sai "2:60.000"
            h, ms = divmod(ms, 3_600_000)
            mi, ms = divmod(ms, 60_000)
            se, ms = divmod(ms, 1000)
            linhas.append(f"{h}:{mi:02d}:{se:02d}.{ms:03d} {' '.join(nome.split())}")
        return '\n'.join(linhas)


_LIMPA_LINHA = re.compile(r'^\s*(?:\(?\d{1,3}[.)\-–—:]?\s+|[A-D]\d{1,2}[.)\-–—]?\s+|[-–—•*]\s*)')


def nomes_de_lista(texto) -> List[str]:
    """Nomes de uma lista colada: um por linha, sem número ("01 -", "1.", "A1"), sem tempo ("3:12")
    e sem linhas vazias. O número da frente só sai quando a lista é numerada (a maioria das linhas
    começa com número) - "99 Luftballons" numa lista sem números fica como está."""
    from catalogo import _TEMPO
    linhas = []
    for linha in (texto or '').splitlines():
        l = re.sub(r'\(\s*\)|\[\s*\]', ' ', _TEMPO.sub(' ', linha))     # "Nome (3:12)" -> "Nome"
        l = re.sub(r'^[\s\-–—|:.,\]]+|[\s\-–—|:.,(\[]+$', '', l)
        if l.strip():
            linhas.append(l)
    numerada = sum(1 for l in linhas if _LIMPA_LINHA.match(l)) > len(linhas) / 2
    nomes = []
    for l in linhas:
        if numerada:
            l = _LIMPA_LINHA.sub('', l)
        l = ' '.join(l.split()).strip(' -–—|')
        if l and not re.fullmatch(r'(?i)(total|side [a-d]|lado [a-d]|tracklist|faixas)\W*', l):
            nomes.append(l)
    return nomes


_LINHA_EXATA = re.compile(r'^(\d+):(\d{2}):(\d{2})\.(\d{3})(?: (.*))?$')


def ler_tempos_exatos(texto) -> Optional[List[Dict]]:
    """
    O texto de texto_tempos() de volta: [{'start_time', 'title'}]. Leitor próprio,
    sem os filtros da lista colada à mão (lá "Side by Side" ou "Total Eclipse"
    seriam linhas a pular, e "5:15" no nome seria lido como tempo). None se não for #exato.
    """
    linhas = [l.strip() for l in (texto or '').strip().splitlines() if l.strip()]
    if not linhas or not linhas[0].startswith('#exato'):
        return None
    lista = []
    for l in linhas[1:]:
        m = _LINHA_EXATA.match(l)
        if not m:
            return None
        h, mi, se, ms, nome = m.groups()
        lista.append({'start_time': int(h) * 3600 + int(mi) * 60 + int(se) + int(ms) / 1000.0,
                      'title': (nome or '').strip()})
    if not lista or any(b['start_time'] <= a['start_time'] for a, b in zip(lista, lista[1:])):
        return None
    return lista


# ------------------------------------------------------------------ disco já cortado (pasta com MP3)
def mp3s_da_pasta(pasta) -> List[Path]:
    return sorted(p for p in Path(pasta).glob('*.mp3') if p.is_file())


def ler_pasta(pasta) -> Dict:
    """Faixas da pasta, em ordem: arquivos, nomes, durações, artista e capa de cada uma e as tags do
    álbum (do 1º arquivo)."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import ID3
    arquivos = mp3s_da_pasta(pasta)
    if not arquivos:
        raise ValueError("a pasta não tem arquivos MP3")
    nomes, duracoes, artistas, capas = [], [], [], []
    for p in arquivos:
        try:
            tags = ID3(str(p))
        except Exception:
            tags = None
        tit = str(tags.get('TIT2') or '').strip() if tags is not None else ''
        nomes.append(tit or re.sub(r'^\d+\s*-\s*', '', p.stem))
        artistas.append(str(tags.get('TPE1') or '').strip() if tags is not None else '')
        apic = tags.getall('APIC') if tags is not None else []
        capas.append(apic[0].data if apic else None)
        duracoes.append(float(MP3(str(p)).info.length))
    album = {}
    try:
        t0 = ID3(str(arquivos[0]))
        for chave in ('TPE1', 'TALB', 'TPE2', 'TCON', 'TDRC', 'TYER'):
            if t0.get(chave):
                album[chave] = str(t0.get(chave))
        for frame in t0.getall('TXXX'):
            if frame.desc in ('DISCOGS_MASTER_ID', 'DISCOGS_RELEASE_ID'):
                album[frame.desc] = str(frame.text[0])
    except Exception:
        pass
    album['capa'] = capas[0]
    try:
        kbps = int(MP3(str(arquivos[0])).info.bitrate // 1000)
    except Exception:
        kbps = 160
    return {'arquivos': arquivos, 'nomes': nomes, 'duracoes': duracoes, 'artistas': artistas, 'capas': capas,
            'album': album, 'kbps': max(96, kbps)}


def juntar_pasta(pasta, destino) -> Path:
    """Os MP3 da pasta num arquivo só (sem recodificar), pra ouvir e editar."""
    arquivos = mp3s_da_pasta(pasta)
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    lista = destino.with_suffix('.txt')
    lista.write_text(''.join("file '" + str(p.resolve()).replace("'", "'\\''") + "'\n" for p in arquivos),
                     encoding='utf-8')
    r = subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(lista),
                        '-map', '0:a', '-c', 'copy', str(destino)], capture_output=True,
                       **_subprocess_no_window_kwargs())
    lista.unlink(missing_ok=True)
    if r.returncode != 0 or not destino.exists():
        raise RuntimeError(f"não consegui juntar os MP3 ({r.stderr.decode(errors='replace')[-120:]})")
    return destino


def _pode_mexer(p: Path) -> bool:
    """O arquivo pode ser movido agora? (no Windows, aberto num tocador não pode)"""
    try:
        os.replace(p, p)
        with open(p, 'r+b'):
            pass
        return True
    except OSError:
        return False


def regravar_pasta(pasta, base, edicao: Edicao, info: Dict, log=print) -> Dict:
    """
    Recorta o disco juntado nos cortes da edição e põe os novos MP3 na pasta,
    com as tags de antes, os nomes da tabela e a numeração nova. Os arquivos
    de antes vão pra .audios_pasta_pendencia/antes_da_edicao/<pasta> <data>/.
    Nada da pasta é mexido até todos os novos estarem prontos e com as tags; se
    a troca falhar no meio, o que já tinha saído volta pro lugar.
    """
    from metadata_manager import MetadataManager, gravar_tags
    pasta = Path(pasta)
    presos = [p.name for p in info['arquivos'] if not _pode_mexer(p)]
    if presos:
        raise RuntimeError(f"{len(presos)} arquivo(s) da pasta estão abertos em outro programa "
                           f"({', '.join(presos[:3])}). Feche o tocador e salve de novo")
    trabalho = pasta_audios(base) / nome_unico('_novos_')
    trabalho.mkdir(parents=True, exist_ok=True)
    try:
        album = info['album']
        capas_arq = {}

        def capa_da(k):
            """A capa da faixa de antes k (cada faixa pode ter a sua, como nas playlists)."""
            capas = info.get('capas') or []
            dados = (capas[k] if k < len(capas) else None) or album.get('capa')
            if not dados:
                return pasta / 'cover.jpg' if (pasta / 'cover.jpg').exists() else None
            chave = hash(dados)
            if chave not in capas_arq:
                capas_arq[chave] = trabalho / f'capa_{len(capas_arq)}.jpg'
                capas_arq[chave].write_bytes(dados)
            return capas_arq[chave]

        novos = []
        pecas, nomes = edicao.pecas(), edicao.nomes()
        for n, ((a, b), nome) in enumerate(zip(pecas, nomes), start=1):
            arq = trabalho / f"{n:02d} - {sanitize(nome)}.mp3"
            r = subprocess.run([FFMPEG_PATH, '-v', 'error', '-y', '-ss', f'{a:.3f}', '-to', f'{b:.3f}',
                                '-i', edicao.arquivo, '-map', '0:a', '-map_metadata', '-1', '-c:a', 'libmp3lame',
                                '-b:a', f"{info['kbps']}k", str(arq)], capture_output=True,
                               **_subprocess_no_window_kwargs())
            if r.returncode != 0 or not arq.exists():
                raise RuntimeError(f"o corte da faixa {n} falhou ({r.stderr.decode(errors='replace')[-120:]})")
            k = edicao.faixa_de_antes(a + 0.5) if edicao.inicios_fixos else 0
            artistas = info.get('artistas') or []
            artista = (artistas[k] if k < len(artistas) else '') or album.get('TPE1', '')
            if not gravar_tags(str(arq), nome, artista, album.get('TALB', ''), n, len(pecas),
                               ano=album.get('TDRC') or album.get('TYER', ''), artista_album=album.get('TPE2', ''),
                               genero=album.get('TCON', ''), capa=capa_da(k)):
                raise RuntimeError(f"não consegui gravar as tags da faixa {n}")
            if album.get('DISCOGS_MASTER_ID') or album.get('DISCOGS_RELEASE_ID'):
                MetadataManager().add_discogs_ids(str(arq), master_id=album.get('DISCOGS_MASTER_ID'),
                                                  release_id=album.get('DISCOGS_RELEASE_ID'))
            novos.append(arq)
    except Exception:
        shutil.rmtree(trabalho, ignore_errors=True)          # a pasta do disco não foi tocada
        raise
    guarda = pasta_audios(base) / PASTA_ANTES / f"{pasta.name} {time.strftime('%Y-%m-%d %H-%M-%S')}"
    guarda.mkdir(parents=True, exist_ok=True)
    saidos, entrados = [], []
    try:
        for p in info['arquivos']:
            os.replace(p, guarda / p.name) if _mesmo_disco(p, guarda) else shutil.move(str(p), str(guarda / p.name))
            saidos.append(p)
        for p in novos:
            shutil.move(str(p), str(pasta / p.name))
            entrados.append(pasta / p.name)
    except Exception as e:
        # volta tudo como estava: tira os novos que entraram e devolve os de antes
        for p in entrados:
            try:
                p.unlink()
            except OSError:
                pass
        voltaram = 0
        for p in saidos:
            try:
                shutil.move(str(guarda / p.name), str(p))
                voltaram += 1
            except OSError:
                pass
        shutil.rmtree(trabalho, ignore_errors=True)
        if voltaram == len(saidos):
            raise RuntimeError(f"não consegui trocar os arquivos ({e}); a pasta ficou como estava")
        raise RuntimeError(f"não consegui trocar os arquivos ({e}); os de antes que não voltaram estão em {guarda}")
    shutil.rmtree(trabalho, ignore_errors=True)
    log(f"✂️  Disco reeditado: {len(novos)} faixas em {pasta} (os arquivos de antes estão em {guarda})")
    return {'faixas': len(novos), 'antes': guarda}


def _mesmo_disco(a: Path, pasta: Path) -> bool:
    try:
        return os.stat(a).st_dev == os.stat(pasta).st_dev
    except OSError:
        return False


# ------------------------------------------------------------------ arquivo de correções (pra ajustar o programa)
ARQUIVO_CORRECOES = 'correcoes_do_editor.txt'
MANTIDO_SEC = 0.5                     # corte que ficou a menos disso do sugerido = mantido
PAR_MAX_SEC = 20.0                    # mais longe que isso não é o mesmo corte movido


def caminho_correcoes(base) -> Path:
    return Path(base) / 'logs' / ARQUIVO_CORRECOES


def _mais_perto(lista, p):
    return min((abs(x - p) for x in lista), default=None)


def registro_de_correcoes(ed: Edicao, extra: Optional[Dict] = None) -> Dict:
    """
    O que o programa sugeriu × o que você deixou ao salvar: cortes mantidos, movidos (quanto),
    apagados e novos, o que havia no áudio perto de cada um (pausa, mudança no som, a conta do
    Discogs) e os nomes trocados. Uma linha por disco no arquivo de correções.
    """
    sug = (ed.sugestao_inicial or {}).get('marcas') or []
    fim = [{'pos': round(m['pos'], 3), 'tipo': m['tipo']} for m in ed.marcas]
    pares = sorted(((abs(a['pos'] - b['pos']), i, j) for i, a in enumerate(sug) for j, b in enumerate(fim)
                    if abs(a['pos'] - b['pos']) <= PAR_MAX_SEC))
    usados_s, usados_f, casados = set(), set(), {}
    for _, i, j in pares:
        if i not in usados_s and j not in usados_f:
            usados_s.add(i); usados_f.add(j); casados[i] = j
    meios = [posicao_de_corte_no_silencio(a, b) for a, b, _ in ed.silencios]
    guias = ed.guias_discogs()

    def ambiente(p):
        sil = min(((abs(posicao_de_corte_no_silencio(a, b) - p), b - a) for a, b, _ in ed.silencios), default=None)
        return {'pausa_perto_s': round(sil[0], 2) if sil else None, 'pausa_dura_s': round(sil[1], 2) if sil else None,
                'som_perto_s': _arred(_mais_perto(ed.sugestoes_som, p)), 'discogs_perto_s': _arred(_mais_perto(guias, p))}
    cortes = []
    for i, a in enumerate(sug):
        if i in casados:
            b = fim[casados[i]]
            d = round(b['pos'] - a['pos'], 3)
            cortes.append(dict(acao='mantido' if abs(d) <= MANTIDO_SEC else 'movido', tipo=a['tipo'],
                               sugerido=a['pos'], final=b['pos'], diferenca_s=d, **ambiente(b['pos'])))
        else:
            cortes.append(dict(acao='apagado', tipo=a['tipo'], sugerido=a['pos'], **ambiente(a['pos'])))
    for j, b in enumerate(fim):
        if j not in usados_f:
            cortes.append(dict(acao='novo', final=b['pos'], **ambiente(b['pos'])))
    nomes_sug = (ed.sugestao_inicial or {}).get('nomes') or []
    nomes_fim = ed.nomes()
    trocados = [{'faixa': i + 1, 'sugerido': nomes_sug[i] if i < len(nomes_sug) else None, 'final': n}
                for i, n in enumerate(nomes_fim) if i >= len(nomes_sug) or nomes_sug[i] != n]
    r = {'data': time.strftime('%Y-%m-%d %H:%M:%S'), 'origem': ed.origem, 'disco': ed.titulo,
         'duracao_s': round(ed.duracao, 1), 'faixas_discogs': len(ed.oficiais),
         'durações_discogs': bool(guias), 'pecas_sugeridas': len(sug) + 1, 'pecas_finais': len(fim) + 1,
         'pausas_no_disco': len(ed.silencios), 'mudancas_no_som': len(ed.sugestoes_som),
         'cortes': cortes, 'nomes_trocados': trocados}
    r.update(extra or {})
    return r


def _arred(x):
    return None if x is None else round(x, 2)


def gravar_correcao(base, registro) -> bool:
    """Uma linha (JSON) no fim de <pasta dos discos>/logs/correcoes_do_editor.txt."""
    import json
    try:
        arq = caminho_correcoes(base)
        arq.parent.mkdir(parents=True, exist_ok=True)
        with open(arq, 'a', encoding='utf-8') as f:
            f.write(json.dumps(registro, ensure_ascii=False) + '\n')
        return True
    except OSError:
        return False


def resumo_correcoes(base, ultimas=50) -> Optional[str]:
    """ "Nas últimas N edições, X% dos cortes sugeridos ficaram onde estavam" (None sem registros)."""
    import json
    try:
        linhas = caminho_correcoes(base).read_text(encoding='utf-8').splitlines()[-ultimas:]
    except OSError:
        return None
    regs = []
    for l in linhas:
        try:
            regs.append(json.loads(l))
        except ValueError:
            pass
    sug = [c for r in regs for c in r.get('cortes', []) if c.get('acao') != 'novo']
    if not regs or not sug:
        return None
    mantidos = sum(1 for c in sug if c['acao'] == 'mantido')
    novos = sum(1 for r in regs for c in r.get('cortes', []) if c.get('acao') == 'novo')
    return (f"nas últimas {len(regs)} edições, {round(100 * mantidos / len(sug))}% dos cortes sugeridos ficaram "
            f"onde estavam ({mantidos} de {len(sug)}; {novos} corte(s) novo(s) marcados por você)")

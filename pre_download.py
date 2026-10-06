"""
Baixar o próximo álbum enquanto o atual é cortado.

Só UM à frente, na pasta .temp/proximo da pasta de saída. Regras:
- só disco único (vídeo com o álbum inteiro), não playlist nem pendência;
- os downloads nunca correm ao mesmo tempo: a mesma trava serve o download
  normal e o antecipado (o yt-dlp e o contorno de cookies guardam estado);
- quando a vez do próximo chega, o programa usa o arquivo já baixado; se o
  download antecipado ainda estiver em andamento, espera ele terminar em vez
  de começar outro;
- se o próximo não for baixado de verdade (ficou pra "Precisam de você", já
  estava no acervo, a fila mudou de ordem) o arquivo antecipado é apagado.
"""
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Callable, Optional

TIPOS_ANTECIPAVEIS = ('disco_unico', 'canal')


class PreDownload:
    """Download antecipado de UM item da fila (o próximo), em thread própria."""

    def __init__(self, baixar: Callable, pasta_saida: Callable, log: Callable = None, reg: Callable = None):
        """
        baixar(url, pasta, progresso) -> caminho|None   (o download_audio com trava)
        pasta_saida() -> pasta de saída atual; log/reg: log da tela e registro em arquivo.
        """
        self._baixar = baixar
        self._pasta_saida = pasta_saida
        self._log = log or (lambda *a: None)
        self._reg = reg or (lambda *a: None)
        self._trava = threading.Lock()
        self.atual = None          # {'url','id','titulo','thread','arquivo','pasta','descartar','inicio','fim'}
        self.limpar_sobras()

    # ------------------------------------------------------------------
    def pasta(self) -> Optional[Path]:
        """<saída>/.temp/proximo, ou None sem pasta de saída."""
        saida = self._pasta_saida()
        return (Path(saida) / '.temp' / 'proximo') if saida else None

    def limpar_sobras(self):
        """Arquivo antecipado de uma abertura anterior não serve mais."""
        try:
            p = self.pasta()
            if p and p.exists():
                shutil.rmtree(p, ignore_errors=True)
        except Exception:
            pass

    # ------------------------------------------------------------------
    def iniciar(self, item) -> bool:
        """Começa a baixar o item (o próximo da fila) em segundo plano."""
        if not item or item.get('tipo') not in TIPOS_ANTECIPAVEIS or not item.get('url'):
            return False
        with self._trava:
            if self.atual and self.atual['url'] == item['url'] and not self.atual['descartar']:
                return False                      # já está sendo (ou foi) baixado
        self.descartar('a fila mudou: o próximo agora é outro')
        base = self.pasta()
        if base is None:
            return False
        pasta = base / str(item.get('id') or int(time.time()))
        pasta.mkdir(parents=True, exist_ok=True)
        reg = {'url': item['url'], 'id': item.get('id'), 'titulo': item.get('titulo') or item['url'],
               'arquivo': None, 'pasta': pasta, 'descartar': False, 'inicio': time.time(), 'fim': None}

        def _rodar():
            arq = None
            try:
                arq = self._baixar(reg['url'], str(pasta), lambda *_a, **_k: None)
            except Exception as e:
                self._reg('AVISO', f"download antecipado falhou: {type(e).__name__}: {e}")
                arq = None
            with self._trava:
                reg['arquivo'] = arq if (arq and os.path.exists(arq)) else None
                reg['fim'] = time.time()
                apagar = reg['descartar']
            if apagar:
                shutil.rmtree(pasta, ignore_errors=True)
            elif reg['arquivo']:
                self._log(f"   ⬇️  Próximo já baixado em segundo plano: {reg['titulo'][:60]} "
                          f"({reg['fim'] - reg['inicio']:.0f}s)")
            else:
                self._log(f"   ⬇️  O download antecipado do próximo não deu certo - ele será baixado "
                          f"na vez dele, como sempre")
                shutil.rmtree(pasta, ignore_errors=True)

        reg['thread'] = threading.Thread(target=_rodar, daemon=True, name='download-antecipado')
        with self._trava:
            self.atual = reg
        self._log(f"   ⬇️  Baixando o próximo em segundo plano enquanto este é cortado: {reg['titulo'][:60]}")
        self._reg('FILA', f"download antecipado: {reg['titulo']} | {reg['url']}")
        reg['thread'].start()
        return True

    def pegar(self, url, mover_para=None) -> Optional[str]:
        """
        O arquivo antecipado deste url, se houver (espera terminar se ainda
        estiver baixando). Com mover_para, o arquivo é movido pra lá (assim a
        limpeza normal do álbum cuida dele). Devolve None se não houver.
        """
        with self._trava:
            reg = self.atual
            if not reg or reg['url'] != url or reg['descartar']:
                return None
        t = reg.get('thread')
        if t is not None and t.is_alive():
            self._log("   ⏳ Este álbum já estava sendo baixado em segundo plano - esperando terminar...")
            t.join()
        with self._trava:
            self.atual = None
            arq = reg['arquivo']
        if not arq or not os.path.exists(arq):
            shutil.rmtree(reg['pasta'], ignore_errors=True)
            return None
        if mover_para:
            os.makedirs(mover_para, exist_ok=True)
            destino = os.path.join(mover_para, os.path.basename(arq))
            shutil.move(arq, destino)
            shutil.rmtree(reg['pasta'], ignore_errors=True)
            arq = destino
        self._log("   ♻️  Usando o áudio que já tinha sido baixado em segundo plano")
        self._reg('FILA', f"download antecipado usado: {reg['titulo']}")
        return arq

    def descartar(self, motivo='', url=None):
        """Apaga o antecipado (ou marca pra apagar quando terminar). Com url, só se for dele."""
        with self._trava:
            reg = self.atual
            if not reg or (url is not None and reg['url'] != url):
                return False
            reg['descartar'] = True
            self.atual = None
            rodando = reg.get('thread') is not None and reg['thread'].is_alive()
        if not rodando:
            shutil.rmtree(reg['pasta'], ignore_errors=True)
        if motivo:
            self._reg('FILA', f"download antecipado descartado ({motivo}): {reg['titulo']}")
        return True

    def rodando(self) -> bool:
        """Há um download antecipado em andamento?"""
        with self._trava:
            reg = self.atual
        return bool(reg and reg.get('thread') is not None and reg['thread'].is_alive())

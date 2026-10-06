"""
O que vai pro disco: nome da pasta do álbum, download do áudio (com novas
tentativas) e capa (baixar e embutir nos MP3). Usado pelos modos álbum
(processo_album.py) e playlist (processo_playlist.py).
"""
import time
from pathlib import Path

import requests

import metadata_manager
import nomes
from util import sanitize

LIMITE_NOME_PASTA = 200      # o Windows aceita 260 caracteres no caminho inteiro
TENTATIVAS_DOWNLOAD = 3


def limpar_nome(nome: str) -> str:
    """Tira o que o Windows não aceita em nome de arquivo (e reticências)."""
    for c in '<>:"/\\|?*':
        nome = nome.replace(c, '')
    return nome.replace('...', '').replace('..', '.').strip()


def nome_da_pasta(artista: str, album: str, ano=None) -> str:
    """'Artista - Álbum (Ano)', sem o ' (N)' do Discogs; corta o álbum se passar do limite."""
    art = limpar_nome(nomes.nome_artista_exibicao(artista))
    alb = limpar_nome(album)
    sufixo = f" ({ano})" if ano else ""
    if len(art) + 3 + len(alb) + len(sufixo) > LIMITE_NOME_PASTA:
        alb = alb[:max(0, LIMITE_NOME_PASTA - len(art) - 3 - len(sufixo))]
    return sanitize(f"{art} - {alb}{sufixo}")


def baixar_audio(downloader, url, pasta, log, tamanho_minimo):
    """
    Baixa o áudio com até 3 tentativas. Para logo quando o motivo não muda
    numa nova tentativa (ex.: bitrate da fonte abaixo do mínimo, ver
    downloader.last_error_retryable). Devolve o caminho ou None; o motivo
    fica em downloader.last_error.
    """
    def progresso(msg):
        # só o que importa: o "Baixando: 43%" de cada pedaço afogaria o log
        if not (msg.startswith('Baixando:') or msg.startswith('Iniciando')):
            log(f"   {msg}")

    for tentativa in range(1, TENTATIVAS_DOWNLOAD + 1):
        try:
            if tentativa > 1:
                log(f"   🔄 Tentativa {tentativa}/{TENTATIVAS_DOWNLOAD}...")
                time.sleep(2)
            arquivo = downloader.download_audio(url, str(pasta), progresso)
            if arquivo and Path(arquivo).exists():
                tamanho = Path(arquivo).stat().st_size
                if tamanho > tamanho_minimo:
                    log("✓ Áudio baixado")
                    return arquivo
                log(f"   ⚠️  Arquivo muito pequeno ({tamanho} bytes)")
                Path(arquivo).unlink()
            else:
                log(f"   ⚠️  Falha na tentativa {tentativa}")
                if not getattr(downloader, 'last_error_retryable', True):
                    return None
        except Exception as e:
            log(f"   ⚠️  Erro na tentativa {tentativa}: {str(e)[:100]}")
    return None


def baixar_capa(url_capa, destino: Path, log, rotulo='Discogs') -> bool:
    """Salva a imagem em destino. Devolve True se deu certo."""
    if not url_capa:
        return False
    log(f"   📥 Baixando capa ({rotulo})...")
    try:
        r = requests.get(url_capa, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
        if r.status_code == 200:
            Path(destino).write_bytes(r.content)
            log(f"   ✓ Capa salva ({rotulo})")
            return True
        log(f"   ⚠️ {rotulo} HTTP {r.status_code}")
    except Exception as e:
        log(f"   ⚠️ Falha ao baixar de {rotulo}: {str(e)[:50]}")
    return False


def embutir_capa(pasta, capa: Path):
    """
    Põe a capa dentro de cada MP3 da pasta (metadata_manager.embutir_capa).
    Devolve os nomes dos arquivos em que NÃO deu (ex.: arquivo aberto noutro programa).
    """
    falhas = []
    for mp3 in sorted(Path(pasta).glob("*.mp3")):
        if not metadata_manager.embutir_capa(mp3, capa):
            falhas.append(mp3.name)
    return falhas

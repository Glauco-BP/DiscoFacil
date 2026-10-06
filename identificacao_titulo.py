"""
Artista, álbum e ano tirados do TÍTULO do vídeo/playlist, por expressões
regulares. É só o ponto de partida da busca: quem dá o nome oficial é o
Discogs (catalogo.py).

Formatos entendidos: "Artista - Álbum", "Artista - Álbum (1975)",
"Artista - Álbum - 1975", com ou sem "Full Album" / "Álbum Completo".
Sem " - ", o título inteiro serve de artista e de álbum.
"""
import re

_FULL_ALBUM = r'(full\s+(album|álbum|albúm)|álbum\s+completo|album\s+completo)'
_ANO = r'[-–—\(]\s*(\d{4})\s*[\)\-–—]?'
_SEPARADOR = r'^(.+?)\s*[-–—]\s*(.+)'


class TituloMixin:
    """Leitura de artista/álbum/ano do título."""

    def _extract_artist(self, title):
        """Artista: o que vem antes do primeiro " - " (sem o ano e o "Full Album")."""
        limpo = re.sub(r'\s*[-–—]?\s*(full\s+album|album\s+completo|álbum\s+completo).*$', '', title,
                       flags=re.IGNORECASE).strip()
        ano = re.search(_ANO, limpo)
        sem_ano = limpo[:ano.start()].strip() if ano else limpo
        m = re.match(_SEPARADOR, sem_ano)
        if m:
            return m.group(1).strip()
        return sem_ano if ano else (limpo or "Unknown Artist")

    def _extract_album(self, title):
        """Álbum: o que vem depois do primeiro " - " (sem o ano e o "Full Album")."""
        limpo = re.sub(r'\s*[-–—(]?\s*' + _FULL_ALBUM + r'\)?.*$', '', title,
                       flags=re.IGNORECASE | re.UNICODE).strip()
        ano = re.search(_ANO, limpo)
        sem_ano = limpo[:ano.start()].strip() if ano else limpo
        m = re.match(_SEPARADOR, sem_ano)
        if m:
            album = re.sub(r'\s*[-–—]?\s*\d{4}\s*$', '', m.group(2).strip()).strip()
            return re.sub(r'\s*\(\d{4}\)\s*$', '', album).strip()
        return sem_ano or "Unknown Album"

    def _extract_year(self, title):
        """Ano entre parênteses ou depois de um traço ("(1975)", "- 1975"), ou ''."""
        m = re.search(_ANO, title)
        return m.group(1) if m else ""

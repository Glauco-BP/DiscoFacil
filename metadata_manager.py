"""
Tags dos MP3, num lugar só (mutagen, ID3 v2.3 - a versão que o Windows lê
melhor): título, artista, álbum, nº/total, ano, artista do álbum, gênero,
capa e os IDs do Discogs.

Os IDs do Discogs (TXXX DISCOGS_MASTER_ID / _RELEASE_ID) são a base do "já
está no acervo?" (acervo_index.py) e viajam com o arquivo mesmo que a pasta
mude de nome.
"""
from pathlib import Path
from typing import Dict, Optional

from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK, TXXX
from mutagen.mp3 import MP3

import nomes

DISCOGS_MASTER_ID_DESC = 'DISCOGS_MASTER_ID'
DISCOGS_RELEASE_ID_DESC = 'DISCOGS_RELEASE_ID'


def _abrir(mp3_file):
    audio = MP3(str(mp3_file), ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    return audio


NOTA_DESC = 'DISCOFACIL_NOTA'       # TXXX com avisos do programa (ex.: nome por palpite)


def gravar_tags(mp3_file, titulo, artista, album, numero, total, ano='', artista_album='',
                genero='', capa: Optional[Path] = None, nota: str = '') -> bool:
    """
    Grava as tags de uma faixa (o que já existir com o mesmo nome é
    substituído). Artistas sem o " (N)" do Discogs. artista_album (TPE2)
    mantém as faixas agrupadas mesmo com participações; vazio = artista.
    nota: aviso do programa gravado em TXXX:DISCOFACIL_NOTA (ex.: nome por
    palpite, a conferir) - dá pra filtrar no player/organizador.
    """
    try:
        audio = _abrir(mp3_file)
        t = audio.tags
        t.add(TIT2(encoding=3, text=str(titulo)))
        t.add(TPE1(encoding=3, text=nomes.nome_artista_exibicao(artista)))
        t.add(TALB(encoding=3, text=str(album)))
        t.add(TRCK(encoding=3, text=f"{numero}/{total}"))
        if ano:
            t.add(TDRC(encoding=3, text=str(ano)))
        t.add(TPE2(encoding=3, text=nomes.nome_artista_exibicao(artista_album or artista)))
        if genero:
            t.add(TCON(encoding=3, text=str(genero)))
        if nota:
            t.add(TXXX(encoding=3, desc=NOTA_DESC, text=str(nota)))
        if capa and Path(capa).exists():
            t.delall('APIC')
            t.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=Path(capa).read_bytes()))
        audio.save(v2_version=3)
        return True
    except Exception as e:
        print(f"Erro ao gravar tags: {e}")
        return False


def embutir_capa(mp3_file, capa) -> bool:
    """Põe a capa (APIC, frente) dentro do MP3, sem mexer no resto."""
    try:
        audio = _abrir(mp3_file)
        audio.tags.delall('APIC')
        audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=Path(capa).read_bytes()))
        audio.save(v2_version=3)
        return True
    except Exception as e:
        print(f"Erro ao embutir a capa: {e}")
        return False


class MetadataManager:
    """Leitura e gravação dos IDs do Discogs nos MP3."""
    
    def add_discogs_ids(self, mp3_file: str, master_id=None, release_id=None) -> bool:
        """
        Grava SÓ as tags TXXX de master_id/release_id do Discogs, sem tocar
        nas outras.
        """
        if not master_id and not release_id:
            return False
        try:
            audio = _abrir(mp3_file)
            if master_id:
                audio.tags.add(TXXX(
                    encoding=3, desc=DISCOGS_MASTER_ID_DESC, text=str(master_id)
                ))
            if release_id:
                audio.tags.add(TXXX(
                    encoding=3, desc=DISCOGS_RELEASE_ID_DESC, text=str(release_id)
                ))

            audio.save(v2_version=3)
            return True
        except Exception as e:
            print(f"Erro ao gravar IDs do Discogs: {e}")
            return False

    def read_discogs_ids(self, mp3_file: str) -> Dict[str, Optional[str]]:
        """
        Lê master_id/release_id do Discogs gravados num MP3 (tags TXXX),
        se existirem. Usado para reconstruir o acervo_index.json quando ele
        estiver ausente, varrendo os MP3s já baixados.

        Retorna {'master_id': str|None, 'release_id': str|None}
        """
        result = {'master_id': None, 'release_id': None}
        try:
            audio = MP3(mp3_file, ID3=ID3)
            if not audio.tags:
                return result

            master_frame = audio.tags.get(f'TXXX:{DISCOGS_MASTER_ID_DESC}')
            if master_frame and master_frame.text:
                result['master_id'] = str(master_frame.text[0])

            release_frame = audio.tags.get(f'TXXX:{DISCOGS_RELEASE_ID_DESC}')
            if release_frame and release_frame.text:
                result['release_id'] = str(release_frame.text[0])

        except Exception as e:
            print(f"Erro ao ler IDs do Discogs: {e}")

        return result
    
"""
Índice dos álbuns já presentes no acervo (pasta de saída), por master_id do
Discogs (ou release_id, quando o lançamento não tem master). Responde rápido
"esse álbum já está no acervo?" antes de baixar.

A fonte da verdade são as tags ID3 TXXX:DISCOGS_MASTER_ID/RELEASE_ID das
faixas (ver metadata_manager.py); acervo_index.json é só um cache delas,
reconstruído varrendo os MP3s quando falta ou quando forçado.
"""
import json
from pathlib import Path
from typing import Dict, Optional, Callable

INDEX_FILENAME = 'acervo_index.json'


class AcervoIndex:
    """Mapa {master_id|release_id: {'folder', 'release_id'}} do acervo em disco."""

    def __init__(self, output_dir: str, metadata_manager=None):
        self.output_dir = Path(output_dir)
        self.index_path = self.output_dir / INDEX_FILENAME
        # Import tardio: evita dependência circular e custo nos testes.
        if metadata_manager is None:
            from metadata_manager import MetadataManager
            metadata_manager = MetadataManager()
        self._metadata_manager = metadata_manager
        # {master_id (str): {'folder': str, 'release_id': str|None}}
        self.data: Dict[str, Dict] = {}

    def _log(self, msg: str, log_func: Optional[Callable] = None):
        if log_func:
            log_func(msg)
        else:
            print(msg)

    def load_or_rebuild(self, log_func: Optional[Callable] = None,
                         force_rebuild: bool = False) -> 'AcervoIndex':
        """
        Carrega o índice do JSON; se faltar ou estiver corrompido, reconstrói
        a partir das tags dos MP3s e salva.

        force_rebuild=True ignora o JSON e relê o disco. O programa usa assim
        uma vez por sessão (_ensure_acervo_and_queue), pois pastas podem ter
        sido apagadas, movidas ou copiadas por fora desde a última vez.
        """
        if force_rebuild:
            self._rebuild_from_disk(log_func, reason='forced')
            self.save()
            return self

        if self.index_path.exists():
            try:
                with open(self.index_path, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                self._log(f"📇 Índice do acervo carregado: {len(self.data)} álbum(ns)", log_func)
                return self
            except Exception as e:
                self._log(f"⚠️  Índice do acervo corrompido ({e}) - reconstruindo...", log_func)
                self.data = {}

        self._rebuild_from_disk(log_func)
        self.save()
        return self

    def _rebuild_from_disk(self, log_func: Optional[Callable] = None, reason: str = 'missing'):
        """Varre as subpastas do acervo e reconstrói o índice a partir das tags ID3."""
        self.data = {}
        if not self.output_dir.exists():
            return

        if reason == 'forced':
            self._log("🔧 Relendo o acervo do disco (índice é refeito a cada abertura)...", log_func)
        else:
            self._log("🔧 Arquivo de índice ausente - reconstruindo a partir dos álbuns já baixados...", log_func)
        found = 0
        scanned = 0
        for folder in sorted(self.output_dir.iterdir()):
            if not folder.is_dir() or folder.name.startswith(('.', '_')):
                continue                    # .audios_pasta_pendencia, _temp: não são discos do acervo
            mp3_files = sorted(folder.glob('*.mp3'))
            if not mp3_files:
                continue
            scanned += 1
            # Basta UMA faixa: todas do álbum têm os mesmos IDs.
            ids = self._metadata_manager.read_discogs_ids(str(mp3_files[0]))
            master_id = ids.get('master_id')
            release_id = ids.get('release_id')
            # Sem master_id, a chave é o release_id (mesma regra do resto do
            # programa): nem todo lançamento do Discogs tem master.
            dedupe_key = master_id or release_id
            if dedupe_key:
                self.data[str(dedupe_key)] = {
                    'folder': folder.name,
                    'release_id': release_id,
                }
                found += 1

        self._log(f"🔧 Reconstrução concluída: {found}/{scanned} pasta(s) com master_id/release_id identificado", log_func)

    def has(self, master_id) -> bool:
        """
        O álbum está no acervo e a pasta ainda existe? Entrada cuja pasta foi
        apagada com o programa aberto é esquecida (permite baixar de novo).
        """
        if not master_id:
            return False
        chave = str(master_id)
        entrada = self.data.get(chave)
        if not entrada:
            return False
        pasta = entrada.get('folder')
        if pasta and not (self.output_dir / pasta).exists():
            self.data.pop(chave, None)
            try:
                self.save()
            except Exception:
                pass
            return False
        return True

    def get(self, master_id) -> Optional[Dict]:
        return self.data.get(str(master_id)) if master_id else None

    def add(self, master_id, folder_name: str, release_id=None) -> None:
        """Registra um álbum recém-gravado (chave: master_id ou release_id) e salva."""
        if not master_id:
            return
        self.data[str(master_id)] = {
            'folder': folder_name,
            'release_id': str(release_id) if release_id else None,
        }
        self.save()

    def save(self) -> bool:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            with open(self.index_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar acervo_index.json: {e}")
            return False

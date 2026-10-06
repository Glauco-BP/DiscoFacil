"""
Lista "Precisam de você": álbuns que o processamento automático não
concluiu e esperam decisão do usuário. Persistida em fila_pendentes.json.

kind: 'baixa_confianca' (Discogs achou, mas com confiança baixa),
'nao_encontrado' (nada no Discogs), 'erro_discogs' (Discogs não respondeu),
'falha_download', 'falha_corte' e 'outro_disco' (o corte mostrou que o
disco identificado provavelmente não é o do vídeo). "Remover" manda o item para
"Descartados" (pendentes_descartados.json), de onde pode ser recuperado.
Acesso protegido por trava: a janela e o trabalhador usam de threads distintas.
"""
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

QUEUE_FILENAME = 'fila_pendentes.json'
# "Remover" não apaga de vez: o item vai pra cá ("Descartados").
DESCARTADOS_FILENAME = 'pendentes_descartados.json'


class PendingQueue:
    """Itens pendentes + descartados, gravados em JSON; `versao` sobe a cada gravação."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.queue_path = self.output_dir / QUEUE_FILENAME
        self.descartados_path = self.output_dir / DESCARTADOS_FILENAME
        self.items: List[Dict] = []
        self.descartados: List[Dict] = []
        # A janela e o trabalhador da fila mexem aqui de threads diferentes.
        self._trava = threading.RLock()
        # Sobe a cada gravação: a janela compara pra só redesenhar quando muda.
        self.versao = 0
        self.load()
        self._carregar_descartados()

    def load(self) -> None:
        if self.queue_path.exists():
            try:
                with open(self.queue_path, 'r', encoding='utf-8') as f:
                    self.items = json.load(f)
            except Exception as e:
                print(f"Erro ao carregar fila de pendentes: {e}")
                self.items = []
        else:
            self.items = []

    def save(self) -> bool:
        """Grava a lista (temporário + replace). Devolve False se falhar."""
        with self._trava:
            self.versao += 1
            try:
                self.output_dir.mkdir(parents=True, exist_ok=True)
                tmp = self.queue_path.with_suffix('.tmp')
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(self.items, f, indent=2, ensure_ascii=False)
                tmp.replace(self.queue_path)
                return True
            except Exception as e:
                print(f"Erro ao salvar fila de pendentes: {e}")
                return False

    # ------------------------------------------------------------------
    # Descartados e ações em lote (uma gravação por ação, não por item)
    # ------------------------------------------------------------------
    def _carregar_descartados(self) -> None:
        try:
            if self.descartados_path.exists():
                with open(self.descartados_path, 'r', encoding='utf-8') as f:
                    self.descartados = json.load(f)
        except Exception as e:
            print(f"Erro ao carregar descartados: {e}")
            self.descartados = []

    def _salvar_descartados(self) -> bool:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            tmp = self.descartados_path.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self.descartados, f, indent=2, ensure_ascii=False)
            tmp.replace(self.descartados_path)
            return True
        except Exception as e:
            print(f"Erro ao salvar descartados: {e}")
            return False

    def descartar(self, ids) -> int:
        """
        Move os itens `ids` da lista para os descartados (recuperáveis com
        recuperar()). Devolve quantos saíram.
        """
        ids = set(ids)
        with self._trava:
            saem = [i for i in self.items if i['id'] in ids]
            if not saem:
                return 0
            agora = time.strftime('%Y-%m-%d %H:%M:%S')
            for i in saem:
                i['descartado_em'] = agora
                i['marked_for_download'] = False
            urls = {i['url'] for i in saem}
            self.descartados = [d for d in self.descartados if d.get('url') not in urls] + saem
            self.items = [i for i in self.items if i['id'] not in ids]
            self._salvar_descartados()
            self.save()
            return len(saem)

    def recuperar(self, ids) -> int:
        """Devolve itens descartados pra lista. Devolve quantos voltaram."""
        ids = set(ids)
        with self._trava:
            voltam = [d for d in self.descartados if d['id'] in ids]
            if not voltam:
                return 0
            urls_na_lista = {i['url'] for i in self.items}
            for d in voltam:
                d.pop('descartado_em', None)
                if d['url'] not in urls_na_lista:
                    self.items.append(d)
            self.descartados = [d for d in self.descartados if d['id'] not in ids]
            self._salvar_descartados()
            self.save()
            return len(voltam)

    def add(self, kind: str, url: str, video_title: str,
            title_artist: str = '', title_album: str = '', year: str = '',
            confidence_pct: int = 0, reason: str = '',
            discogs_data: Optional[Dict] = None, source_type: str = 'video', **extras) -> Dict:
        """
        Adiciona um item (ou devolve o já existente com a mesma URL).

        kind: um dos motivos do módulo. source_type: 'video' (um vídeo = um
        álbum) ou 'playlist' (cada vídeo é uma faixa). discogs_data: resultado
        já obtido do Discogs, reaproveitado ao reprocessar. `extras` não-None
        (ex.: 'candidatas', 'notas') vão direto pro item.
        """
        with self._trava:
            for item in self.items:
                if item['url'] == url:
                    if item.get('kind') == 'erro_discogs' and kind != 'erro_discogs':
                        # só esperava o Discogs responder: fica com o resultado novo
                        item.update({'kind': kind, 'video_title': video_title or item['video_title'],
                                     'title_artist': title_artist, 'title_album': title_album, 'year': year,
                                     'confidence_pct': confidence_pct, 'reason': reason,
                                     'discogs_data': discogs_data, 'source_type': source_type})
                        item.update({k: v for k, v in extras.items() if v is not None})
                        self.save()
                    return item

        item = {
            'id': uuid.uuid4().hex[:12],
            'kind': kind,
            'source_type': source_type,
            'url': url,
            'video_title': video_title,
            'title_artist': title_artist,
            'title_album': title_album,
            'year': year,
            'confidence_pct': confidence_pct,
            'reason': reason,
            'discogs_data': discogs_data,
            'marked_for_download': False,
            'falhas': 0,
            'added_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        item.update({k: v for k, v in extras.items() if v is not None})
        with self._trava:
            self.items.append(item)
            self.save()
        return item

    def corrigir_busca(self, item_id: str, artista: str, album: str) -> Optional[Dict]:
        """
        O usuário corrigiu o artista/álbum a buscar. O que foi achado antes
        (dados do Discogs, edições candidatas) deixa de valer; ao processar,
        a busca é refeita com os nomes novos (ver 'busca_corrigida').
        """
        with self._trava:
            item = self.get(item_id)
            if not item:
                return None
            item.update({'title_artist': artista.strip(), 'title_album': album.strip(),
                         'busca_corrigida': True, 'discogs_data': None, 'confidence_pct': 0,
                         'editor_sem_discogs': False,
                         'reason': f"Busca corrigida por você: {artista.strip()} – {album.strip()}"})
            item.pop('candidatas', None)
            self.save()
            return item

    def informar_tempos(self, item_id: str, texto: str, extra: Optional[Dict] = None) -> Optional[Dict]:
        """
        O usuário colou a lista com os tempos das faixas (ou salvou no ✂ Editar). Ao processar, o
        corte é feito nesses tempos antes de tudo ('tempos_usuario'). `extra`: outros campos do item
        (ex.: artista/álbum digitados no editor, 'editor_sem_discogs').
        """
        with self._trava:
            item = self.get(item_id)
            if not item:
                return None
            linhas = len([l for l in (texto or '').splitlines() if l.strip()])
            if (texto or '').lstrip().startswith('#exato'):
                motivo = f"Cortes conferidos por você no ✂ Editar ({linhas - 1} faixas)"
            else:
                motivo = f"Tempos informados por você ({linhas} linhas)"
            item.update({'tempos_usuario': texto, 'reason': motivo})
            item.update(extra or {})
            self.save()
            return item

    def remove(self, item_id: str) -> None:
        with self._trava:
            self.items = [i for i in self.items if i['id'] != item_id]
            self.save()

    def get(self, item_id: str) -> Optional[Dict]:
        for item in self.items:
            if item['id'] == item_id:
                return item
        return None

    def __len__(self) -> int:
        return len(self.items)

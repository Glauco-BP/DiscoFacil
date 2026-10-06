"""
Fila única de trabalho: a única fonte da verdade sobre o que fazer e o que
já foi feito, consumida por UM trabalhador (os botões só enfileiram, então
não há dois processamentos concorrentes). Persistida em <saída>/fila.json.

Tipos e prioridade (menor sai primeiro): disco_unico 0, playlist 1,
pendencia 2, canal 3. Item novo não interrompe o álbum em andamento; só
passa à frente na próxima volta do laço.

Estados: pendente, processando, feito, rejeitado. Itens feitos/rejeitados
ficam como histórico: é o que impede repetir trabalho já feito ou recusado.
"""

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional


class FilaUnica:
    """Fila persistente com prioridade, deduplicada por URL e gravação atômica."""

    PRIORIDADES = {
        'disco_unico': 0,
        'playlist': 1,
        'pendencia': 2,
        'nova_tentativa': 2,    # álbum que esperava o Discogs responder (limite de pedidos)
        'canal': 3,
    }

    ESTADOS_ABERTOS = ('pendente', 'processando')
    ESTADOS_FECHADOS = ('feito', 'rejeitado')

    def __init__(self, pasta_saida, nome='fila.json'):
        self.caminho = Path(pasta_saida) / nome
        self.items: List[Dict] = []
        self._contador = 0
        self._adiando = 0           # >0: dentro de em_lote(), grava só no fim
        self._sujo = False
        self.carregar()

    def em_lote(self):
        """`with fila.em_lote(): ...` - várias mudanças, uma gravação só no fim."""
        fila = self

        class _Lote:
            def __enter__(self_):
                fila._adiando += 1
                return fila

            def __exit__(self_, *a):
                fila._adiando -= 1
                if fila._adiando == 0 and fila._sujo:
                    fila._sujo = False
                    fila.salvar()
                return False
        return _Lote()

    # ------------------------------------------------------------------
    # Disco
    # ------------------------------------------------------------------

    def carregar(self) -> None:
        """
        Lê a fila do disco. Item 'processando' volta a 'pendente' (o programa
        caiu ou foi fechado no meio); senão ficaria travado num estado que
        ninguém consome. Arquivo ilegível é renomeado para .corrompido.
        """
        self.items = []
        self._contador = 0
        if not self.caminho.exists():
            return
        try:
            with open(self.caminho, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            self.items = dados.get('items', []) if isinstance(dados, dict) else list(dados)
            self._contador = dados.get('contador', 0) if isinstance(dados, dict) else 0
        except Exception:
            # Arquivo corrompido: guarda pra inspeção e começa limpo.
            try:
                self.caminho.rename(self.caminho.with_suffix('.corrompido'))
            except Exception:
                pass
            self.items = []
            self._contador = 0
            return

        interrompidos = 0
        for it in self.items:
            if it.get('estado') == 'processando':
                it['estado'] = 'pendente'
                interrompidos += 1
        if interrompidos:
            self.salvar()
        self._interrompidos_ao_abrir = interrompidos

    def salvar(self) -> None:
        """
        Grava de forma atômica (temporário + os.replace): uma queda no meio
        deixa o arquivo antigo ou o novo inteiro, nunca um meio-termo.
        Dentro de em_lote() só marca como sujo.
        """
        if self._adiando:
            self._sujo = True
            return
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        dados = {'contador': self._contador, 'items': self.items}
        tmp_fd, tmp_nome = tempfile.mkstemp(
            dir=str(self.caminho.parent), prefix='.fila_', suffix='.tmp'
        )
        try:
            with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_nome, str(self.caminho))
        except Exception:
            try:
                os.unlink(tmp_nome)
            except Exception:
                pass
            raise

    # ------------------------------------------------------------------
    # Entrada
    # ------------------------------------------------------------------

    def adicionar(self, tipo: str, url: str, titulo: str = '',
                  discogs_data=None, motivo: str = '',
                  reabrir_se_fechado: bool = False, **extras) -> Optional[Dict]:
        """
        Põe um item na fila. Devolve o item, ou None se foi ignorado.

        Não duplica por URL. URL já feita/rejeitada é ignorada, salvo com
        reabrir_se_fechado=True (usuário pediu pra tentar de novo). URL já
        presente é promovida (ver abaixo). `extras` vão direto pro item.
        """
        if tipo not in self.PRIORIDADES:
            raise ValueError(f"tipo desconhecido: {tipo}")

        existente = self.por_url(url)
        if existente:
            fechado = existente['estado'] in self.ESTADOS_FECHADOS
            if fechado and not reabrir_se_fechado:
                return None
            # Promove o existente: o pedido novo manda. Tipo, prioridade e
            # extras (ex.: 'pendencia_item') são atualizados e o item vai pro
            # fim da ordem do seu tipo. Sem isso, um disco que já estava na
            # fila vindo do canal continuaria com prioridade 3.
            self._contador += 1
            existente['tipo'] = tipo
            existente['prioridade'] = self.PRIORIDADES[tipo]
            existente['ordem'] = self._contador
            existente['atualizado_em'] = self._agora()
            if fechado:
                existente['estado'] = 'pendente'
                existente['falhas'] = 0
                existente['motivo'] = ''
            if discogs_data is not None:
                existente['discogs_data'] = discogs_data
            if titulo:
                existente['titulo'] = titulo
            existente.update(extras)
            self.salvar()
            return existente

        self._contador += 1
        item = {
            'id': uuid.uuid4().hex[:12],
            'tipo': tipo,
            'prioridade': self.PRIORIDADES[tipo],
            'ordem': self._contador,
            'url': url,
            'titulo': titulo,
            'estado': 'pendente',
            'falhas': 0,
            'motivo': motivo,
            'discogs_data': discogs_data,
            'adicionado_em': self._agora(),
            'atualizado_em': self._agora(),
        }
        item.update(extras)
        self.items.append(item)
        self.salvar()
        return item

    def adicionar_varios(self, tipo: str, entradas) -> int:
        """
        Enfileira muitas entradas (URLs ou dicts com 'url'/'titulo'), como os
        milhares de vídeos de um canal, gravando uma vez só. Ignora URLs já
        presentes. Devolve quantas entraram.
        """
        novos = 0
        for e in entradas:
            url = e.get('url') if isinstance(e, dict) else e
            if not url:
                continue
            titulo = e.get('titulo', '') if isinstance(e, dict) else ''
            if self.por_url(url):
                continue
            self._contador += 1
            self.items.append({
                'id': uuid.uuid4().hex[:12],
                'tipo': tipo,
                'prioridade': self.PRIORIDADES[tipo],
                'ordem': self._contador,
                'url': url,
                'titulo': titulo,
                'estado': 'pendente',
                'falhas': 0,
                'motivo': '',
                'discogs_data': None,
                'adicionado_em': self._agora(),
                'atualizado_em': self._agora(),
            })
            novos += 1
        if novos:
            self.salvar()
        return novos

    # ------------------------------------------------------------------
    # Consumo
    # ------------------------------------------------------------------

    def proximo(self) -> Optional[Dict]:
        """
        Próximo pendente: menor prioridade e, entre iguais, o mais antigo.
        O trabalhador só chama ao terminar o item anterior, por isso nada é
        interrompido.
        """
        abertos = [i for i in self.items if i.get('estado') == 'pendente']
        if not abertos:
            return None
        return min(abertos, key=lambda i: (i.get('prioridade', 9), i.get('ordem', 0)))

    def marcar_processando(self, item_id: str) -> None:
        self._mudar_estado(item_id, 'processando')

    def marcar_feito(self, item_id: str, pasta: str = '') -> None:
        """Fecha o item como 'feito', guardando a pasta do álbum gerado."""
        it = self.get(item_id)
        if it and pasta:
            it['pasta'] = pasta
        self._mudar_estado(item_id, 'feito')

    def marcar_falha(self, item_id: str, motivo: str = '', max_falhas: int = 1) -> str:
        """
        Conta a falha: volta a 'pendente' ou vira 'rejeitado' ao atingir
        max_falhas. Padrão 1: repetir o mesmo vídeo não resolve quando a causa
        é o áudio ou o catálogo. Devolve o estado final.
        """
        it = self.get(item_id)
        if not it:
            return 'pendente'
        it['falhas'] = int(it.get('falhas', 0)) + 1
        it['motivo'] = motivo or it.get('motivo', '')
        it['estado'] = 'rejeitado' if it['falhas'] >= max_falhas else 'pendente'
        it['atualizado_em'] = self._agora()
        self.salvar()
        return it['estado']

    def remover(self, item_id: str) -> None:
        self.items = [i for i in self.items if i.get('id') != item_id]
        self.salvar()

    # ------------------------------------------------------------------
    # Consulta
    # ------------------------------------------------------------------

    def get(self, item_id: str) -> Optional[Dict]:
        for i in self.items:
            if i.get('id') == item_id:
                return i
        return None

    def por_url(self, url: str) -> Optional[Dict]:
        for i in self.items:
            if i.get('url') == url:
                return i
        return None

    def por_estado(self, estado: str) -> List[Dict]:
        return [i for i in self.items if i.get('estado') == estado]

    def contagens(self) -> Dict[str, int]:
        """Quantos itens há em cada estado."""
        c = {'pendente': 0, 'processando': 0, 'feito': 0, 'rejeitado': 0}
        for i in self.items:
            e = i.get('estado', 'pendente')
            c[e] = c.get(e, 0) + 1
        return c

    # ------------------------------------------------------------------

    def _mudar_estado(self, item_id: str, estado: str) -> None:
        it = self.get(item_id)
        if it:
            it['estado'] = estado
            it['atualizado_em'] = self._agora()
            self.salvar()

    @staticmethod
    def _agora() -> str:
        return time.strftime('%Y-%m-%d %H:%M:%S')

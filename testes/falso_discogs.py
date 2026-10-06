"""
Discogs (e MusicBrainz) falsos, no formato das respostas reais da API, pra
testar identificação sem internet.

    fd = FalsoDiscogs()
    fd.release(101, 'Simone (3)', 'Pedaço De Mim', 1980, [('Faixa', '3:20'), ...], master=55)
    fd.ligar(catalogo)                 # troca _discogs_get do catalogo.Catalogo
"""


class Resp:
    def __init__(self, dados, status=200):
        self._d = dados
        self.status_code = status

    def json(self):
        return self._d


class FalsoDiscogs:
    def __init__(self):
        self.releases = {}
        self.chamadas = []

    def release(self, rid, artista, titulo, ano, faixas, master=None, generos=('Jazz',),
                formatos=None, artistas=None):
        self.releases[rid] = {
            'id': rid, 'title': titulo, 'year': ano, 'master_id': master,
            'artists': [{'name': a} for a in (artistas or [artista])],
            'genres': list(generos), 'styles': [],
            'formats': formatos or [{'name': 'Vinyl', 'descriptions': ['LP', 'Album']}],
            'images': [{'uri': f'https://img/{rid}.jpg'}],
            'tracklist': [{'type_': 'track', 'position': str(i + 1), 'title': t, 'duration': d}
                          for i, (t, d) in enumerate(faixas)],
        }
        return self.releases[rid]

    def _busca(self):
        return {'results': [{'id': rid, 'title': f"{r['artists'][0]['name']} - {r['title']}",
                             'year': str(r['year']), 'master_id': r['master_id']}
                            for rid, r in self.releases.items()]}

    def get(self, url, params=None, timeout=None, max_retries=None, log_func=None):
        self.chamadas.append((url, dict(params or {})))
        if 'database/search' in url:
            return Resp(self._busca())
        if '/releases/' in url:
            rid = int(url.rstrip('/').split('/')[-1])
            if rid in self.releases:
                return Resp(self.releases[rid])
            return Resp({}, 404)
        if '/masters/' in url:
            return Resp({'results': []})
        return Resp({}, 404)

    def ligar(self, hunter):
        hunter._discogs_get = self.get
        hunter.config['discogs_token'] = 'x'
        return self


def config_falsa(saida, valores=None):
    """
    Config de mentira que se comporta como a real: chave ausente devolve o
    PADRÃO pedido (devolver '' pra tudo já fez código antigo apagar a pasta atual).
    """
    import types
    valores = valores or {}
    return types.SimpleNamespace(
        get_output_directory=lambda: saida,
        get=lambda k, d=None: valores.get(k, d),
        has_api_key=lambda nome: bool(valores.get(f'api_keys.{nome}')),
    )

"""
Configurações do DiscoFácil em config.json: pasta de saída, chaves de API
(api_keys.*) e ajustes (settings.*). Acesso por notação de ponto, ex.:
config.get('settings.min_bitrate_kbps', 80). set() grava na hora.
As chaves nunca devem ir pro log (ver registro.py).

Formato antigo (bloco "apis", pasta dentro de "settings", ajustes que não
são mais usados) é convertido ao abrir, com cópia do original em
config.json.antigo; o que mudou fica em `migracao` (sem as chaves).
"""
import json
import os
import shutil

# Ajustes que versões antigas gravavam e que nada mais lê
AJUSTES_SEM_USO = ('audio_quality', 'silence_threshold', 'min_silence_duration')

class ConfigManager:
    """Gerencia configurações da aplicação"""
    
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self.migracao = []
        self.config = self.load_config()
        self._converter_formato_antigo()

    def _converter_formato_antigo(self):
        """
        Leva o que estiver no formato antigo pro atual, sem perder nada que
        ainda é usado: chaves do bloco "apis" só preenchem as de "api_keys"
        que estiverem vazias. Guarda o original antes de gravar.
        """
        cfg = self.config
        if not isinstance(cfg, dict):
            return
        settings = cfg.get('settings') if isinstance(cfg.get('settings'), dict) else {}
        antigos = 'apis' in cfg or 'output_directory' in settings or any(k in settings for k in AJUSTES_SEM_USO)
        if not antigos:
            return
        apis = cfg.get('apis') if isinstance(cfg.get('apis'), dict) else {}
        chaves = cfg.setdefault('api_keys', {})
        google = chaves.setdefault('google_custom_search', {})
        for antigo, destino, nome in (('discogs_token', (chaves, 'discogs_token'), 'Discogs'),
                                      ('groq_api_key', (chaves, 'groq'), 'Groq'),
                                      ('youtube_api_key', (google, 'api_key'), 'YouTube Data API')):
            valor = (apis.get(antigo) or '').strip() if isinstance(apis.get(antigo), str) else ''
            onde, campo = destino
            if valor and not (onde.get(campo) or '').strip():
                onde[campo] = valor
                self.migracao.append(f"chave do {nome} levada pro formato novo")
        if 'apis' in cfg:
            cfg.pop('apis')
            self.migracao.append('bloco antigo "apis" removido (Last.fm não é mais usado)')
        pasta = settings.pop('output_directory', None)
        if pasta is not None:
            if not cfg.get('output_directory'):
                cfg['output_directory'] = pasta
            self.migracao.append('pasta de saída repetida em "settings" removida')
        sem_uso = [k for k in AJUSTES_SEM_USO if settings.pop(k, None) is not None]
        if sem_uso:
            self.migracao.append(f"ajustes sem uso removidos ({', '.join(sem_uso)})")
        try:
            if os.path.exists(self.config_file):
                copia = self.config_file + '.antigo'
                if not os.path.exists(copia):
                    shutil.copy2(self.config_file, copia)
                self.migracao.append(f"original guardado em {os.path.basename(copia)}")
        except Exception as e:
            self.migracao.append(f"não consegui guardar o original ({e})")
        self.save_config()
    
    def load_config(self):
        """Carrega configurações do arquivo JSON"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Erro ao carregar config: {e}")
                return self._get_default_config()
        else:
            return self._get_default_config()
    
    def _get_default_config(self):
        """Retorna configuração padrão"""
        return {
            "output_directory": "",
            "api_keys": {
                "groq": "",
                "discogs_token": "",
                "google_custom_search": {
                    "api_key": ""
                }
            },
            "settings": {
                "min_bitrate_kbps": 80
            }
        }
    
    def save_config(self):
        """Salva configurações no arquivo JSON"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Erro ao salvar config: {e}")
            return False
    
    def get(self, key, default=None):
        """Obtém valor de configuração usando notação de ponto"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key, value):
        """Define valor de configuração usando notação de ponto"""
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
        self.save_config()
    
    def get_output_directory(self):
        """Retorna diretório de saída"""
        return self.config.get('output_directory', '')
    
    def set_output_directory(self, directory):
        """Define diretório de saída"""
        self.config['output_directory'] = directory
        self.save_config()
    
    def has_api_key(self, api_name):
        """Verifica se possui chave de API"""
        key = self.get(f"api_keys.{api_name}", "")
        return bool(key and key.strip())
    
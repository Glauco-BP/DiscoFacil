"""
Groq (IA) como AJUDA - sempre só sugestão.

Onde entra:
- álbum que o título do vídeo não traz: lê título + descrição e sugere
  artista/álbum pra BUSCAR no Discogs (quem confirma é o Discogs, pela nota
  de identificação);
- nome de faixa de playlist que a comparação normal não casou: sugere qual
  faixa do Discogs é - só vale se a DURAÇÃO do vídeo confirmar;
- ordem das faixas daquele vídeo, lida da descrição: vira mais uma opção de
  corte, que só é usada se ENCAIXAR nos silêncios do áudio.

Regras: não ouve áudio (não corta nada); pode inventar, então nunca decide
sozinho; o plano gratuito tem limite - ao receber "limite atingido", fica
10 minutos sem perguntar nada (e diz isso no log uma vez). Respostas iguais
não são perguntadas duas vezes na mesma abertura.
"""
import json
import re
import time
from typing import Callable, Dict, List, Optional

# Modelos em ordem de preferência. O Groq aposenta modelos (o llama-3.3-70b
# saiu em 16/08/2026 e passou a responder 404): quando um some, o próximo da
# lista é usado na hora e fica valendo até o programa fechar.
MODELOS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"]
PAUSA_LIMITE_SEG = 600
# Os gpt-oss "pensam" antes de responder e esse raciocínio gasta tokens da
# resposta: pensamento curto e folga no limite, senão a resposta sai vazia.
FOLGA_RACIOCINIO = 1024


def _modelo_sumiu(msg: str) -> bool:
    """O erro diz que o MODELO não existe mais (e não que a chave ou a rede falhou)?"""
    m = msg.lower()
    return ('404' in m or 'model_not_found' in m or 'decommissioned' in m
            or 'does not exist' in m or 'model_decommissioned' in m)


class AjudaGroq:
    """
    Perguntas ao Groq com cache por abertura e pausa ao atingir o limite.
    chave() devolve a chave atual da API; fabrica_cliente(chave) substitui o
    cliente groq (testes).
    """

    def __init__(self, chave: Callable[[], str], log: Callable = None, reg: Callable = None,
                 fabrica_cliente: Callable = None):
        self._chave = chave
        self._log = log or (lambda *a: None)
        self._reg = reg or (lambda *a: None)
        self._fabrica = fabrica_cliente
        self._cliente = None
        self._chave_do_cliente = None
        self._pausa_ate = 0.0
        self._cache = {}
        self.perguntas = 0
        self._modelo = 0                # índice em MODELOS do que está respondendo

    # ------------------------------------------------------------------
    def disponivel(self) -> bool:
        """Há chave configurada e não está em pausa por limite?"""
        try:
            ch = (self._chave() or '').strip()
        except Exception:
            ch = ''
        return bool(ch) and time.time() >= self._pausa_ate

    def _obter_cliente(self):
        """Cliente Groq, recriado se a chave mudou."""
        ch = (self._chave() or '').strip()
        if self._cliente is None or ch != self._chave_do_cliente:
            if self._fabrica:
                self._cliente = self._fabrica(ch)
            else:
                from groq import Groq
                self._cliente = Groq(api_key=ch)
            self._chave_do_cliente = ch
        return self._cliente

    def _perguntar(self, tarefa: str, prompt: str, max_tokens: int = 300) -> Optional[str]:
        """
        Texto da resposta, ou None (indisponível/erro). Usa o cache; erro de
        limite (429) pausa por PAUSA_LIMITE_SEG.
        """
        if not self.disponivel():
            return None
        chave_cache = (tarefa, prompt)
        if chave_cache in self._cache:
            return self._cache[chave_cache]
        texto, msg = None, ''
        while self._modelo < len(MODELOS):
            modelo = MODELOS[self._modelo]
            try:
                texto = self._chamar(modelo, prompt, max_tokens)
                break
            except Exception as e:
                msg = f"{type(e).__name__}: {str(e)[:160]}"
                if _modelo_sumiu(msg) and self._modelo + 1 < len(MODELOS):
                    self._modelo += 1
                    self._log(f"   🤖 Groq: o modelo {modelo} saiu do ar - usando {MODELOS[self._modelo]}")
                    self._reg('AVISO', f"Groq: modelo {modelo} indisponível ({msg[:100]}) - trocando por "
                                       f"{MODELOS[self._modelo]}")
                    continue
                break
        if texto is None:
            if '429' in msg or 'rate' in msg.lower() or 'limit' in msg.lower():
                self._pausa_ate = time.time() + PAUSA_LIMITE_SEG
                self._log("   🤖 Groq: limite do plano gratuito atingido - sem perguntar nada por 10 minutos")
            else:
                self._log(f"   🤖 Groq: não respondeu ({msg[:80]})")
            self._reg('AVISO', f"Groq ({tarefa}) falhou: {msg}")
            return None
        self._cache[chave_cache] = texto
        self._reg('AVISO', f"Groq ({tarefa}) respondeu: {texto[:300]}")
        return texto

    def _chamar(self, modelo: str, prompt: str, max_tokens: int) -> str:
        """Uma pergunta a um modelo; devolve o texto (levanta exceção no erro)."""
        cli = self._obter_cliente()
        self.perguntas += 1
        extra = {}
        if modelo.startswith('openai/gpt-oss'):
            extra = {'reasoning_effort': 'low', 'include_reasoning': False}
            max_tokens += FOLGA_RACIOCINIO
        r = cli.chat.completions.create(
            model=modelo, messages=[{"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=max_tokens, **({'extra_body': extra} if extra else {}))
        return (r.choices[0].message.content or '').strip()

    @staticmethod
    def _json(texto: Optional[str]):
        """Primeiro objeto/lista JSON da resposta (tolera cercas ```), ou None."""
        if not texto:
            return None
        t = re.sub(r'```(?:json)?\s*|\s*```', '', texto).strip()
        m = re.search(r'(\{.*\}|\[.*\])', t, re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(1))
        except Exception:
            return None

    # ------------------------------------------------------------------
    def album_do_titulo_e_descricao(self, titulo: str, descricao: str) -> Optional[Dict]:
        """{'artist','album','year'} pra BUSCAR no Discogs, ou None."""
        prompt = (
            "Este é um vídeo do YouTube com um álbum completo. Diga o ARTISTA e o nome do ÁLBUM, "
            "usando SÓ o que está escrito no título e na descrição abaixo. Se o nome do álbum não "
            "estiver escrito, responda album vazio. Não invente.\n\n"
            f"TÍTULO: {titulo}\n\nDESCRIÇÃO:\n{(descricao or '')[:2500]}\n\n"
            'Responda APENAS um JSON: {"artist": "...", "album": "...", "year": "AAAA ou vazio"}')
        d = self._json(self._perguntar('álbum', prompt, 150))
        if not isinstance(d, dict):
            return None
        alb = str(d.get('album') or '').strip()
        art = str(d.get('artist') or '').strip()
        if not alb or len(alb) > 100:
            return None
        # só vale se o álbum sugerido estiver mesmo escrito no título ou na descrição
        from nomes import normalizar_para_comparar as N
        if N(alb) not in N(f"{titulo}\n{descricao}"):
            self._reg('AVISO', f"Groq sugeriu o álbum '{alb}', que não está escrito no título nem na descrição - ignorado")
            return None
        ano = str(d.get('year') or '').strip()
        return {'artist': art, 'album': alb, 'year': ano if re.fullmatch(r'(19|20)\d{2}', ano) else ''}

    def escolher_faixa(self, titulo_video: str, oficiais: List[str], artista: str = '') -> Optional[int]:
        """Índice (0..n-1) da faixa oficial que é este vídeo, ou None."""
        if not oficiais:
            return None
        lista = '\n'.join(f"{i + 1}. {t}" for i, t in enumerate(oficiais))
        prompt = (
            f"Vídeo de uma playlist do álbum de {artista or 'um artista'}: \"{titulo_video}\".\n"
            f"Faixas oficiais do álbum:\n{lista}\n\n"
            "Qual faixa oficial é este vídeo? Considere nome do artista na frente, tradução, "
            "títulos com '=' (duas línguas) e '&' no lugar de 'e'. Se nenhuma, responda 0.\n"
            'Responda APENAS um JSON: {"faixa": N}')
        d = self._json(self._perguntar('faixa', prompt, 30))
        try:
            n = int((d or {}).get('faixa', 0))
        except Exception:
            return None
        return n - 1 if 1 <= n <= len(oficiais) else None

    def tracklist_da_descricao(self, descricao: str) -> Optional[List[str]]:
        """Títulos das faixas, NA ORDEM em que aparecem na descrição, ou None."""
        if not descricao or len(descricao) < 40:
            return None
        prompt = (
            "A descrição abaixo é de um vídeo do YouTube com um álbum completo. Se ela tiver a "
            "lista de faixas, devolva os títulos NA ORDEM em que aparecem (sem números, sem "
            "tempos). Se não tiver lista de faixas, devolva lista vazia. Não invente.\n\n"
            f"DESCRIÇÃO:\n{descricao[:3000]}\n\n"
            'Responda APENAS um JSON: {"faixas": ["...", "..."]}')
        d = self._json(self._perguntar('tracklist', prompt, 600))
        faixas = (d or {}).get('faixas') if isinstance(d, dict) else None
        if not isinstance(faixas, list):
            return None
        faixas = [str(f).strip() for f in faixas if str(f).strip()]
        return faixas or None

"""
Funções pequenas usadas em vários lugares: sanitize (nome de arquivo),
segundos_da_faixa (duração em qualquer formato que circula no programa) e
onde_quebrou (arquivo:linha de uma exceção, pro log).
"""
import os
import re


def sanitize(name: str) -> str:
    """Remove caracteres inválidos e limpa formatação"""
    # Remove caracteres inválidos
    clean = re.sub(r'[<>:"/\\|?*]', '', name)
    
    # MANTÉM espaço antes de parênteses para formato "Álbum (ano)"
    # clean = re.sub(r'\s+\(', '(', clean)  # ← COMENTADO para manter espaço
    
    # Remove parênteses duplicados: "( (" → "("
    clean = re.sub(r'\(\s*\(', '(', clean)
    
    # Remove múltiplos espaços: "  " → " "
    clean = re.sub(r'\s+', ' ', clean)
    
    return clean.strip()


def segundos_da_faixa(faixa) -> float:
    """
    Duração de uma faixa em segundos, aceitando qualquer formato que circula
    pelo programa: 'duration_seconds' (número exato), 'duration' como número
    (formato bruto do Discogs) ou como texto "M:SS" / "H:MM:SS" (formato já
    formatado pra exibição). Nunca levanta exceção - devolve 0 se não der.

    Existe porque o mesmo dicionário de faixas aparece nos dois formatos
    dependendo de onde veio, e somar/comparar sem converter derrubava o
    processamento do álbum inteiro ("int + str").
    """
    if not isinstance(faixa, dict):
        return 0.0
    exata = faixa.get('duration_seconds')
    if isinstance(exata, (int, float)) and exata > 0:
        return float(exata)
    valor = faixa.get('duration')
    if isinstance(valor, (int, float)):
        return float(valor) if valor > 0 else 0.0
    if isinstance(valor, str) and valor.strip():
        try:
            partes = [float(p) for p in valor.strip().split(':')]
            total = 0.0
            for p in partes:
                total = total * 60 + p
            return total if total > 0 else 0.0
        except ValueError:
            return 0.0
    return 0.0


def onde_quebrou(exc) -> str:
    """Arquivo:linha e função onde a exceção nasceu - vai pro log junto com
    a mensagem, pra um erro relatado pelo usuário já apontar o lugar."""
    import traceback
    try:
        quadro = traceback.extract_tb(exc.__traceback__)[-1]
        return f"{os.path.basename(quadro.filename)}:{quadro.lineno} em {quadro.name}"
    except Exception:
        return "local desconhecido"

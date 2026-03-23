"""
Receita Federal CNPJ Lookup Service
Uses BrasilAPI (free, no-auth) as the primary source.
"""
import re
import requests
from app.infrastructure.logger import logger

BRASILAPI_URL = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
TIMEOUT = 10  # seconds


def _clean_cnpj(cnpj: str) -> str:
    """Strip all non-digits from CNPJ string."""
    return re.sub(r'\D', '', cnpj or '')


def buscar_empresa_por_cnpj(cnpj: str) -> dict:
    """
    Queries BrasilAPI for CNPJ data, with fallback to ReceitaWS on rate limits.
    Returns a structured dict on success, or raises ValueError on not-found/invalid.
    """
    cnpj_limpo = _clean_cnpj(cnpj)

    if len(cnpj_limpo) != 14:
        raise ValueError("CNPJ inválido. Deve conter 14 dígitos.")

    url_brasilapi = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}"
    url_receitaws = f"https://receitaws.com.br/v1/cnpj/{cnpj_limpo}"

    data = None

    # Tenta BrasilAPI primeiro
    try:
        req = requests.get(url_brasilapi, timeout=TIMEOUT)
        if req.status_code == 200:
            data = req.json()
        elif req.status_code == 404:
            raise ValueError(f"CNPJ {cnpj} não encontrado na base da Receita Federal.")
    except Exception as e:
        if isinstance(e, ValueError): raise e
        logger.warning(f"BrasilAPI falhou para {cnpj_limpo}: {e}")

    # Fallback para ReceitaWS se BrasilAPI rate limted (429) ou falhou
    if not data:
        try:
            req = requests.get(url_receitaws, timeout=TIMEOUT)
            if req.status_code == 200:
                raw = req.json()
                if raw.get('status') == 'ERROR':
                    raise ValueError(raw.get('message', 'CNPJ rejeitado pela ReceitaWS.'))
                # Adapta payload ReceitaWS para o padrão esperado
                data = {
                    'razao_social': raw.get('nome', ''),
                    'nome_fantasia': raw.get('fantasia', '') or raw.get('nome', ''),
                    'descricao_situacao_cadastral': raw.get('situacao', 'Não informada'),
                    'cnae_fiscal_descricao': raw.get('atividade_principal', [{}])[0].get('text', ''),
                    'logradouro': raw.get('logradouro', ''),
                    'numero': raw.get('numero', ''),
                    'municipio': raw.get('municipio', ''),
                    'uf': raw.get('uf', ''),
                    'cep': raw.get('cep', ''),
                    'email': raw.get('email', ''),
                    'ddd_telefone_1': raw.get('telefone', ''),
                    'porte': raw.get('porte', '')
                }
            elif req.status_code == 429:
                raise ValueError("Os servidores gratuitos de Receita estão sobrecarregados (Muitas requisições). Tente novamente em 1 minuto.")
        except Exception as e:
            if isinstance(e, ValueError): raise e
            logger.error(f"ReceitaWS também falhou: {e}")

    if not data:
        raise ValueError("Não foi possível conectar com os servidores da Receita Federal no momento.")

    # Formata CNPJ para exibição
    cnpj_formatado = f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"

    # Monta endereço completo
    logradouro = data.get('logradouro', '')
    numero = data.get('numero', '')
    municipio = data.get('municipio', '')
    uf = data.get('uf', '')
    cep = data.get('cep', '')
    endereco = f"{logradouro}, {numero} — {municipio}/{uf} — CEP {cep}".strip(', ')

    return {
        'cnpj': cnpj_formatado,
        'cnpj_limpo': cnpj_limpo,
        'razao_social': data.get('razao_social', ''),
        'nome_fantasia': data.get('nome_fantasia', '') or data.get('razao_social', ''),
        'situacao': data.get('descricao_situacao_cadastral', 'Não informada'),
        'atividade_principal': data.get('cnae_fiscal_descricao', ''),
        'endereco': endereco,
        'email': data.get('email', ''),
        'telefone': data.get('ddd_telefone_1', ''),
        'porte': data.get('porte', ''),
    }

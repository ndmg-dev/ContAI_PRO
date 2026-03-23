"""
Excel Spreadsheet Parser
Reads accounting spreadsheets with standard columns:
  - data, descrição, num. documento, valor
Supports .xlsx and .xls formats.
"""
import io
import re
from datetime import datetime
from app.infrastructure.logger import logger

# Column name aliases (covers casing and punctuation variations)
COL_ALIASES = {
    'data': ['data', 'date', 'dt', 'data lançamento', 'dt lançamento'],
    'descricao': ['descrição', 'descricao', 'historico', 'histórico', 'descr', 'description', 'memo'],
    'num_doc': ['num. documento', 'num documento', 'numero documento', 'nro doc', 'doc', 'documento', 'número', 'num.doc'],
    'valor': ['valor', 'value', 'amount', 'vlr', 'vl', 'débito/crédito', 'debito/credito'],
}


def _normalize(text: str) -> str:
    """Lowercase + strip accents for column matching."""
    import unicodedata
    text = str(text).strip().lower()
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    return text


def _find_col(df_cols: list, aliases: list) -> str | None:
    """Returns the first matching column from the DataFrame."""
    for col in df_cols:
        normalized = _normalize(col)
        for alias in aliases:
            if normalized == alias or alias in normalized:
                return col
    return None


def _parse_valor(val) -> tuple[float, str]:
    """
    Parse monetary value. Returns (amount_as_float, tipo_dc).
    Negative = debito, Positive = credito.
    """
    if val is None:
        return 0.0, 'credito'
    val_str = str(val).replace('R$', '').replace(' ', '').replace('.', '').replace(',', '.')
    try:
        amount = float(val_str)
    except ValueError:
        amount = 0.0
    tipo = 'debito' if amount < 0 else 'credito'
    return abs(amount), tipo


def _parse_date(val) -> str | None:
    """Tries to parse a date value into YYYY-MM-DD string."""
    if val is None or str(val).lower() == 'nan':
        return None
    val_str = str(val).strip()
    if not val_str: return None
    
    # Se for datetime do pandas/timestamp: '2025-12-12 00:00:00'
    if ' ' in val_str:
        val_str = val_str.split(' ')[0]
    
    # Padroniza separadores para facilitar o matching
    val_str = val_str.replace('.', '/').replace('-', '/')

    for fmt in ('%Y/%m/%d', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d'):
        try:
            return datetime.strptime(val_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    
    logger.warning(f"[Excel Parser] Falha ao converter data: {val_str}")
    return None


import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

def _get_dynamic_mapping(df_sample, cols) -> dict:
    """Uses OpenAI LLM to infer the correct column names based on headers and sample data."""
    api_key = os.environ.get('OPENAI_API_KEY', '').strip().strip('"').strip("'")
    
    # Fallback to heuristics if no API key
    if not api_key:
        logger.warning("OPENAI_API_KEY ausente. Usando heurística padrão para colunas.")
        return _fallback_mapping(cols)

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
        
        system_prompt = """Você é um especialista em análise de engenharia de dados contábeis.
Sua missão é mapear as colunas de uma planilha enviada pelo cliente para o layout padrão do sistema.

O sistema precisa identificar *exatamente* qual coluna da planilha corresponde a:
1. "data" (contém a data da transação)
2. "descricao" (o histórico, nome do fornecedor ou detalhe do gasto)
3. "valor" (o montante da transação, débito ou crédito)
4. "num_doc" (número do documento, comprovante, id da transação - opcional)

Retorne APENAS um JSON válido contendo o nome EXATO da coluna na planilha.
Exemplo:
{"data": "Data Lançamento", "descricao": "Histórico", "valor": "Débito/Crédito", "num_doc": "Doc."}

Se uma coluna opcional não existir (ex: num_doc), retorne null para ela.
MUITO IMPORTANTE: Não invente nomes. Use EXATAMENTE os nomes contidos na lista de colunas recebidas."""

        human_prompt = f"""
COLUNAS DISPONÍVEIS:
{cols}

AMOSTRA DE DADOS (3 primeiras linhas):
{df_sample.to_dict(orient='records')}

Responda APENAS com o JSON do mapeamento.
"""
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt)
        ])
        
        # Parse the JSON from the LLM response
        content = response.content.strip()
        if content.startswith('```json'):
            content = content.replace('```json', '').replace('```', '')
        elif content.startswith('```'):
            content = content.replace('```', '')
            
        mapping = json.loads(content.strip())
        logger.info(f"[Excel Parser] LLM Mapeou as colunas: {mapping}")
        return mapping

    except Exception as e:
        logger.error(f"[Excel Parser] Falha ao invocar LLM para mapeamento dinâmico: {e}. Usando fallback.")
        return _fallback_mapping(cols)


def _fallback_mapping(cols) -> dict:
    """Standard hardcoded aliases for fallback if LLM is offline."""
    aliases = {
        'data': ['data', 'date', 'dt', 'lançamento'],
        'descricao': ['descrição', 'descricao', 'historico', 'histórico', 'memo'],
        'num_doc': ['num', 'documento', 'doc', 'número'],
        'valor': ['valor', 'value', 'amount', 'vlr', 'vl', 'débito', 'crédito'],
    }
    mapping = {'data': None, 'descricao': None, 'num_doc': None, 'valor': None}
    
    for key, alist in aliases.items():
        for col in cols:
            norm = _normalize(col)
            if any(a in norm for a in alist):
                mapping[key] = col
                break
    return mapping


def parse_excel(content: bytes) -> dict:
    """
    Main entry point. Uses dynamic AI column mapping.
    Returns {'transactions': [...], 'error': str|None}
    """
    try:
        import openpyxl  # noqa: F401
        import pandas as pd
    except ImportError:
        return {'transactions': [], 'error': 'Dependência ausente: instale openpyxl e pandas.'}

    try:
        # Pula as primeiras linhas que costumam ser cabeçalhos inúteis em extratos bancários brutos
        # Tenta achar a 'verdadeira' linha de cabeçalho.
        # Por robustez, vamos ler o arquivo inteiro cru e depois limpar as linhas com NaN pesado.
        df_raw = pd.read_excel(io.BytesIO(content), header=None, dtype=str)
        
        # Heurística: a linha com o maior número de células preenchidas é provável ser o cabeçalho
        valid_counts = df_raw.notna().sum(axis=1)
        header_idx = valid_counts.idxmax()
        
        # Lê o dataframe real a partir dessa linha
        df = pd.read_excel(io.BytesIO(content), header=header_idx, dtype=str)
        # Dropa colunas vazias
        df = df.dropna(axis=1, how='all')
        
    except Exception as e:
        return {'transactions': [], 'error': f'Erro ao ler planilha: {e}'}

    if df.empty:
        return {'transactions': [], 'error': 'Planilha vazia ou sem dados legíveis.'}

    cols = list(df.columns)
    
    # 1. Pede para a IA mapear as colunas
    mapping = _get_dynamic_mapping(df.head(3), cols)

    col_data = mapping.get('data')
    col_valor = mapping.get('valor')
    col_descr = mapping.get('descricao')
    col_num_doc = mapping.get('num_doc')

    if not col_data or col_data not in df.columns or not col_valor or col_valor not in df.columns:
        return {
            'transactions': [],
            'error': (
                f'O motor de IA não encontrou colunas suficientes de Data e Valor. '
                f'Colunas detectadas: {cols}. Mapeamento tentado: {mapping}'
            )
        }

    transactions = []
    for _, row in df.iterrows():
        data_str = _parse_date(row.get(col_data))
        if not data_str:
            continue  # Skip rows without a valid date

        valor_raw = row.get(col_valor)
        if pd.isna(valor_raw):
            continue
            
        amount, tipo_dc = _parse_valor(valor_raw)

        if amount == 0:
            # Caso o extrato tenha colunas separadas para debito e credito
            pass

        historico = str(row.get(col_descr, '')).strip() if (col_descr and not pd.isna(row.get(col_descr))) else 'Importado via Planilha'
        num_doc = str(row.get(col_num_doc, '')).strip() if (col_num_doc and not pd.isna(row.get(col_num_doc))) else ''

        txn = {
            'data_lancamento': data_str,
            'historico': historico,
            'valor': amount,
            'tipo_dc': tipo_dc,
            'origem': 'Excel',
            'status': 'pendente',
            'transacao_origem_id': num_doc or None,
        }
        transactions.append(txn)

    logger.info(f"[Excel Parser] {len(transactions)} transações extraídas usando IA dinâmica.")
    return {'transactions': transactions, 'error': None}

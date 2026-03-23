"""
CSV Import Service
Uses pandas to parse bank statement CSVs with smart column mapping.
"""
import pandas as pd
import io
import re
from typing import List, Dict, Any

def parse_csv(content: bytes | str) -> Dict[str, Any]:
    """
    Parse CSV content and return a dict with 'transactions' and 'metadata'.
    """
    if isinstance(content, bytes):
        try:
            text = content.decode('utf-8')
        except UnicodeDecodeError:
            text = content.decode('latin-1', errors='ignore')
    else:
        text = content

    # Detect separator (common: ; or ,)
    # Simple heuristic: count occurrences in first line
    first_line = text.split('\n')[0]
    sep = ';' if first_line.count(';') > first_line.count(',') else ','

    try:
        df = pd.read_csv(io.StringIO(text), sep=sep)
    except Exception as e:
        return {'transactions': [], 'error': f'Erro ao ler CSV: {e}'}

    if df.empty:
        return {'transactions': [], 'metadata': {}}

    # Column Mapping Heuristics
    cols = [c.lower() for c in df.columns]
    
    mapping = {
        'date': next((c for c in df.columns if any(k in c.lower() for k in ['data', 'date', 'venc', 'pag'])), None),
        'memo': next((c for c in df.columns if any(k in c.lower() for k in ['hist', 'descr', 'memo', 'detalhe'])), None),
        'value': next((c for c in df.columns if any(k in c.lower() for k in ['valor', 'amount', 'total', 'quant'])), None),
    }

    transactions = []
    for _, row in df.iterrows():
        try:
            # 1. Date
            date_val = str(row[mapping['date']]) if mapping['date'] else None
            # Basic normalization (convert DD/MM/YYYY to YYYY-MM-DD)
            if date_val and '/' in date_val:
                parts = date_val.split('/')
                if len(parts) == 3:
                    if len(parts[2]) == 4: # DD/MM/YYYY
                        date_val = f"{parts[2]}-{parts[1]}-{parts[0]}"
                    elif len(parts[0]) == 4: # YYYY/MM/DD
                        date_val = f"{parts[0]}-{parts[1]}-{parts[2]}"

            # 2. Value
            raw_val = str(row[mapping['value']]) if mapping['value'] else "0"
            # Standardize decimal separator
            clean_val = raw_val.replace('.', '').replace(',', '.')
            amount = float(re.sub(r'[^\d.-]', '', clean_val)) if clean_val else 0.0

            # 3. Memo
            memo = str(row[mapping['memo']]) if mapping['memo'] else "Transação CSV"

            # 4. Type (D/C)
            tipo_dc = 'credito' if amount > 0 else 'debito'

            transactions.append({
                'transacao_origem_id': None, # CSVs usually don't have fitid
                'data_lancamento': date_val[:10] if date_val else None,
                'historico': memo.strip(),
                'valor': abs(amount),
                'tipo_dc': tipo_dc,
                'origem': 'CSV',
                'status': 'pendente',
            })
        except Exception:
            continue

    return {
        'transactions': transactions,
        'metadata': {
            'format': 'csv',
            'columns': list(df.columns)
        }
    }

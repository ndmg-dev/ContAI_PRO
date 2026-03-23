"""
Domínio Systems Integration Service
Handles parsing of Domínio's "Lançamentos com Separador" layout.
"""
import csv
import io
from datetime import datetime
from typing import List, Dict, Any
from app.infrastructure.logger import logger

def parse_dominio_layout(content: bytes | str) -> List[Dict[str, Any]]:
    """
    Parses Domínio's standard TXT/CSV layout with separators (usually semicolon).
    Expected fields: Date, Debit Account, Credit Account, Value, History Code, Complement.
    """
    if isinstance(content, bytes):
        try:
            text = content.decode('utf-8')
        except Exception:
            text = content.decode('latin-1', errors='ignore')
    else:
        text = content

    # Domínio layouts often use semicolon as separator
    # We'll try to sniff or default to semicolon
    dialect = ';' if ';' in text else ','
    
    entries = []
    # Use io.StringIO to treat the string as a file
    f = io.StringIO(text)
    reader = csv.reader(f, delimiter=dialect)

    for row in reader:
        if not row or len(row) < 4:
            continue
            
        # Basic mapping (this varies by Domínio configuration, but this is the "Standard" layout)
        # 0: Data (DD/MM/YYYY)
        # 1: Conta Débito
        # 2: Conta Crédito
        # 3: Valor
        # 4: Cód Histórico (Optional)
        # 5: Complemento (Optional)
        
        try:
            data_str = row[0].strip()
            # Try multiple date formats common in Brazil
            for fmt in ('%d/%m/%Y', '%d%m%Y', '%Y-%m-%d'):
                try:
                    dt = datetime.strptime(data_str, fmt).date()
                    break
                except ValueError:
                    continue
            else:
                logger.warning(f"[Domínio Parser] Data inválida: {data_str}")
                continue

            valor_str = row[3].replace('.', '').replace(',', '.')
            valor = abs(float(valor_str))
            
            conta_debito = row[1].strip()
            conta_credito = row[2].strip()
            historico = ""
            if len(row) > 4:
                historico = f"Hist: {row[4]}"
            if len(row) > 5:
                historico += f" - {row[5]}"
            
            # Incorporate accounts into historico to avoid schema changes
            full_hist = f"{historico} (D:{conta_debito} C:{conta_credito})".strip()

            # A Domínio entry often represents two "ContAI" lancamentos (or one double entry)
            # For reconciliation, we might want to store both sides or a simplified version.
            # Here we create a single "Documento" representation for matching.
            entries.append({
                'data_lancamento': str(dt),
                'valor': valor,
                'historico': full_hist or f"Lançamento Domínio {conta_debito}/{conta_credito}",
                'tipo_dc': 'debito' # Simplified for the first pass
            })
        except Exception as e:
            logger.error(f"[Domínio Parser] Erro na linha {row}: {e}")
            continue

    return entries

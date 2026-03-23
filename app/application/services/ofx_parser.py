"""
OFX Import Service
Parses OFX bank statement files and extracts transactions into lancamentos.
"""
import re
from datetime import datetime
from typing import List, Dict, Any


def parse_ofx(content: bytes | str) -> Dict[str, Any]:
    """
    Parse OFX file content and return a dict with 'transactions' and 'metadata'.
    """
    if isinstance(content, bytes):
        try:
            text = content.decode('utf-8')
        except Exception:
            text = content.decode('latin-1', errors='ignore')
    else:
        text = content

    # Metadata extraction (Header info)
    def extract_header(tag: str) -> str:
        match = re.search(rf'<{tag}>\s*([^\r\n<]+)', text, re.IGNORECASE)
        return match.group(1).strip() if match else ''

    org_name = extract_header('ORG')
    fid = extract_header('FID')

    transactions = []

    # Find all <STMTTRN> blocks (SGML or XML OFX)
    blocks = re.findall(r'<STMTTRN>(.*?)</STMTTRN>', text, re.DOTALL | re.IGNORECASE)

    for block in blocks:
        def extract(tag: str) -> str:
            match = re.search(rf'<{tag}>\s*([^\r\n<]+)', block, re.IGNORECASE)
            return match.group(1).strip() if match else ''

        trntype = extract('TRNTYPE')
        dtposted = extract('DTPOSTED')
        trnamt_raw = extract('TRNAMT')
        fitid = extract('FITID')
        memo = extract('MEMO') or extract('NAME')

        # Parse date: YYYYMMDDHHMMSS or YYYYMMDD
        try:
            date_str = dtposted[:8]
            parsed_date = datetime.strptime(date_str, '%Y%m%d').date()
        except Exception:
            parsed_date = None

        # Parse amount
        try:
            amount = float(trnamt_raw.replace(',', '.'))
        except Exception:
            continue

        # Determine D/C
        tipo_dc = 'credito' if amount > 0 else 'debito'

        transactions.append({
            'transacao_origem_id': fitid,
            'data_lancamento': str(parsed_date) if parsed_date else None,
            'historico': _normalize_text(memo),
            'valor': abs(amount),
            'tipo_dc': tipo_dc,
            'origem': 'OFX',
            'status': 'pendente',
        })

    return {
        'transactions': transactions,
        'metadata': {
            'org_name': org_name,
            'fid': fid
        }
    }


def _normalize_text(text: str) -> str:
    """Remove special characters and normalize whitespace."""
    if not text:
        return ''
    # Remove multiple spaces and strip
    normalized = re.sub(r'\s+', ' ', text)
    # Remove special chars except accents
    normalized = re.sub(r'[^\w\s\-./àáâãéêíóôõúüçÀÁÂÃÉÊÍÓÔÕÚÜÇ]', '', normalized)
    return normalized.strip()

"""
NF-e XML Import Service
Parses Brazilian NF-e (Nota Fiscal Eletrônica) XML files
and extracts key fiscal data into a structured dict.
"""
import re
from typing import Dict, Any
try:
    import xml.etree.ElementTree as ET
except ImportError:
    ET = None

# NF-e namespace
NFE_NS = 'http://www.portalfiscal.inf.br/nfe'
NFS_NS = ''  # NFS-e varies by municipality


def parse_nfe_xml(content: bytes | str) -> Dict[str, Any]:
    """Parse NF-e XML and return fiscal data."""
    if isinstance(content, bytes):
        try:
            text = content.decode('utf-8')
        except Exception:
            text = content.decode('latin-1')
    else:
        text = content

    # Strip XML declaration if present
    text = text.strip()

    try:
        root = ET.fromstring(text)
    except Exception as e:
        return {'erro': f'XML inválido: {e}'}

    def find(node, path: str):
        """Find with or without namespace."""
        result = node.find(f'{{{NFE_NS}}}{path}')
        if result is None:
            result = node.find(path)
        return result

    def findtext(node, path: str, default='') -> str:
        el = find(node, path)
        return (el.text or '').strip() if el is not None else default

    def findall(node, path: str):
        result = node.findall(f'{{{NFE_NS}}}{path}')
        if not result:
            result = node.findall(path)
        return result

    # Navigate to infNFe
    inf_nfe = root.find(f'.//{{{NFE_NS}}}infNFe') or root.find('.//infNFe')
    if inf_nfe is None:
        return {'erro': 'Estrutura NF-e não reconhecida'}

    # Emitente
    emit = find(inf_nfe, 'emit')
    cnpj_emitente = findtext(emit, 'CNPJ') if emit is not None else ''
    nome_emitente = findtext(emit, 'xNome') if emit is not None else ''

    # Identificação
    ide = find(inf_nfe, 'ide')
    numero_nfe = findtext(ide, 'nNF') if ide is not None else ''
    data_emissao = findtext(ide, 'dhEmi') or findtext(ide, 'dEmi')
    # Parse date
    if 'T' in data_emissao:
        data_emissao = data_emissao[:10]

    # Totais
    total = find(inf_nfe, 'total')
    icms_tot = find(total, 'ICMSTot') if total is not None else None
    valor_nf = findtext(icms_tot, 'vNF') if icms_tot is not None else ''
    valor_bc = findtext(icms_tot, 'vBC') if icms_tot is not None else ''

    # Retencoes (COFINS, PIS, CSLL, IRRF, INSS)
    retencoes = {}
    ret_node = find(inf_nfe, 'total/retTrib') or (find(inf_nfe, 'total') and find(find(inf_nfe, 'total'), 'retTrib'))
    if ret_node is not None:
        for tag in ['vRetPIS', 'vRetCOFINS', 'vRetCSLL', 'vIRRF', 'vRetINSS', 'vISSRet']:
            val = findtext(ret_node, tag)
            if val:
                retencoes[tag] = float(val.replace(',', '.'))

    # Itens (first item description)
    itens = []
    for det in findall(inf_nfe, 'det'):
        prod = find(det, 'prod')
        if prod is not None:
            itens.append({
                'descricao': findtext(prod, 'xProd'),
                'codigo': findtext(prod, 'cProd'),
                'ncm': findtext(prod, 'NCM'),
                'valor_unitario': findtext(prod, 'vUnTrib'),
                'valor_total': findtext(prod, 'vProd'),
            })

    return {
        'numero_nfe': numero_nfe,
        'data_emissao': data_emissao,
        'cnpj_emitente': _format_cnpj(cnpj_emitente),
        'nome_emitente': nome_emitente,
        'valor_nf': _to_float(valor_nf),
        'valor_bc': _to_float(valor_bc),
        'retencoes': retencoes,
        'itens': itens,
        'tipo_documento': 'nfe',
        'origem': 'XML',
        'status': 'pendente',
    }


def _format_cnpj(cnpj: str) -> str:
    digits = re.sub(r'\D', '', cnpj)
    if len(digits) == 14:
        return f"{digits[:2]}.{digits[2:5]}.{digits[5:8]}/{digits[8:12]}-{digits[12:]}"
    return cnpj


def _to_float(value: str) -> float:
    try:
        return float(value.replace(',', '.'))
    except Exception:
        return 0.0

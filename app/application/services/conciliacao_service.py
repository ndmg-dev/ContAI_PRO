"""
Conciliation Service — Motor de Conciliação Bancária
=====================================================

Lógica REAL de conciliação:

1. Pegamos todos os lançamentos do LADO BANCÁRIO (origem: Excel, OFX)
2. Pegamos todos os lançamentos do LADO DOCUMENTAL (origem: PDF, XML)
3. Para cada linha bancária tentamos encontrar uma linha documental que satisfaça:
   - Valor próximo (dentro de 5% de tolerância para taxas/descontos)
   - Data próxima (dentro de 5 dias — cobertura para feriados e processos)
4. Se encontrou par válido → status 'conciliado', com score de assertividade
5. Se NÃO encontrou par (data ou valor muito diferente) → status 'excecao', sem par exibido
6. Um lançamento documental só pode ser pareado com UM lançamento bancário (pool 1-to-1)
"""

import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from app.infrastructure.logger import logger


# ─────────────────────────────── Helpers ───────────────────────────────────

def _parse_date(val: str) -> Optional[datetime]:
    if not val:
        return None
    try:
        return datetime.strptime(str(val)[:10], '%Y-%m-%d')
    except Exception:
        return None


def _parse_valor(val) -> float:
    try:
        return abs(float(val or 0))
    except (ValueError, TypeError):
        return 0.0


def _valor_compativel(a: float, b: float, tolerancia: float = 0.05) -> bool:
    """
    Retorna True se os valores são próximos o suficiente para serem o mesmo lançamento.
    tolerância padrão de 5% cobre: taxas de maquininha, tarifas e arredondamentos.
    """
    if a == 0 or b == 0:
        return False
    diff = abs(a - b) / max(a, b)
    return diff <= tolerancia


def _data_compativel(da: Optional[datetime], db: Optional[datetime], janela_dias: int = 5) -> bool:
    """
    Retorna True se as datas estão dentro da janela admissível.
    Janela padrão de 5 dias cobre feriados, D+1, processamentos tardios.
    """
    if da is None or db is None:
        return False
    return abs((da - db).days) <= janela_dias


def _score_match(banc_valor: float, doc_valor: float,
                 banc_data: Optional[datetime], doc_data: Optional[datetime]) -> float:
    """
    Score de assertividade do par (0.0 → 1.0).

    Composição:
      - 60% baseado no valor  (diferença percentual)
      - 40% baseado na data   (diferença em dias)

    Só executa se já validamos compatibilidade prévia.
    """
    # Score de valor (quanto mais próximo, melhor)
    if banc_valor > 0 and doc_valor > 0:
        diff_pct = abs(banc_valor - doc_valor) / max(banc_valor, doc_valor)
        valor_score = max(0.0, 1.0 - diff_pct * 5)  # 1% diff → 0.95 score
    else:
        valor_score = 0.0

    # Score de data (0 dias → 1.0, 1-2 dias → ≥ 0.85, até 5 dias → decaindo)
    if banc_data and doc_data:
        delta = abs((banc_data - doc_data).days)
        date_score = max(0.0, 1.0 - delta * 0.15)
    else:
        date_score = 0.0

    return round((valor_score * 0.60) + (date_score * 0.40), 3)


# ─────────────────────────────── Engine Principal ──────────────────────────

def run_conciliation(
    bancarios: List[Dict],
    documentais: List[Dict],
    threshold: float = 0.70,
    tolerancia_valor: float = 0.05,
    janela_dias: int = 5,
) -> List[Dict[str, Any]]:
    """
    Cruza lançamentos bancários (Excel/OFX) com lançamentos documentais (PDF/XML).

    Retorna lista de dicionários com:
      - lancamento_ofx    : o lançamento bancário (lado esquerdo na UI)
      - lancamento_pdf    : o match documental encontrado (ou None se falhou)
      - score             : assertividade do par (0.0 → 1.0)
      - status            : 'conciliado' | 'excecao'
      - lancamento_id     : ID do bancário para ação de workflow
    """
    logger.info(
        f"[Conciliação] Iniciando cruzamento: {len(bancarios)} lançamentos bancários × "
        f"{len(documentais)} lançamentos documentais."
    )

    # Pool de documentais disponíveis para pareamento (1-to-1)
    pool = list(documentais)  # cópia

    results = []

    for banc in bancarios:
        banc_valor = _parse_valor(banc.get('valor'))
        banc_data  = _parse_date(banc.get('data_lancamento'))

        best_score = 0.0
        best_doc   = None
        best_idx   = -1

        for idx, doc in enumerate(pool):
            doc_valor = _parse_valor(doc.get('valor'))
            doc_data  = _parse_date(doc.get('data_lancamento'))

            # Gate duplo: valor E data precisam ser compatíveis
            if not _valor_compativel(banc_valor, doc_valor, tolerancia_valor):
                continue
            if not _data_compativel(banc_data, doc_data, janela_dias):
                continue

            # Se passou nos dois gates, calcula score de assertividade
            score = _score_match(banc_valor, doc_valor, banc_data, doc_data)

            if score > best_score:
                best_score = score
                best_doc   = doc
                best_idx   = idx

        # Apenas considera match se score atingiu o threshold mínimo
        if best_score < threshold:
            best_doc = None
            best_score = 0.0
        elif best_idx >= 0:
            # Consome o documental do pool para evitar double-match
            pool.pop(best_idx)

        status = 'conciliado' if best_doc is not None else 'excecao'

        results.append({
            'lancamento_id'  : banc.get('id'),
            'lancamento_ofx' : banc,
            'lancamento_pdf' : best_doc,
            'score'          : best_score,
            'status'         : status,
        })

    conciliados = sum(1 for r in results if r['status'] == 'conciliado')
    excecoes    = len(results) - conciliados
    logger.info(
        f"[Conciliação] Resultado: {conciliados} conciliados, {excecoes} exceções "
        f"de {len(results)} lançamentos bancários."
    )
    return results


# ─────────────────────────────── Relatório ─────────────────────────────────

def generate_report(results: List[Dict]) -> Dict:
    """
    Gera relatório resumido da conciliação.
    """
    total        = len(results)
    conciliados  = [r for r in results if r['status'] == 'conciliado']
    excecoes     = [r for r in results if r['status'] == 'excecao']

    total_bancario    = sum(_parse_valor(r['lancamento_ofx'].get('valor')) for r in results)
    total_conciliado  = sum(_parse_valor(r['lancamento_ofx'].get('valor')) for r in conciliados)

    return {
        'total_lancamentos' : total,
        'conciliados'       : len(conciliados),
        'excecoes'          : len(excecoes),
        'taxa_conciliacao'  : round((len(conciliados) / total * 100) if total else 0, 1),
        'valor_total_ofx'   : round(total_bancario, 2),
        'valor_conciliado'  : round(total_conciliado, 2),
        'valor_pendente'    : round(total_bancario - total_conciliado, 2),
        'total_matches'     : len(conciliados),
        'detalhes'          : results,
    }


# ─────────────────────────────── Utilitários ───────────────────────────────

def deduplicate_by_fitid(
    new_transactions: List[Dict],
    existing_fitids: set,
) -> Tuple[List[Dict], int]:
    """
    Remove transactions already imported (by Transaction ID).
    Returns (unique_transactions, skipped_count).
    """
    unique  = []
    skipped = 0
    for t in new_transactions:
        fitid = t.get('transacao_origem_id', '')
        if fitid and fitid in existing_fitids:
            skipped += 1
        else:
            unique.append(t)
    return unique, skipped

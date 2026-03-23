from app.infrastructure.logger import logger

def apply_classification_rules(client, transactions: list[dict], empresa_id: str) -> list[dict]:
    """
    Applies the classification rules defined by the user to automatically assign
    a 'conta_contabil_id' to matching transactions.
    
    Args:
        client: Supabase client instance
        transactions: List of transaction dictionaries BEFORE being inserted into DB.
        empresa_id: The ID of the company.
    
    Returns:
        The updated list of transactions with 'conta_contabil_id' assigned if matched.
    """
    if not transactions or not empresa_id:
        return transactions

    regras = []
    try:
        resp = client.table('regras_classificacao') \
                     .select('*') \
                     .eq('empresa_id', empresa_id) \
                     .order('prioridade', desc=True) \
                     .execute()
                     
        regras = resp.data or []
    except Exception as e:
        logger.error(f"[Regras Service] Erro ao carregar regras: {e}")

    # Aplica regras a cada transação
    matched_count = 0
    for txn in transactions:
        historico = txn.get('historico', '').upper()
        
        for r in regras:
            padrao = r['padrao'].upper()
            
            match_found = False
            if r['tipo_regra'] in ['TEXTO_LIVRE', 'FORNECEDOR', 'BANCO']:
                if padrao in historico:
                    match_found = True
            
            if match_found:
                txn['conta_contabil_id'] = r['conta_id']
                matched_count += 1
                break

    if matched_count > 0:
        logger.info(f"[Regras Service] {matched_count} transações classificadas via regras manuais!")

    # --- FALLBACK PARA INTELIGÊNCIA ARTIFICIAL (BATCH) ---
    unmapped = [t for t in transactions if not t.get('conta_contabil_id')]
    
    if unmapped:
        try:
            # 1. Busca plano de contas para a empresa ativa
            resp_pc = client.table('plano_contas').select('*').eq('empresa_id', empresa_id).execute()
            plano = resp_pc.data or []
            
            if plano:
                logger.info(f"[Regras Service] Invocando AI Batch Classification para {len(unmapped)} transações órfãs...")
                from app.infrastructure.ai.services import batch_suggest_classification
                
                # Para garantir pareamento exato, injetamos um id provisório nas transações
                import uuid
                for t in unmapped:
                    if '_ai_id' not in t:
                        t['_ai_id'] = str(uuid.uuid4())
                
                # Prepara lote com id modificado
                batch_txns = []
                for t in unmapped:
                    batch_txns.append({
                        'id': t['_ai_id'],
                        'historico': t.get('historico'),
                        'valor': t.get('valor'),
                        'tipo_dc': t.get('tipo_dc')
                    })
                
                ai_mapping = batch_suggest_classification(batch_txns, plano)
                
                ai_matched = 0
                for t in unmapped:
                    ai_conta_id = ai_mapping.get(t['_ai_id'])
                    if ai_conta_id:
                        t['conta_contabil_id'] = ai_conta_id
                        ai_matched += 1
                    # Remove id provisório
                    t.pop('_ai_id', None)
                
                logger.info(f"[Regras Service] IA classificou {ai_matched} de {len(unmapped)} transações órfãs!")
            else:
                logger.debug(f"[Regras Service] Empresa {empresa_id} não possui Plano de Contas. Ignorando AI Fallback.")
        except Exception as ai_err:
            logger.error(f"[Regras Service] Erro ao aplicar AI Fallback: {ai_err}")

    return transactions

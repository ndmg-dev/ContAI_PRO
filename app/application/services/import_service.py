"""
Import Orchestrator
Main entry point for document ingestion pipeline.
Coordinates: storage upload → parsing → dedup → DB insert → workflow init.
"""
import re
from app.infrastructure.supabase.client import db_adapter
from app.application.services.ofx_parser import parse_ofx
from app.application.services.nfe_parser import parse_nfe_xml
from app.application.services.pdf_parser import parse_pdf_transactions
from app.application.services.conciliacao_service import deduplicate_by_fitid
from app.infrastructure.logger import logger
from app.application.services.csv_parser import parse_csv
from app.application.services.dominio_service import parse_dominio_layout
from app.application.services.regras_service import apply_classification_rules


def _get_client():
    client = db_adapter.get_client()
    if not client:
        raise RuntimeError("Supabase não configurado. Verifique SUPABASE_URL e SUPABASE_KEY.")
    return client


def _ensure_empresa(name: str, client, cnpj: str = None) -> str:
    """Busca empresa pelo nome/cnpj ou cria uma nova se não existir.
    Garante que o ID retornado EXISTE no banco (double-check após insert)."""
    if not name:
        return None
    
    name = name.strip()
    logger.debug(f"_ensure_empresa: Processando '{name}' (CNPJ: {cnpj})")
    try:
        # 1. Tenta buscar por CNPJ primeiro se fornecido
        if cnpj:
            resp_cnpj = client.table('empresas').select('id').eq('cnpj', cnpj).execute()
            if resp_cnpj.data:
                eid = resp_cnpj.data[0]['id']
                logger.debug(f"_ensure_empresa: Encontrada por CNPJ! ID={eid}")
                return eid

        # 2. Busca por nome (ignore case)
        resp = client.table('empresas').select('id').ilike('nome', name).execute()
        if resp.data:
            eid = resp.data[0]['id']
            logger.debug(f"_ensure_empresa: Encontrada por Nome! ID={eid}")
            return eid
        
        # 3. Cria se não existir
        logger.info(f"_ensure_empresa: '{name}' não encontrada. Criando...")
        payload = {'nome': name}
        if cnpj:
            payload['cnpj'] = cnpj
        
        insert_resp = client.table('empresas').insert(payload).execute()
        if insert_resp.data:
            eid = insert_resp.data[0]['id']
            logger.info(f"_ensure_empresa: Criada com ID={eid}. Fazendo double-check...")
            
            # DOUBLE-CHECK: Verifica se o ID realmente existe após o insert
            verify = client.table('empresas').select('id').eq('id', eid).execute()
            if verify.data:
                logger.info(f"_ensure_empresa: Double-check OK. ID={eid} confirmado no banco.")
                return eid
            else:
                logger.error(f"_ensure_empresa: FALHA no double-check! ID={eid} não encontrado após insert. Possível problema de RLS.")
                return None
        else:
            logger.error(f"_ensure_empresa: Insert não retornou dados para '{name}'. Resposta: {insert_resp}")
            return None
            
    except Exception as e:
        logger.error(f"[Import Service] Erro ao assegurar empresa '{name}': {e}")
        raise RuntimeError(f"Falha ao consultar ou criar empresa '{name}': {str(e)}")
    
    return None


def _validate_empresa_id(empresa_id: str, client) -> bool:
    """Verifica se o empresa_id realmente existe na tabela empresas."""
    if not empresa_id:
        return False
    try:
        resp = client.table('empresas').select('id').eq('id', empresa_id).execute()
        return bool(resp.data)
    except Exception:
        return False


def import_ofx(content: bytes, filename: str, storage_path: str, empresa_id: str = None) -> dict:
    """
    Full OFX import pipeline with Auto-Registration.
    """
    client = _get_client()

    # Parse
    ofx_data = parse_ofx(content)
    transactions = ofx_data.get('transactions', [])
    metadata = ofx_data.get('metadata', {})
    
    org_name = metadata.get('org_name')
    logger.debug(f"import_ofx: org_name={org_name}, txns={len(transactions)}")

    if not transactions:
        return {'status': 'erro', 'mensagem': 'Nenhuma transação encontrada no arquivo OFX.', 'inseridos': 0}

    # Validate empresa_id — if stale/ghost, fall back to auto-registration
    if empresa_id and not _validate_empresa_id(empresa_id, client):
        logger.warning(f"[Import OFX] empresa_id '{empresa_id}' não existe no banco. Fazendo auto-registro...")
        empresa_id = None

    if not empresa_id:
        if not org_name:
            return {'status': 'erro', 'mensagem': f'Não foi possível identificar a empresa no conteúdo do arquivo "{filename}". Selecione uma empresa antes de importar.', 'inseridos': 0}
        
        try:
            empresa_id = _ensure_empresa(org_name, client)
        except RuntimeError as e:
            return {'status': 'erro', 'mensagem': str(e), 'inseridos': 0}

    # Fetch existing transaction IDs (dedup check)
    try:
        existing_query = (
            client.table('lancamentos')
            .select('transacao_origem_id')
            .not_.is_('transacao_origem_id', 'null')
            .eq('empresa_id', empresa_id)
        )
        existing_resp = existing_query.execute()
        existing_fitids = {r['transacao_origem_id'] for r in (existing_resp.data or [])}
    except Exception:
        existing_fitids = set()

    unique_txns, skipped = deduplicate_by_fitid(transactions, existing_fitids)

    # Apply classification rules
    unique_txns = apply_classification_rules(client, unique_txns, empresa_id)

    # Insert unique transactions
    inserted = 0
    for txn in unique_txns:
        txn['empresa_id'] = empresa_id
        try:
            client.table('lancamentos').insert(txn).execute()
            inserted += 1
        except Exception as e:
            logger.exception(f"[Import OFX] erro ao inserir transação: {e}")

    return {
        'status': 'ok',
        'arquivo': filename,
        'total_encontrados': len(transactions),
        'inseridos': inserted,
        'duplicados_ignorados': skipped,
        'empresa_id': empresa_id,
        'empresa_nome': org_name or (filename.split('.')[0] if empresa_id else None)
    }


def import_nfe(content: bytes, filename: str, storage_path: str, empresa_id: str = None) -> dict:
    """
    Full NF-e import pipeline with Auto-Registration.
    """
    client = _get_client()

    fiscal_data = parse_nfe_xml(content)

    if 'erro' in fiscal_data:
        return {'status': 'erro', 'mensagem': fiscal_data['erro']}

    # Auto-Registration if empresa_id is missing
    emitente_nome = fiscal_data.get('nome_emitente')
    cnpj_emitente = fiscal_data.get('cnpj_emitente')
    logger.debug(f"import_nfe: emitente_nome={emitente_nome}, cnpj={cnpj_emitente}")
    
    if not empresa_id and emitente_nome:
        try:
            empresa_id = _ensure_empresa(emitente_nome, client, cnpj=cnpj_emitente)
        except RuntimeError as e:
            return {'status': 'erro', 'mensagem': str(e)}

    # Extrai retenções de impostos mapeadas no XML
    ret_dict = fiscal_data.get('retencoes', {})

    # Create lancamento from NF-e
    lancamento = {
        'historico': f"NF-e {fiscal_data.get('numero_nfe', '')} - {emitente_nome or 'Emitente não identificado'}",
        'data_lancamento': fiscal_data.get('data_emissao'),
        'valor': fiscal_data.get('valor_nf', 0),
        'tipo_dc': 'debito',  # NF-e de fornecedor é debito por padrão
        'origem': 'NF-e',
        'status': 'pendente',
        'empresa_id': empresa_id,
        'retencao_iss': ret_dict.get('vISSRet', 0.0),
        'retencao_irrf': ret_dict.get('vIRRF', 0.0),
        'retencao_csll': ret_dict.get('vRetCSLL', 0.0),
        'dados_extracao': fiscal_data  # Payload cru salvo em JSON
    }

    # Apply classification loop for NF-e
    lancamento = apply_classification_rules(client, [lancamento], empresa_id)[0]

    try:
        client.table('lancamentos').insert(lancamento).execute()
    except Exception as e:
        return {'status': 'erro', 'mensagem': f'Erro ao salvar lançamento: {e}'}

    return {
        'status': 'ok',
        'arquivo': filename,
        'numero_nfe': fiscal_data.get('numero_nfe'),
        'emitente': emitente_nome,
        'valor': fiscal_data.get('valor_nf'),
        'empresa_id': empresa_id,
        'empresa_nome': emitente_nome # Returned for display/storage organization
    }


def import_pdf(content: bytes, filename: str, storage_path: str, empresa_id: str = None) -> dict:
    """
    Full PDF import pipeline (Usa IA) with Auto-Registration.
    """
    client = _get_client()
    pdf_data = parse_pdf_transactions(content)
    transactions = pdf_data.get('transactions', [])
    metadata = pdf_data.get('metadata', {})
    
    # Campo pode vir como nome_empresa (IA)
    org_name = metadata.get('nome_empresa') or metadata.get('org_name')
    logger.debug(f"import_pdf: org_name={org_name}, txns={len(transactions)}")

    if not transactions:
        return {'status': 'erro', 'mensagem': 'Nenhum lançamento extraído do PDF via IA.'}

    # Validate empresa_id — if stale/ghost, fall back to auto-registration
    if empresa_id and not _validate_empresa_id(empresa_id, client):
        logger.warning(f"[Import PDF] empresa_id '{empresa_id}' não existe no banco. Fazendo auto-registro...")
        empresa_id = None

    if not empresa_id:
        if not org_name:
            return {'status': 'erro', 'mensagem': f'Não foi possível identificar a empresa via IA no PDF "{filename}". Selecione uma empresa antes de importar.'}
            
        try:
            empresa_id = _ensure_empresa(org_name, client)
        except RuntimeError as e:
            return {'status': 'erro', 'mensagem': str(e)}

    if not empresa_id:
        return {'status': 'erro', 'mensagem': f'Não foi possível identificar ou criar empresa para "{filename}". Selecione uma empresa antes de importar.'}

    # Apply classification rules
    transactions = apply_classification_rules(client, transactions, empresa_id)

    inserted = 0
    for txn in transactions:
        txn['empresa_id'] = empresa_id
        try:
            client.table('lancamentos').insert(txn).execute()
            inserted += 1
        except Exception as e:
            logger.exception(f"[Import PDF] erro ao inserir transação: {e}")

    return {
        'status': 'ok',
        'arquivo': filename,
        'inseridos': inserted,
        'mensagem': f'IA extraiu {inserted} lançamentos com sucesso.',
        'empresa_id': empresa_id,
        'empresa_nome': org_name
    }


from app.application.services.csv_parser import parse_csv


def import_csv(content: bytes, filename: str, storage_path: str, empresa_id: str = None) -> dict:
    """
    Full CSV import pipeline with Auto-Registration.
    """
    client = _get_client()

    # Parse
    csv_data = parse_csv(content)
    transactions = csv_data.get('transactions', [])
    
    if 'error' in csv_data:
        return {'status': 'erro', 'mensagem': csv_data['error']}

    if not transactions:
        return {'status': 'erro', 'mensagem': 'Nenhuma transação encontrada no arquivo CSV.'}

    # Validate empresa_id — if stale/ghost, fall back to auto-registration
    if empresa_id and not _validate_empresa_id(empresa_id, client):
        logger.warning(f"[Import CSV] empresa_id '{empresa_id}' não existe no banco. Fazendo auto-registro...")
        empresa_id = None

    if not empresa_id:
        # CSV doesn't extract org_name yet, so we REQUIRE a selection if not in content
        return {'status': 'erro', 'mensagem': f'O formato CSV não permite identificação automática da empresa em "{filename}". Por favor, selecione uma empresa no menu lateral antes de importar.', 'inseridos': 0}

    # Apply classification rules
    transactions = apply_classification_rules(client, transactions, empresa_id)

    # Insert transactions
    inserted = 0
    for txn in transactions:
        txn['empresa_id'] = empresa_id
        try:
            client.table('lancamentos').insert(txn).execute()
            inserted += 1
        except Exception as e:
            logger.exception(f"[Import CSV] erro ao inserir transação: {e}")

    return {
        'status': 'ok',
        'arquivo': filename,
        'inseridos': inserted,
        'empresa_id': empresa_id,
        'empresa_nome': None # CSV requires manual selection/active business
    }


def import_dominio(content: bytes, filename: str, storage_path: str, empresa_id: str = None) -> dict:
    """
    Import accounting entries from Domínio Systems layout.
    """
    client = _get_client()
    
    # Parse Domínio Layout
    entries = parse_dominio_layout(content)
    
    if not entries:
        return {'status': 'erro', 'mensagem': 'Nenhum lançamento válido encontrado no layout Domínio.'}
        
    if not empresa_id:
        return {'status': 'erro', 'mensagem': 'A importação do Domínio exige uma empresa selecionada.'}

    inserted = 0
    for entry in entries:
        entry['empresa_id'] = empresa_id
        entry['origem'] = 'Domínio'
        entry['status'] = 'pendente'
        
        try:
            client.table('lancamentos').insert(entry).execute()
            inserted += 1
        except Exception as e:
            logger.exception(f"[Import Domínio] erro ao inserir: {e}")

    return {
        'status': 'ok',
        'arquivo': filename,
        'inseridos': inserted,
        'mensagem': f'Importados {inserted} lançamentos do Domínio para conciliação.',
        'empresa_id': empresa_id
    }


def detect_company(content: bytes, filename: str) -> dict:
    ext = filename.rsplit('.', 1)[-1].lower()
    client = _get_client()
    
    name = None
    cnpj = None

    # 1. FAST PATH: Tentativa por Nome do Arquivo
    try:
        resp = client.table('empresas').select('id, nome').execute()
        for emp in (resp.data or []):
            slug_emp = re.sub(r'[^a-zA-Z0-9]', '', emp['nome'].upper())
            slug_file = re.sub(r'[^a-zA-Z0-9]', '', filename.upper())
            if slug_emp and slug_emp in slug_file:
                logger.info(f"[Detect] Identificado via NOME DE ARQUIVO: {emp['nome']}")
                return {'empresa_id': emp['id'], 'empresa_nome': emp['nome']}
    except Exception as e:
        logger.error(f"[Detect Heuristic] Erro: {e}")

    # 2. CONTENT PATH: Analisa o conteúdo do arquivo
    text = ""
    if isinstance(content, bytes):
        try:
            text = content.decode('utf-8')
        except Exception:
            text = content.decode('latin-1', errors='ignore')
    else:
        text = str(content)

    try:
        if ext == 'ofx':
            # <ORG> no OFX é o BANCO (ex: Stone, Itaú), NÃO a empresa cliente.
            # A empresa cliente está no NOME DO ARQUIVO (ex: "Sushi Express.ofx").
            # Usamos o stem do arquivo como nome da empresa para OFX.
            import os
            file_stem = os.path.splitext(filename)[0]
            # Remove padrões comuns de datas/números do filename para extrair apenas o nome
            cleaned_stem = re.sub(r'\b(20\d{2}|jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez|\d{2,})\b', '', file_stem, flags=re.IGNORECASE)
            cleaned_stem = re.sub(r'[\-_]+', ' ', cleaned_stem).strip()
            if len(cleaned_stem) >= 3:
                name = cleaned_stem
                logger.info(f"[Detect OFX] Usando nome do arquivo como empresa: '{name}'")
            
            # Log do banco para diagnóstico (mas NÃO usa como nome de empresa)
            match_org = re.search(r'<ORG>\s*([^<\r\n]+)', text, re.IGNORECASE)
            if match_org:
                logger.debug(f"[Detect OFX] Banco/Adquirente no OFX: '{match_org.group(1).strip()}' (ignorado para identificação de empresa)")

        elif ext == 'xml':
            try:
                from app.application.services.nfe_parser import parse_nfe_xml
                data = parse_nfe_xml(text)
                name = data.get('nome_emitente')
                cnpj = data.get('cnpj_emitente')
            except Exception: pass
            
        elif ext == 'pdf':
            try:
                from app.application.services.pdf_parser import parse_pdf_transactions
                data = parse_pdf_transactions(content)
                metadata = data.get('metadata', {})
                name = metadata.get('nome_empresa') or metadata.get('org_name')
                # Fallback para PDF: usa o stem do arquivo se a IA não identificar
                if not name:
                    import os
                    file_stem = os.path.splitext(filename)[0]
                    cleaned_stem = re.sub(r'[\-_\d]+', ' ', file_stem).strip()
                    if len(cleaned_stem) >= 3:
                        name = cleaned_stem
                        logger.info(f"[Detect PDF] Fallback para nome do arquivo: '{name}'")
            except Exception as ai_err:
                logger.error(f"[Detect content] AI falhou: {ai_err}")

    except Exception as e:
        logger.error(f"[Detect Content] Erro ao processar: {e}")
        
    if name:
        logger.info(f"[Detect Content] Nome '{name}' extraído de {filename}")
        try:
            eid = _ensure_empresa(name, client, cnpj=cnpj)
            if eid:
                return {'empresa_id': eid, 'empresa_nome': name}
        except Exception: pass
            
    return {'empresa_id': None, 'empresa_nome': None}


def import_document(content: bytes, filename: str, storage_path: str, empresa_id: str = None) -> dict:
    """
    Route to the correct parser based on file extension.
    """
    ext = filename.rsplit('.', 1)[-1].lower()

    # Heurística para Domínio: Se for .txt ou se o nome contiver 'dominio'
    if 'dominio' in filename.lower() or (ext == 'txt'):
         res = import_dominio(content, filename, storage_path, empresa_id)
         if res['status'] == 'ok':
             return res

    if ext == 'ofx':
        return import_ofx(content, filename, storage_path, empresa_id)
    elif ext == 'xml':
        return import_nfe(content, filename, storage_path, empresa_id)
    elif ext == 'pdf':
        return import_pdf(content, filename, storage_path, empresa_id)
    elif ext in ('xlsx', 'xls'):
        from app.application.services.excel_import_service import import_excel
        return import_excel(content, filename, empresa_id)
    elif ext == 'csv':
        return import_csv(content, filename, storage_path, empresa_id)
    else:
        return {'status': 'aviso', 'mensagem': f'Tipo ".{ext}" ainda não suportado automaticamente. Documento salvo.'}

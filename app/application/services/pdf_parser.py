import pdfplumber
import io
import json
from app.infrastructure.ai.services import get_ai_response
from app.infrastructure.logger import logger

# Only these fields exist in the lancamentos table
_LANCAMENTO_ALLOWED_FIELDS = {
    'data_lancamento', 'historico', 'valor', 'tipo_dc',
    'origem', 'status', 'transacao_origem_id', 'empresa_id',
    'plano_contas_id',
}

def extract_text_from_pdf(content: bytes) -> str:
    """Extrai todo o texto de um arquivo PDF usando pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        logger.exception(f"[PDF Parser] erro ao extrair texto: {e}")
        return ""
    return text

def parse_pdf_transactions(content: bytes) -> dict:
    """
    Extrai o texto do PDF e usa o ContAI (OpenAI) para estruturar os lançamentos e metadados.
    """
    text = extract_text_from_pdf(content)
    if not text:
        return {'transactions': [], 'metadata': {}}

    prompt = f"""
    Analise o texto extraído de um extrato bancário em PDF abaixo.
    
    TEXTO DO EXTRATO:
    ---
    {text[:4000]}
    ---

    INSTRUÇÕES:
    1. Retorne um JSON com dois campos principais: "metadata" e "transactions".
    2. Em "metadata", extraia o nome da empresa/titular da conta (campo "nome_empresa").
    3. Em "transactions" (lista), cada objeto deve ter APENAS estes campos:
       - "data_lancamento": string YYYY-MM-DD
       - "historico": string com a descrição
       - "valor": número decimal positivo
       - "tipo_dc": "debito" ou "credito"
       - "transacao_origem_id": string id ou null
    
    4. Ignore saldos e rodapés. NÃO inclua nenhum campo extra. Retorne APENAS o JSON.
    """

    try:
        response = get_ai_response(prompt)
        if not response:
            logger.warning("[PDF Parser] IA retornou resposta vazia (possível Rate Limit). Prosseguindo sem dados.")
            return {'transactions': [], 'metadata': {}}
            
        clean_response = response.strip()
        if "```json" in clean_response:
            clean_response = clean_response.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_response:
            clean_response = clean_response.split("```")[1].split("```")[0].strip()
        
        try:
            data = json.loads(clean_response)
        except json.JSONDecodeError as je:
            # Resposta truncada pela IA — tenta recuperar o que for possível
            logger.warning(f"[PDF Parser] JSON truncado (char {je.pos}). Tentando recuperação parcial...")
            logger.debug(f"[PDF Parser] Raw response (500 chars): {clean_response[:500]}")
            # Estratégia: Tenta completar manualmente o JSON truncado
            try:
                # Remove o final corrompido e fecha os colchetes/chaves
                safe = clean_response[:je.pos].rstrip(',').rstrip()
                if safe.endswith('"') or safe[-1].isalnum():
                    safe = safe + '"'
                safe = safe + '}]}'
                data = json.loads(safe)
                logger.info("[PDF Parser] Recuperação parcial do JSON bem-sucedida.")
            except Exception:
                logger.error("[PDF Parser] Impossível recuperar JSON truncado. Retornando vazio.")
                return {'transactions': [], 'metadata': {}}
            
        transactions = data.get('transactions', [])
        metadata = data.get('metadata', {})
        
        # Add standard fields and strip any unknown keys the AI may have hallucinated
        cleaned = []
        for txn in transactions:
            txn['origem'] = 'PDF'
            txn['status'] = 'pendente'
            # Keep only fields that exist in the DB schema
            txn = {k: v for k, v in txn.items() if k in _LANCAMENTO_ALLOWED_FIELDS}
            cleaned.append(txn)
            
        return {
            'transactions': cleaned,
            'metadata': metadata
        }
    except Exception as e:
        logger.exception(f"[PDF Parser] erro ao interpretar com IA: {e}")
        return {'transactions': [], 'metadata': {}}

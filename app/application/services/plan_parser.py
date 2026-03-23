import os
import json
import pdfplumber
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.infrastructure.logger import logger

def parse_plano_contas_pdf_stream(file_bytes: bytes):
    """Lê o PDF e retorna um gerador rendendo dicts de eventos, ex: {'status': 'progress', 'msg': '...'}"""
    import io
    import re
    
    yield {"status": "progress", "msg": "Extraindo texto bruto do PDF via PDFPlumber..."}
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
    except Exception as e:
        logger.exception(f"[Plan Parser] erro extract: {e}")
        yield {"status": "error", "erro": f"Falha ao extrair texto: {e}"}
        return
        
    cleaned_text = re.sub(r'\s+', ' ', text).strip()
    if not cleaned_text:
        yield {"status": "error", "erro": "Documento vazio ou ilegível."}
        return

    # Vamos particionar para evitar a saturação de output tokens na IA (gpt-4o-mini limita output em 16k tokens)
    # Como uma página tem ao redor de 3k-4k chars, e queremos gerar ~1 JSON de saida estruturado, 
    # pedaços de 8000 caracteres é um teto seguro para iterar todo o arquivo sem truncamentos.
    chunk_size = 10000
    chunks = [cleaned_text[i:i+chunk_size] for i in range(0, len(cleaned_text), chunk_size)]
    
    yield {"status": "progress", "msg": f"PDF longo identificado. Dividido em {len(chunks)} blocos de processamento."}

    api_key = os.environ.get('OPENAI_API_KEY', '').strip().strip('"').strip("'")
    if not api_key:
        yield {"status": "error", "erro": "OPENAI_API_KEY não configurada."}
        return

    llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.0)
    
    system_prompt = """Você é um Especialista em Contabilidade Brasileira e Análise de Dados.
Sua missão é extrair minuciosamente O PLANO DE CONTAS em um formato JSON da estrutura crua abaixo.

*** ATENÇÃO CRÍTICA AO LAYOUT DOMÍNIO SISTEMAS ***
Geralmente, há duas colunas confundíveis:
Coluna "Classificação": Contém a hierarquia ESTRUTURAL (Ex: 1, 1.1, 1.1.01.001, 3.1.4.02).
Coluna "Código": Contém um número id interno, curto (Ex: 293, 294, 666).

REGRAS DE FORMATAÇÃO:
1. No campo JSON "codigo", ENVIE A DESCRIÇÃO HIERÁRQUICA ESTRUTURAL que contenha pontos (ex: "1.1.1.01.001" ou "3.2.1"). ESQUEÇA O CÓDIGO INTERNO REDUZIDO NUMÉRICO DA COLUNA "Código"! Traga sempre a "Classificação"!
2. No campo "nome", o nome da conta.
3. Ignore linhas que não parecem estruturais contábeis (cabeçalhos como CNPJ, PLANO DE CONTAS, Emissão, Data).
4. Em "tipo", responda "DEBITO" ou "CREDITO".
5. Em "natureza", "ATIVO", "PASSIVO", "RECEITA" ou "DESPESA".

6. SAÍDA JSON EXCLUSIVA OBRIGATÓRIA:
{
  "contas": [
    {"codigo": "1.1.1.01.001", "nome": "CAIXA GERAL", "tipo": "DEBITO", "natureza": "ATIVO"}
  ]
}
Não imprima mais nada além do objeto JSON."""

    todas_contas = []
    for idx, chunk in enumerate(chunks):
        yield {"status": "progress", "msg": f"Ponderando bloco {idx+1}/{len(chunks)} na base do modelo GPT-4o-mini..."}
        
        try:
            response = llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"BLOCO DE DADOS BRUTOS {idx+1}:\n{chunk}")
            ])
            
            raw_output = response.content.strip()
            
            if "```json" in raw_output:
                raw_output = raw_output.split("```json")[1].split("```")[0].strip()
            elif "```" in raw_output:
                raw_output = raw_output.split("```")[1].split("```")[0].strip()

            parsed = json.loads(raw_output)
            contas = parsed.get("contas", [])
            
            if contas:
                todas_contas.extend(contas)
                yield {"status": "progress", "msg": f" ✓ Mais {len(contas)} contas salvas à memória..."}
                
        except Exception as e:
            logger.error(f"[Plan Parser] Falha parcial chunk {idx+1}: {e}")
            yield {"status": "progress", "msg": f"Aviso Interno: Análises do segmento {idx+1} não puderam ser abstraídas."}

    if not todas_contas:
        yield {"status": "error", "erro": "Infelizmente nenhuma formatação contábil válida emergiu do arquivo."}
        return
        
    yield {"status": "final_data", "contas": todas_contas}

import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.infrastructure.logger import logger

SYSTEM_PROMPT = """[PERSONA CORE]
Identidade: Você é o "ContAI", a Inteligência Artificial central da Mendonça Galvão Contadores Associados.
Experiência: Especialista Sênior em Contabilidade Brasileira, Fiscal, Fechamento Contábil, Conciliação Financeira, SPED e Legislação Tributária.
Tom e Estilo: Cirúrgico, objetivo, técnico, porém altamente didático. Você resolve problemas e nunca usa suposições como fato. Idioma estritamente PT-BR.

[ARQUITETURA DE RACIOCÍNIO - HIERARQUIA DE PROCESSAMENTO]
Toda vez que uma nova tarefa ou arquivo chegar até você, independente de estrutura desorganizada dos dados, você deve processar na seguinte ordem lógica:

1. [INJEÇÃO DE CONTEXTO E METADADOS]
   - O que eu sei? Você lerá a seção "Contexto do Sistema (dados atuais)" que contém informações factuais do banco de dados.
   - EMPRESA ATIVA: Verifique sempre os campos `empresa_ativa` e `cnpj_empresa`. Se o usuário perguntar sobre "esta empresa" ou citar o nome dela, use esses dados. Jamais diga que não tem acesso a uma empresa que está listada no contexto como ativa.
   - O que me foi pedido? Identifique se o pedido/arquivo é para (A) Extração Estrutural, (B) Classificação/Conciliação, ou (C) Explicação e Relatório via Chat.

2. [RESILIÊNCIA DE FORMATOS E DINAMISMO (ARQUIVOS E PLANILHAS)]
   - Assume-se que clientes enviem formatos corrompidos ou com nomenclaturas anômalas.
   - Jamais exija colunas fixas ou cabeçalhos perfeitos. Utilize ancoragem semântica:
     * Exemplo: Se encontrar uma coluna escrita "Saídas (R$)", mapeie cognitivamente para a variável isolada "valor_debito".
     * Exemplo 2: Se um PDF de banco não tiver ordem cronológica clara, busque os blocos formatados em formato DATA e construa a linha temporal da transação.
   - Ignore "ruídos" (informações inúteis de cabeçalho, propaganda nos extratos, e células inúteis do Excel).

3. [REGRAS DE CLASSIFICAÇÃO CONTÁBIL E INTELIGÊNCIA]
   - Quando questionado para aplicar/sugerir classificações contábeis, cruze o "Histórico/Anotação" do extrato com a natureza real do Plano de Contas.
   - Impostos Retidos nas Notas Fiscais (ISS, IRRF, CSLL, PIS/COFINS) NUNCA podem ser somados magicamente. Você deve declarar a base de cálculo, a alíquota extraída e a dedução exata conforme legislação.

4. [ANTI-ALUCINAÇÃO & COMPLIANCE]
   - Tolerância zero para invenção de dados financeiros.
   - Se um extrato cita um gasto com valor indefinido, você DEVE retornar valor `null` ou 0.0, ao invez de presumir baseado no mercado.
   - Se perguntado no CHAT sobre algo fora do "Contexto do Sistema", você deve explicitar: "Como Assistente, não tenho acesso a esse documento no banco de dados ativo no momento".

5. [AGENDAMENTO E CALENDÁRIO]
   - Se o usuário pedir para criar um compromisso ou evento:
     * REUNIÃO/ALINHAMENTO: Se o evento for claramente uma reunião (ex: "Reunião com X", "Alinhamento", "Standup"), inclua obrigatoriamente um link do Google Meet e um ID fictício no formato UUID.
     * EVENTO GERAL: Se for um lembrete ou evento simples (ex: "Aniversário", "Lembrete", "Reunião com meu Pai" - se não for profissional), NÃO inclua link de reunião, apenas confirme o horário.
     * FORMATO: Use sempre Markdown para links: `[Clique aqui para acessar](URL)`.

6. [FORMATO DE SAÍDA (QUANDO SOLICITADA INTEGRAÇÃO SISTÊMICA)]
   - Se a tarefa exigir um JSON (como no mapeamento dinâmico de planilhas ou classificação), responda ESTRITAMENTE o JSON. Proibido adicionar blocos de texto como "Aqui está o JSON..." ou formatadores Markdown caso não solicitado explicitamente.

[EXECUÇÃO]
Atue como o maestro da auditoria fiscal, assegurando 100% de precisão em cada cruzamento efetuado entre o documento de origem e o ERP."""

def get_ai_response(user_input: str, context: dict | None = None) -> str:
    """
    Chama o ContAI usando OpenAI. 
    Se a IA falhar (ex: Rate Limit), o erro é capturado e retorna vazio
    para que fallbacks (como nome de arquivo) possam assumir.
    """
    api_key = os.environ.get('OPENAI_API_KEY', '').strip().strip('"').strip("'")
    if not api_key:
        logger.error("[AI Service] OPENAI_API_KEY não configurada no .env")
        return ""

    try:
        llm = ChatOpenAI(
            model="gpt-4o-mini",
            api_key=api_key,
            temperature=0.7,
        )
        return _call_llm(llm, user_input, context)
    except Exception as e:
        # Se atingir o limite de quota ou conexão, apenas loga um aviso e segue
        if any(term in str(e).lower() for term in ["429", "rate_limit", "quota", "connection"]):
            logger.warning(f"[AI Service] IA indisponível momentaneamente ({e}). Seguindo para fallbacks offline.")
            return ""
        
        logger.error(f"[AI Service] Erro crítico no modelo: {e}")
        raise e

def _call_llm(llm, user_input, context):
    system_content = SYSTEM_PROMPT
    if context:
        system_content += "\n\n## Contexto do Sistema (dados atuais)\n"
        for k, v in context.items():
            system_content += f"- {k}: {v}\n"

    messages = [
        SystemMessage(content=system_content),
        HumanMessage(content=user_input),
    ]
    response = llm.invoke(messages)
    return response.content


def suggest_classification(transaction: dict, plano_contas: list) -> dict:
    """
    Usa IA para sugerir a classificação contábil correta baseada no histórico.
    Phase 3: AI Intelligence Engine.
    """
    api_key = os.environ.get('OPENAI_API_KEY', '').strip().strip('"').strip("'")
    if not api_key:
        return {"id": None, "descricao": "Erro: OPENAI_API_KEY", "confianca": 0}

    # Reduz o plano de contas para o prompt (apenas Despesas e Receitas costumam ser úteis aqui)
    plano_reduzido = [
        {"codigo": c['codigo_estrutural'], "nome": c['descricao']}
        for c in plano_contas
    ][:100] # Limite de sanidade

    prompt = f"""
    Como assistente contábil (ContAI), classifique o seguinte lançamento bancário no Plano de Contas fornecido.
    
    LANÇAMENTO:
    - Histórico: {transaction.get('historico')}
    - Valor: R$ {transaction.get('valor')}
    - Tipo: {transaction.get('tipo_dc')}
    
    PLANO DE CONTAS (Reduzido):
    {json.dumps(plano_reduzido, indent=2)}
    
    INSTRUÇÕES:
    1. Retorne APENAS um JSON com os campos: "codigo", "nome", "justificativa".
    2. Escolha o código que melhor se adapta à natureza do gasto/receita.
    3. Seja preciso. Se não tiver certeza, escolha a conta mais genérica compatível.
    """

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
        response = llm.invoke([HumanMessage(content=prompt)])
        
        clean_response = response.content.strip()
        if "```json" in clean_response:
            clean_response = clean_response.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_response:
            clean_response = clean_response.split("```")[1].split("```")[0].strip()
            
        return json.loads(clean_response)
    except Exception as e:
        logger.exception(f"[AI Classification] Erro: {e}")
        return {"codigo": None, "nome": "Não classificado", "justificativa": str(e)}


def batch_suggest_classification(transactions: list, plano_contas: list) -> dict:
    """
    Classifica transações em lote contra o plano de contas.
    Retorna dict mapeando: { 'id_da_transacao': 'id_da_conta_contabil' }
    """
    if not transactions or not plano_contas:
        return {}

    api_key = os.environ.get('OPENAI_API_KEY', '').strip().strip('"').strip("'")
    if not api_key:
        logger.debug("[AI Batch Classification] OPENAI_API_KEY ausente.")
        return {}

    # Reduz plano para não estourar o limite de tokens
    plano_reduzido = [
        {"id_conta": c.get('id'), "codigo": c.get('codigo_estrutural'), "nome": c.get('descricao'), "tipo": c.get('tipo')}
        for c in plano_contas
    ]
    
    # Prepara lote de transações
    txns_reduzido = [
        {"id_transacao": t.get('id', t.get('transacao_origem_id', str(i))), "historico": t.get('historico'), "valor": t.get('valor'), "tipo_dc": t.get('tipo_dc')}
        for i, t in enumerate(transactions)
    ]

    prompt = f"""
Você é o assistente contábil (ContAI). Sua tarefa é classificar um LOTE de transações bancárias.

PLANO DE CONTAS DISPONÍVEL:
{json.dumps(plano_reduzido, indent=1)}

TRANSAÇÕES A CLASSIFICAR:
{json.dumps(txns_reduzido, indent=1)}

REGRAS OBRIGATÓRIAS:
1. Retorne EXCLUSIVAMENTE um objeto JSON onde a chave é o "id_transacao" e o valor é o "id_conta" escolhido.
2. Não classifique se não houver correlação óbvia, nesse caso omita a chave ou passe `null`.
3. Retorne apenas o objeto JSON, sem formatação markdown adicional ou textos fora do JSON.
Exemplo de resposta esperada:
{{
  "UUID-1": "UUID-CONTA-A",
  "UUID-2": "UUID-CONTA-B"
}}
"""
    try:
        llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.1)
        response = llm.invoke([HumanMessage(content=prompt)])
        
        raw_output = response.content.strip()
        if "```json" in raw_output:
            raw_output = raw_output.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_output:
            raw_output = raw_output.split("```")[1].split("```")[0].strip()

        raw_suggestions = json.loads(raw_output)
        
        # Mapeamento reverso para caso a IA tenha retornado o código estrutural em vez do ID (hallucination)
        code_to_id = {str(c.get('codigo_estrutural')): c.get('id') for c in plano_contas if c.get('codigo_estrutural')}
        valid_ids = {str(c.get('id')) for c in plano_contas}
        
        final_suggestions = {}
        for txn_id, sug_id in raw_suggestions.items():
            if not sug_id: continue
            sug_str = str(sug_id).strip()
            
            if sug_str in valid_ids:
                final_suggestions[txn_id] = sug_str
            elif sug_str in code_to_id:
                final_suggestions[txn_id] = code_to_id[sug_str]
            else:
                logger.warning(f"[AI Batch] Sugestão inválida ignorada (não é ID nem código): {sug_str}")
                
        return final_suggestions
    except Exception as e:
        logger.exception(f"[AI Batch Classification] Erro na requisição em lote: {e}")
        return {}


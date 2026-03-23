from flask import Blueprint, jsonify, request, session
from app.web.routes.decorators import login_required
from app.web.routes.api_responses import ok, error

bp = Blueprint('chat', __name__)


@bp.route('/history')
@login_required
def get_history():
    """Retorna o histórico de mensagens de HOJE para o usuário/empresa."""
    from app.infrastructure.supabase.client import db_adapter
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    from app.infrastructure.logger import logger
    
    client = db_adapter.get_client()
    if not client:
        return ok(data=[])

    user_id = session.get('user', {}).get('id')
    active_empresa = session.get('active_empresa', {})
    empresa_id = active_empresa.get('id')

    # Sem empresa ativa → retorna histórico vazio (chat será resetado pelo frontend)
    if not empresa_id:
        return ok(data=[])

    # Filtro por Hoje (reset às 00:00 em America/Sao_Paulo)
    # Supabase armazena normalmente em timestamptz (UTC). Então comparamos usando UTC.
    sp_tz = ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.now(sp_tz)
    start_sp = now_sp.replace(hour=0, minute=0, second=0, microsecond=0)
    start_utc = start_sp.astimezone(timezone.utc)
    start_utc_iso = start_utc.isoformat()

    try:
        query = client.table('chat_mensagens').select('remetente, conteudo, created_at')\
            .eq('user_id', user_id)\
            .gte('created_at', start_utc_iso)
        
        if empresa_id:
            query = query.eq('empresa_id', empresa_id)
        
        resp = query.order('created_at', desc=False).execute()
        return ok(data=resp.data or [])
    except Exception as e:
        logger.error(f"[Chat History] Error: {e}")
        return ok(data=[])

@bp.route('/send', methods=['POST'])
@login_required
def send_message():
    data = request.get_json(silent=True) or {}
    message = (data.get('message') or '').strip()
    if not message:
        return error("Mensagem vazia.", status_code=400, code="EMPTY_MESSAGE")

    user_id = session.get('user', {}).get('id')
    active_empresa = session.get('active_empresa', {})
    empresa_id = active_empresa.get('id')

    # Sem empresa selecionada → resposta imediata sem chamar IA
    if not empresa_id:
        return ok(data={"response": (
            "Nenhuma empresa está selecionada no momento. "
            "Selecione ou cadastre uma empresa no menu lateral para que eu possa "
            "acessar os dados e ajudar com sua análise contábil."
        )})

    try:
        from app.infrastructure.supabase.client import db_adapter
        from app.infrastructure.ai.services import get_ai_response
        from app.infrastructure.logger import logger
        
        client = db_adapter.get_client()
        
        # 1. Salva mensagem do usuário no banco
        if client:
            client.table('chat_mensagens').insert({
                'user_id': user_id,
                'empresa_id': empresa_id,
                'remetente': 'user',
                'conteudo': message
            }).execute()

        context = {
            'empresa_ativa': active_empresa.get('nome', 'Não Identificada'),
            'cnpj_empresa': active_empresa.get('cnpj', 'Não Cadastrado'),
        }
        
        if client:
            try:
                # ── Documentos ───────────────────────────────────────────────────────
                q_docs = client.table('documentos').select('nome_original, tipo, status')
                if empresa_id:
                    q_docs = q_docs.eq('empresa_id', empresa_id)
                docs = q_docs.order('created_at', desc=True).limit(10).execute().data or []
                context['documentos'] = [f"{d['nome_original']} ({d['tipo']}/{d['status']})" for d in docs]

                # ── Lançamentos bancários (Excel/OFX) ────────────────────────────────
                q_b = client.table('lancamentos').select(
                    'historico, valor, tipo_dc, status, data_lancamento'
                ).in_('origem', ['Excel', 'OFX'])
                if empresa_id:
                    q_b = q_b.eq('empresa_id', empresa_id)
                banc = q_b.order('data_lancamento', desc=True).execute().data or []

                # ── Lançamentos documentais (PDF/XML) ────────────────────────────────
                q_p = client.table('lancamentos').select(
                    'historico, valor, tipo_dc, status, data_lancamento'
                ).in_('origem', ['PDF', 'XML'])
                if empresa_id:
                    q_p = q_p.eq('empresa_id', empresa_id)
                pdfs = q_p.order('data_lancamento', desc=True).execute().data or []

                # ── Resumo compacto de conciliação ───────────────────────────────────
                conc  = [l for l in banc if l['status'] == 'concluido']
                pend  = [l for l in banc if l['status'] == 'pendente']
                exc   = [l for l in banc if l['status'] == 'excecao']
                v_tot = sum(abs(float(l.get('valor') or 0)) for l in banc)
                v_con = sum(abs(float(l.get('valor') or 0)) for l in conc)

                context['conciliacao'] = (
                    f"Bancários: {len(banc)} | PDF/docs: {len(pdfs)} | "
                    f"Conciliados: {len(conc)} | Exceções: {len(exc)} | Pendentes: {len(pend)} | "
                    f"Taxa: {round(len(conc)/len(banc)*100,1) if banc else 0}% | "
                    f"Total bancário: R${v_tot:,.2f} | Conciliado: R${v_con:,.2f} | "
                    f"Pendente: R${v_tot - v_con:,.2f}"
                )

                # ── Amostra de 10 lançamentos por lado (econômico) ──────────────────
                context['amostra_bancario'] = [
                    f"{l['data_lancamento']} {l['historico']} R${l['valor']} {l['tipo_dc']} [{l['status']}]"
                    for l in banc[:10]
                ]
                context['amostra_pdf'] = [
                    f"{l['data_lancamento']} {l['historico']} R${l['valor']} {l['tipo_dc']}"
                    for l in pdfs[:10]
                ]

                # ── Plano de Contas (Amostra) ────────────────────────────────────────
                q_pc = client.table('plano_contas').select('codigo, descricao, tipo')
                if empresa_id:
                    q_pc = q_pc.eq('empresa_id', empresa_id)
                contas = q_pc.order('codigo').limit(20).execute().data or []
                context['plano_contas'] = [f"{c['codigo']} - {c['descricao']} ({c['tipo']})" for c in contas]


            except Exception as ctx_err:
                from app.infrastructure.logger import logger as _lg
                _lg.warning(f"[Chat Context] Erro: {ctx_err}")


        response = get_ai_response(message, context=context)

        # 2. Salva resposta da IA no banco
        if client:
            client.table('chat_mensagens').insert({
                'user_id': user_id,
                'empresa_id': empresa_id,
                'remetente': 'ai',
                'conteudo': response
            }).execute()

    except RuntimeError as e:
        # API key missing or invalid — clear message
        response = f"⚠ Configuração do ContAI: {e}"
    except Exception as e:
        error_msg = str(e)
        if 'chat_mensagens' in error_msg:
            response = "⚠ Erro: A tabela 'chat_mensagens' não foi encontrada no Supabase. Por favor, execute o script SQL de criação (chat_history.sql) no painel do Supabase."
        else:
            logger.exception(f"[Chat] AI error: {type(e).__name__}: {e}")
            response = f"⚠ Erro no ContAI ({type(e).__name__}): {e}"

    return ok(data={"response": response})


@bp.route('/chat/diag')
@login_required
def diagnostic():
    """Lista os modelos disponíveis para esta chave de API."""
    import os
    import google.generativeai as genai
    api_key = os.environ.get('GOOGLE_API_KEY', '').strip().strip('"').strip("'")
    if not api_key:
        return "GOOGLE_API_KEY não encontrada."
    
    try:
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models()]
        return f"Modelos disponíveis: {', '.join(models)}"
    except Exception as e:
        return f"Erro ao listar modelos: {e}"


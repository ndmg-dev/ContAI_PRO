from datetime import datetime
from flask import Blueprint, render_template, session, request, redirect, url_for, flash, jsonify
from app.web.routes.decorators import login_required
from app.web.routes.api_responses import ok, error
from app.web.routes.request_context import get_active_empresa_id, get_active_empresa
from app.infrastructure.supabase.client import db_adapter
from app.application.services.conciliacao_service import run_conciliation, generate_report
from app.application.services.workflow import advance_lancamento, WorkflowStatus
from app.infrastructure.logger import logger

bp = Blueprint('conciliacao', __name__)


def _compute_conciliacao(active_id: str, periodo_ativo: str | None) -> dict:
    """
    Computes the conciliacao view data for the active empresa/período. Shared
    by the HTML route and the JSON API route.
    """
    client = db_adapter.get_client()
    result = {'pendentes': [], 'report': None, 'periodos': [], 'periodo_ativo': None}

    if not client or not active_id:
        return result

    # Detectar períodos disponíveis
    resp_p = client.table('lancamentos').select('data_lancamento').eq('empresa_id', active_id).eq('status', 'pendente').execute()
    datas = [d['data_lancamento'] for d in (resp_p.data or []) if d.get('data_lancamento')]
    periodos = sorted(list(set([d[:7] for d in datas])), reverse=True)

    if not periodo_ativo and periodos:
        periodo_ativo = periodos[0]

    q_ofx = client.table('lancamentos').select('*, plano_contas!conta_contabil_id(codigo_estrutural, descricao)').in_('origem', ['OFX', 'Excel']).eq('status', 'pendente').eq('empresa_id', active_id)
    # PDF/XML are the supporting document side for reconciliation
    q_pdf = client.table('lancamentos') \
                  .select('*, plano_contas!conta_contabil_id(codigo_estrutural, descricao)') \
                  .in_('origem', ['PDF', 'XML']) \
                  .eq('empresa_id', active_id)

    if periodo_ativo:
        try:
            ano, mes = map(int, periodo_ativo.split('-'))
            data_inicio = f"{ano}-{mes:02d}-01"
            mes_fim = mes + 1 if mes < 12 else 1
            ano_fim = ano if mes < 12 else ano + 1
            data_fim = f"{ano_fim}-{mes_fim:02d}-01"

            q_ofx = q_ofx.gte('data_lancamento', data_inicio).lt('data_lancamento', data_fim)
            q_pdf = q_pdf.gte('data_lancamento', data_inicio).lt('data_lancamento', data_fim)
        except ValueError:
            pass

    # EXECUTAR CONSULTAS
    ofx_entries = q_ofx.order('data_lancamento', desc=True).execute().data or []
    pdf_entries = q_pdf.execute().data or []

    report = None
    if ofx_entries or pdf_entries:
        matches = run_conciliation(ofx_entries, pdf_entries)
        report = generate_report(matches)

    return {
        'pendentes': ofx_entries,
        'report': report,
        'periodos': periodos,
        'periodo_ativo': periodo_ativo,
    }


@bp.route('/conciliacao')
@login_required
def index():
    active_id = get_active_empresa_id()
    periodo_ativo = request.args.get('periodo')

    try:
        data = _compute_conciliacao(active_id, periodo_ativo)
    except Exception as e:
        logger.exception(f"[Conciliacao] Erro: {e}")
        flash("Erro ao carregar os dados. Tente novamente.", "error")
        data = {'pendentes': [], 'report': None, 'periodos': [], 'periodo_ativo': None}

    return render_template('conciliacao.html', pendentes=data['pendentes'], report=data['report'],
                           periodos=data['periodos'], periodo_ativo=data['periodo_ativo'], user=session.get('user'))


@bp.route('/api/conciliacao')
@login_required
def api_index():
    """
    JSON: { ok, data: { pendentes: [...], report: {...}|null, periodos: [...],
                          periodo_ativo: str|null } }
    Query params: empresa_id (required if no active session empresa), periodo (optional, 'YYYY-MM').
    """
    active_id = get_active_empresa_id()
    if not active_id:
        return jsonify({'ok': False, 'message': 'Empresa não selecionada', 'code': 'NO_EMPRESA'}), 400

    periodo_ativo = request.args.get('periodo')
    try:
        data = _compute_conciliacao(active_id, periodo_ativo)
    except Exception as e:
        logger.exception(f"[Conciliacao] Erro: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500

    return jsonify({'ok': True, 'data': data})


@bp.route('/conciliacao/auto-classificar', methods=['POST'])
@login_required
def auto_classificar():
    """Trigger AI classification for the current active period/company."""
    client = db_adapter.get_client()
    active_id = get_active_empresa_id()

    if not client or not active_id:
        return error("Seleção de empresa inválida.")

    try:
        # Busca transações sem conta
        resp = client.table('lancamentos').select('*') \
                     .in_('origem', ['OFX', 'Excel']) \
                     .eq('empresa_id', active_id) \
                     .eq('status', 'pendente') \
                     .is_('conta_contabil_id', 'null') \
                     .limit(100).execute()
        
        unclassified = resp.data or []
        if not unclassified:
            return ok(message="Todos os lançamentos já estão classificados.")

        # Busca Plano de Contas
        resp_plan = client.table('plano_contas').select('*').eq('empresa_id', active_id).execute()
        plano = resp_plan.data or []
        
        if not plano:
            return error("Nenhum Plano de Contas encontrado. Importe-o primeiro na aba 'Plano de Contas'.")

        from app.infrastructure.ai.services import batch_suggest_classification
        suggestions = batch_suggest_classification(unclassified, plano)
        
        # Preparamos os objetos completos para o upsert (para evitar erro de NOT NULL se o Postgres tentar INSERT)
        full_updates = []
        applied_count = 0
        
        for txn in unclassified:
            txn_id = txn.get('id')
            s_id_conta = suggestions.get(txn_id)
            if s_id_conta:
                txn['conta_contabil_id'] = s_id_conta
                # Limpar campos que podem vir do join do select (plano_contas) para evitar erro de 'column not found'
                txn.pop('plano_contas', None)
                full_updates.append(txn)
                applied_count += 1
        
        if full_updates:
            client.table('lancamentos').upsert(full_updates, on_conflict='id').execute()
            return ok(message=f"{applied_count} lançamentos classificados com sucesso pela IA!")
            
        return ok(message="A IA não encontrou correspondências seguras para estes lançamentos.")

    except Exception as e:
        logger.exception(f"[Conciliacao] Erro auto-classificar: {e}")
        return error(f"Falha na classificação: {str(e)}")


@bp.route('/conciliacao/resolver/<lancamento_id>', methods=['POST'])
@login_required
def resolver(lancamento_id: str):
    """Mark a lancamento as conciliado."""
    updated = advance_lancamento(lancamento_id, WorkflowStatus.CONCLUIDO, notas='Resolvido manualmente')
    if updated:
        return ok()
    return error("Não foi possível atualizar o lançamento.", status_code=500, code="WORKFLOW_UPDATE_FAILED")


@bp.route('/conciliacao/excecao/<lancamento_id>', methods=['POST'])
@login_required
def marcar_excecao(lancamento_id: str):
    """Mark a lancamento as exception with a reason."""
    data = request.get_json(silent=True) or {}
    motivo = data.get('motivo', 'Sem correspondência identificada')
    ok2 = advance_lancamento(lancamento_id, WorkflowStatus.EXCECAO, notas=motivo)
    if ok2:
        return ok()
    return error("Não foi possível atualizar o lançamento.", status_code=500, code="WORKFLOW_UPDATE_FAILED")


@bp.route('/conciliacao/exportar-dominio')
@login_required
def exportar_dominio():
    """
    Gera arquivo TXT para importação no Domínio.
    Filtra lançamentos com status 'concluido' da empresa ativa.
    """
    from app.application.services.dominio_export_service import DominioExportService
    from flask import Response
    
    active_empresa = session.get('active_empresa', {})
    empresa_id = active_empresa.get('id')
    if not empresa_id:
        return redirect(url_for('conciliacao.index'))
    
    client = db_adapter.get_client()
    try:
        # Busca lançamentos já conciliados (status: concluido)
        # Podem ser da origem OFX ou PDF que foram marcados como finalizados
        resp = client.table('lancamentos').select('*, plano_contas!conta_contabil_id(codigo_estrutural, descricao)').eq('empresa_id', empresa_id).eq('status', 'concluido').execute()
        lancamentos = resp.data or []
        
        if not lancamentos:
            flash("Não existem lançamentos concluídos para exportar.", "info")
            return redirect(url_for('conciliacao.index'))
            
        txt_content = DominioExportService.generate_txt(lancamentos, empresa=active_empresa)
        
        # Gera o arquivo para download
        filename = f"Dominio_ContAI_{active_empresa.get('nome','empresa')}_{datetime.now().strftime('%Y%m%d%H%M')}.txt"
        
        return Response(
            txt_content,
            mimetype="text/plain",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        logger.exception(f"Erro ao exportar arquivo Domínio: {e}")
        flash(f"Erro ao gerar arquivo: {str(e)}", "danger")
        return redirect(url_for('conciliacao.index'))
@bp.route('/conciliacao/confirmar-todos', methods=['POST'])
@login_required
def confirmar_todos():
    """Bulk-confirm all lancamentos that matched (score >= threshold)."""
    from app.application.services.conciliacao_service import run_conciliation, generate_report
    client = db_adapter.get_client()
    active_id = get_active_empresa_id()

    if not client or not active_id:
        return error("Empresa não selecionada.", status_code=400)

    try:
        q_ofx = client.table('lancamentos').select('*').in_('origem', ['OFX', 'Excel']).eq('status', 'pendente').eq('empresa_id', active_id)
        ofx_entries = (q_ofx.execute().data or [])

        q_pdf = client.table('lancamentos').select('*').in_('origem', ['PDF', 'XML']).eq('empresa_id', active_id)
        pdf_entries = (q_pdf.execute().data or [])

        if not ofx_entries or not pdf_entries:
            return error("Sem lançamentos de Planilha/OFX + suporte PDF para confirmar.", status_code=400)

        matches = run_conciliation(ofx_entries, pdf_entries)
        confirmados = 0
        for m in matches:
            if m['status'] == 'conciliado' and m.get('lancamento_id'):
                advance_lancamento(m['lancamento_id'], WorkflowStatus.CONCLUIDO, notas='Confirmado em lote')
                confirmados += 1

        return ok(data={'confirmados': confirmados})
    except Exception as e:
        logger.exception(f"[Confirmar Todos] erro: {e}")
        return error(str(e), status_code=500)

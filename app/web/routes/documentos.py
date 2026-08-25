"""
Documentos Blueprint
Handles: company lookup/registration via CNPJ + document upload pipeline.
Auto-detection of company via file content has been REMOVED.
empresa_id in session is the single source of truth.
"""
import re
import unicodedata
from flask import Blueprint, render_template, session, redirect, url_for, request, flash, jsonify
from app.web.routes.decorators import login_required
from app.web.routes.request_context import get_active_empresa_id
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

bp = Blueprint('documentos', __name__)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'xml', 'pdf', 'csv', 'ofx'}


def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[-1].lower() in ALLOWED_EXTENSIONS


def slugify(value: str) -> str:
    """Creates a filesystem-safe slug from a company name."""
    if not value:
        return 'sem-nome'
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().upper()
    return re.sub(r'[-\s]+', '-', value)


# ─── Pages ────────────────────────────────────────────────────────────────────

def _compute_documentos(active_id: str) -> list:
    client = db_adapter.get_client()
    documentos = []
    if client and active_id:
        try:
            resp = client.table('documentos').select('*') \
                         .eq('empresa_id', active_id) \
                         .order('created_at', desc=True) \
                         .limit(50).execute()
            documentos = resp.data or []
        except Exception as e:
            logger.error(f"[Documentos] erro ao buscar documentos: {e}")
    return documentos


@bp.route('/documentos')
@login_required
def index():
    active_id = get_active_empresa_id()
    documentos = _compute_documentos(active_id)
    return render_template('documentos.html', documentos=documentos, user=session.get('user'))


@bp.route('/api/documentos')
@login_required
def api_index():
    """JSON: { ok, data: [ { id, empresa_id, nome_original, storage_path, tipo, status, created_at, ... } ] }"""
    active_id = get_active_empresa_id()
    documentos = _compute_documentos(active_id)
    return jsonify({'ok': True, 'data': documentos})


# ─── API: CNPJ Lookup ─────────────────────────────────────────────────────────

@bp.route('/documentos/buscar-cnpj', methods=['POST'])
@login_required
def buscar_cnpj():
    """
    Queries BrasilAPI for CNPJ data and returns a JSON payload.
    Does NOT save to DB — that's a separate step.
    """
    from app.application.services.receita_service import buscar_empresa_por_cnpj
    data = request.get_json(silent=True) or {}
    cnpj = data.get('cnpj', '').strip()

    if not cnpj:
        return jsonify({'ok': False, 'message': 'CNPJ não informado.'}), 400

    try:
        empresa = buscar_empresa_por_cnpj(cnpj)
        return jsonify({'ok': True, 'empresa': empresa})
    except ValueError as e:
        return jsonify({'ok': False, 'message': str(e)}), 422
    except Exception as e:
        logger.exception(f"[CNPJ Lookup] erro inesperado: {e}")
        return jsonify({'ok': False, 'message': 'Erro interno ao consultar a Receita Federal.'}), 500


# ─── API: Save Company ───────────────────────────────────────────────────────

@bp.route('/documentos/cadastrar-empresa', methods=['POST'])
@login_required
def cadastrar_empresa():
    """
    Persists a company into the 'empresas' table and sets it as active in session.
    Expects JSON: {cnpj, razao_social, nome_fantasia, ...}
    """
    data = request.get_json(silent=True) or {}
    cnpj = data.get('cnpj_limpo', '').strip()
    razao_social = data.get('razao_social', '').strip()

    if not cnpj or not razao_social:
        return jsonify({'ok': False, 'message': 'CNPJ e razão social são obrigatórios.'}), 400

    # Format CNPJ for display/storage
    cnpj_fmt = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}" if len(cnpj) == 14 else cnpj

    client = db_adapter.get_client()
    if not client:
        return jsonify({'ok': False, 'message': 'Banco de dados indisponível.'}), 503

    try:
        # Check if already exists
        resp = client.table('empresas').select('id, nome').eq('cnpj', cnpj_fmt).execute()
        if resp.data:
            empresa = resp.data[0]
            session['active_empresa'] = {'id': empresa['id'], 'nome': empresa['nome']}
            session.modified = True
            return jsonify({'ok': True, 'message': 'Empresa já cadastrada. Selecionada automaticamente.', 'empresa': empresa})

        # Insert
        payload = {
            'nome': razao_social,
            'cnpj': cnpj_fmt,
        }
        ins = client.table('empresas').insert(payload).execute()
        if not ins.data:
            return jsonify({'ok': False, 'message': 'Falha ao salvar empresa no banco.'}), 500

        empresa = ins.data[0]
        session['active_empresa'] = {'id': empresa['id'], 'nome': empresa['nome']}
        session.modified = True
        logger.info(f"[Empresa] Cadastrada: {razao_social} ({cnpj_fmt})")
        return jsonify({'ok': True, 'message': f'Empresa {razao_social} cadastrada com sucesso!', 'empresa': empresa})

    except Exception as e:
        logger.exception(f"[Empresa] erro ao salvar: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


# ─── Upload ──────────────────────────────────────────────────────────────────

@bp.route('/documentos/upload', methods=['POST'])
@login_required
def upload():
    """
    Processes file uploads. empresa_id MUST already be set in session.
    No auto-detection of company — clean and predictable.
    """
    active_empresa = session.get('active_empresa', {})
    empresa_id = active_empresa.get('id')
    empresa_nome = active_empresa.get('nome')

    if not empresa_id:
        flash('Selecione ou cadastre uma empresa antes de importar documentos.', 'error')
        return redirect(url_for('documentos.index'))

    files = request.files.getlist('file')
    if not files or all(f.filename == '' for f in files):
        flash('Nenhum arquivo selecionado.', 'error')
        return redirect(url_for('documentos.index'))

    client = db_adapter.get_client()
    if not client:
        flash('Banco de dados indisponível.', 'error')
        return redirect(url_for('documentos.index'))

    from app.application.services.excel_import_service import import_excel
    from app.application.services.import_service import import_document

    folder_prefix = slugify(empresa_nome) if empresa_nome else empresa_id

    for f in files:
        if not f or f.filename == '':
            continue

        filename = f.filename
        if not _allowed(filename):
            flash(f'"{filename}" ignorado — tipo não suportado.', 'error')
            continue

        content = f.read()
        ext = filename.rsplit('.', 1)[-1].lower()
        tipo = {'xlsx': 'ofx', 'xls': 'ofx', 'xml': 'xml', 'pdf': 'pdf', 'csv': 'csv', 'ofx': 'ofx'}.get(ext, 'ofx')
        new_status = 'concluido'

        logger.info(f"[Upload] {filename} → empresa: {empresa_nome} ({empresa_id})")

        try:
            if ext in ('xlsx', 'xls'):
                result = import_excel(content, filename, empresa_id)
            else:
                result = import_document(content, filename, storage_path="", empresa_id=empresa_id)

            if result['status'] == 'ok':
                inseridos = result.get('inseridos', 0)
                duplicados = result.get('duplicados_ignorados', 0)
                msg = f'✓ {filename}: {inseridos} lançamento(s) criado(s)'
                if duplicados:
                    msg += f', {duplicados} duplicado(s) ignorado(s).'
                flash(msg, 'success')
            elif result['status'] == 'aviso':
                flash(f'⚠ {filename}: {result["mensagem"]}', 'info')
            else:
                new_status = 'erro'
                flash(f'✗ {filename}: {result.get("mensagem", "erro desconhecido")}', 'error')

        except Exception as e:
            new_status = 'erro'
            logger.exception(f"[Upload] falha inesperada em {filename}: {e}")
            flash(f'✗ {filename}: erro inesperado — {e}', 'error')

        # Storage
        storage_path = f"{folder_prefix}/{filename}"
        try:
            try:
                client.storage.from_('documentos').upload(storage_path, content)
            except Exception as se:
                if 'already exists' in str(se).lower():
                    logger.warning(f"[Storage] {filename} já existe, ignorando.")
                else:
                    raise
        except Exception as e:
            logger.exception(f"[Storage] falhou {filename}: {e}")

        # DB record
        try:
            client.table('documentos').insert({
                'nome_original': filename,
                'storage_path': storage_path,
                'tipo': tipo,
                'status': new_status,
                'empresa_id': empresa_id,
            }).execute()
        except Exception as e:
            logger.exception(f"[Documentos] erro db {filename}: {e}")

    return redirect(url_for('documentos.index'))

from flask import Blueprint, render_template, request, jsonify, session, flash, redirect, url_for, Response
import time
from app.web.routes.decorators import login_required
from app.infrastructure.supabase.client import db_adapter
from app.infrastructure.logger import logger

bp = Blueprint('plano_contas', __name__)

@bp.route('/plano-contas')
@login_required
def index():
    client = db_adapter.get_client()
    active_empresa = session.get('active_empresa', {})
    
    if not active_empresa:
        return redirect(url_for('documentos.index'))
        
    contas = []
    if client:
        try:
            # Busca todas as contas ordenadas pelo código
            resp = client.table('plano_contas') \
                         .select('*') \
                         .eq('empresa_id', active_empresa['id']) \
                         .order('codigo_estrutural') \
                         .execute()
            contas = resp.data or []
        except Exception as e:
            logger.error(f"Erro ao buscar plano de contas: {e}")
            flash(f"Erro ao carregar o plano de contas: {e}", "error")

    return render_template('plano_contas.html', contas=contas)

@bp.route('/plano-contas', methods=['POST'])
@login_required
def save_conta():
    """Adiciona ou atualiza uma conta no plano de contas."""
    active_empresa = session.get('active_empresa', {})
    if not active_empresa:
        return jsonify({'ok': False, 'message': 'Empresa não selecionada'}), 400
        
    data = request.get_json(silent=True) or {}
    codigo = data.get('codigo', '').strip()
    nome = data.get('nome', '').strip()
    tipo = data.get('tipo', '').strip().upper()
    natureza = data.get('natureza', '').strip().upper()
    
    if not codigo or not nome:
        return jsonify({'ok': False, 'message': 'Código e Nome são obrigatórios'}), 400
        
    # Calcular nivel baseado na quantia de pontos ou tamanho
    nivel = len(codigo.replace('.', ''))
    
    client = db_adapter.get_client()
    if not client:
         return jsonify({'ok': False, 'message': 'Erro de conexão BD'}), 500

    payload = {
        'empresa_id': active_empresa['id'],
        'codigo': codigo,
        'codigo_estrutural': codigo,
        'nome': nome,
        'descricao': nome,
        'tipo': tipo if tipo in ('DEBITO', 'CREDITO') else None,
        'natureza': natureza if natureza in ('ATIVO', 'PASSIVO', 'RECEITA', 'DESPESA') else None,
        'nivel': nivel
    }
    
    conta_id = data.get('id')
    try:
        if conta_id:
            # Update
            client.table('plano_contas').update(payload).eq('id', conta_id).execute()
        else:
            # Insert
            client.table('plano_contas').insert(payload).execute()
            
        return jsonify({'ok': True, 'message': 'Conta salva com sucesso!'})
    except Exception as e:
        logger.error(f"Erro ao salvar conta: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500

@bp.route('/plano-contas/importar', methods=['POST'])
@login_required
def importar_plano():
    """Importa o Plano de Contas via PDF usando IA."""
    active_empresa = session.get('active_empresa', {})
    if not active_empresa:
        return jsonify({'ok': False, 'message': 'Empresa não selecionada'}), 400

    if 'file' not in request.files:
        return jsonify({'ok': False, 'message': 'Nenhum arquivo enviado.'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'ok': False, 'message': 'Arquivo inválido.'}), 400

    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'ok': False, 'message': 'Apenas arquivos PDF são suportados para importação automática.'}), 400

    file_bytes = file.read()

    def generate():
        import json
        from app.application.services.plan_parser import parse_plano_contas_pdf_stream
        
        try:
            contas_extraidas = []
            
            # Consume the service generator
            for event in parse_plano_contas_pdf_stream(file_bytes):
                if event['status'] == 'progress':
                    yield f"data: {json.dumps({'status': 'progress', 'msg': event['msg']})}\n\n"
                elif event['status'] == 'error':
                    yield f"data: {json.dumps({'status': 'error', 'message': event['erro']})}\n\n"
                    return
                elif event['status'] == 'final_data':
                    contas_extraidas = event.get('contas', [])
                    break
            
            if not contas_extraidas:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Nenhuma conta lida até o final do processo.'})}\n\n"
                return

            yield f"data: {json.dumps({'status': 'progress', 'msg': f'Etapa Semântica finalizada! Total de contas agrupadas: {len(contas_extraidas)}.'})}\n\n"
            yield f"data: {json.dumps({'status': 'progress', 'msg': f'Preparando modelagem de Banco de Dados com Supabase...'})}\n\n"

            client = db_adapter.get_client()
            if not client:
                yield f"data: {json.dumps({'status': 'error', 'message': 'Erro de conexão no banco de dados.'})}\n\n"
                return

            # ─── NOVO: Limpeza prévia para evitar erro de Duplicidade (23505) ───
            try:
                yield f"data: {json.dumps({'status': 'progress', 'msg': 'Limpando estrutura antiga da empresa para nova importação...'})}\n\n"
                # Remove contas existentes desta empresa
                client.table('plano_contas').delete().eq('empresa_id', active_empresa['id']).execute()
            except Exception as del_err:
                logger.warning(f"[Import Plan] Falha ao limpar contas antigas (podem haver vínculos): {del_err}")
                # Não interrompemos aqui, pois o insert falhará naturalmente se houver duplicata real não removível

            payload_map = {}
            for conta in contas_extraidas:
                codigo = str(conta.get('codigo', '')).strip()
                if not codigo: continue
                # Fix: Level calculation
                nivel = len(codigo.split('.')) if '.' in codigo else len(codigo.replace('.', ''))
                
                # Deduplicar aqui mesmo se a IA extraiu repetido em blocos diferentes
                payload_map[codigo] = {
                    'empresa_id': active_empresa['id'],
                    'codigo': codigo,
                    'codigo_estrutural': codigo,
                    'nome': str(conta.get('nome', conta.get('descricao', ''))).strip(),
                    'descricao': str(conta.get('nome', conta.get('descricao', ''))).strip(),
                    'tipo': conta.get('tipo', 'DEBITO') if str(conta.get('tipo')).upper() in ('DEBITO', 'CREDITO') else None,
                    'natureza': conta.get('natureza') if str(conta.get('natureza')).upper() in ('ATIVO', 'PASSIVO', 'RECEITA', 'DESPESA') else None,
                    'nivel': nivel
                }

            payload = list(payload_map.values())

            yield f"data: {json.dumps({'status': 'progress', 'msg': 'Formatado local, enviando INSERT em lote definitivo...'})}\n\n"
            
            # Since Supabase insert could be big, we chunk it over 200 items maybe? Supabase supports up to 1000 typically
            import math
            batch_size = 300
            total_batches = math.ceil(len(payload)/batch_size)
            
            for index in range(total_batches):
                b_slice = payload[index*batch_size : (index+1)*batch_size]
                # Usamos upsert com on_conflict para lidar com contas que já existem (e podem estar vinculadas)
                client.table('plano_contas').upsert(b_slice, on_conflict='empresa_id,codigo_estrutural').execute()
                yield f"data: {json.dumps({'status': 'progress', 'msg': f'Pacote SQL {index+1}/{total_batches} processado.'})}\n\n"

            # ─── NOVO: Salvar o PDF no Storage e na tabela de documentos ───
            from app.web.routes.documentos import slugify
            folder_prefix = slugify(active_empresa.get('nome','')) or active_empresa['id']
            filename = f"PLANO_CONTAS_{int(time.time())}.pdf"
            storage_path = f"{folder_prefix}/{filename}"
            
            try:
                yield f"data: {json.dumps({'status': 'progress', 'msg': 'Salvando cópia do PDF no Storage do Supabase...'})}\n\n"
                client.storage.from_('documentos').upload(storage_path, file_bytes)
                
                client.table('documentos').insert({
                    'empresa_id': active_empresa['id'],
                    'nome_original': filename,
                    'storage_path': storage_path,
                    'tipo': 'pdf',
                    'status': 'concluido'
                }).execute()
            except Exception as st_err:
                logger.warning(f"[Import Plan] Erro ao salvar arquivo no storage: {st_err}")

            yield f"data: {json.dumps({'status': 'success', 'message': f'{len(payload)} contas importadas rigorosamente!'})}\n\n"

        except Exception as e:
            logger.exception(f"[Import Plan] Erro na stream: {e}")
            yield f"data: {json.dumps({'status': 'error', 'message': f'Erro interno do servidor: {e}'})}\n\n"

    return Response(generate(), mimetype='text/event-stream')



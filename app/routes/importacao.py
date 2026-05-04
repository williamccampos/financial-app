from flask import Blueprint, request, jsonify
import csv
import io
from app.database import db_connection
from app.utils import erro_json, validar_csrf, login_required, get_current_user_id

bp = Blueprint('importacao', __name__)


@bp.route('/importar/csv', methods=['POST'])
@login_required
def importar_csv():
    if not validar_csrf():
        return erro_json('CSRF inválido.', 403)
    file = request.files.get('arquivo')
    if not file or not file.filename:
        return erro_json('Arquivo é obrigatório.', 400)
    if not file.filename.lower().endswith('.csv'):
        return erro_json('Apenas arquivos CSV são aceitos.', 400)
    conta_id = request.form.get('conta_id') or None
    user_id = get_current_user_id()
    try:
        content = file.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(content))
        count = 0
        with db_connection() as conn:
            for row in reader:
                data_val = (row.get('data') or row.get('Data') or row.get('date') or '').strip()
                descricao = (row.get('descricao') or row.get('Descrição') or row.get('description') or row.get('Descricao') or '').strip()
                valor_str = (row.get('valor') or row.get('Valor') or row.get('amount') or '0').strip()
                valor_str = valor_str.replace('.', '').replace(',', '.') if ',' in valor_str else valor_str
                try:
                    valor = abs(float(valor_str))
                except (ValueError, TypeError):
                    continue
                if not data_val or not descricao or valor <= 0:
                    continue
                raw = (row.get('valor') or row.get('Valor') or row.get('amount') or '0').strip()
                tipo = 'saida' if raw.startswith('-') else 'entrada'
                categoria = (row.get('categoria') or row.get('Categoria') or row.get('category') or '').strip()
                conn.execute("INSERT INTO lancamentos (user_id, data, tipo, descricao, valor, categoria, vencimento, recorrente, parcelas, parcela_atual, conta_id) VALUES (?,?,?,?,?,?,'',0,1,1,?)",
                    (user_id, data_val, tipo, descricao, valor, categoria, conta_id))
                count += 1
    except Exception as e:
        return erro_json(f'Erro ao processar: {str(e)}', 400)
    return jsonify({'status': 'ok', 'importados': count})

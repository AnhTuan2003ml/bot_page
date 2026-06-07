import json
from urllib.parse import unquote

from database.dynamic_table_manager import ensure_dynamic_table, sanitize_table_name
from database.expertise_manager import create_expertise, delete_expertise, get_expertise, list_expertises, update_expertise
from services.runtime_context import clear_skill_context, clear_page_context


def _fields_from_payload(data):
    fields = data.get('fields') or []
    if fields and isinstance(fields, list):
        normalized = []
        for idx, f in enumerate(fields):
            if isinstance(f, str):
                label = f.strip()
                key = label.lower().replace(' ', '_')
            else:
                label = f.get('field_label') or f.get('label') or f.get('field_key') or f.get('key') or f'Field {idx+1}'
                key = f.get('field_key') or f.get('key') or str(label).lower().replace(' ', '_')
            if label:
                normalized.append({'key': key, 'label': label, 'required': bool(f.get('required')) if isinstance(f, dict) else False})
        return normalized
    raw = data.get('data_fields_json') or '[]'
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def _persona_from_payload(data):
    # persona_json is the main config, but the UI has separate fields for
    # Tên chuyên môn and Tên nhân vật.  Keep those fields authoritative so
    # typing character_name='Linh' does not get overwritten by the expertise name.
    raw = data.get('persona_json')
    if raw:
        try:
            persona = json.loads(raw) if isinstance(raw, str) else (raw or {})
            if not isinstance(persona, dict):
                persona = {}
        except Exception:
            persona = {}
    else:
        persona = {}

    thong_tin = persona.get('thong_tin') if isinstance(persona.get('thong_tin'), dict) else {}
    character_name = (data.get('character_name') or '').strip()
    expertise_name = (data.get('name') or '').strip()
    description = data.get('description') or ''

    if character_name:
        thong_tin['ten'] = character_name
    elif not thong_tin.get('ten'):
        thong_tin['ten'] = ''
    if expertise_name:
        thong_tin['vai_tro'] = expertise_name
    if description:
        thong_tin['mo_ta'] = description
    persona['thong_tin'] = thong_tin

    persona.setdefault('tinh_cach', {'mo_ta': data.get('personality') or '', 'cach_noi_chuyen': []})
    persona.setdefault('xung_ho', {
        'bat_buoc_xac_dinh': True,
        'mac_dinh': 'A/C',
        'cau_hoi': 'Dạ em nên xưng hô với mình là anh hay chị để tư vấn cho tiện ạ?',
    })
    persona.setdefault('quy_trinh_lam_viec', str(data.get('workflow_prompt') or '').splitlines())
    persona.setdefault('quy_tac_phan_tich', [data.get('intent_prompt')] if data.get('intent_prompt') else [])
    persona.setdefault('quy_tac_phan_hoi', [])
    persona.setdefault('tach_tin_nhan', {'delimiter': '---MSG---'})
    persona.setdefault('prompt', {'phan_tich': '', 'tra_loi': data.get('system_prompt') or ''})

    if data.get('skill_id'):
        persona['legacy_skill_id'] = data.get('skill_id')
    return json.dumps(persona, ensure_ascii=False)


def _legacy_item(e):
    try:
        fields = json.loads(e.get('data_fields_json') or '[]')
    except Exception:
        fields = []
    try:
        persona = json.loads(e.get('persona_json') or '{}')
    except Exception:
        persona = {}
    legacy_id = str(persona.get('legacy_skill_id') or e['id'])
    return {
        'id': e['id'],
        'skill_id': legacy_id,
        'name': e.get('name') or '',
        'description': e.get('description') or e.get('job_title') or '',
        'character_name': (persona.get('thong_tin') or {}).get('ten') or e.get('name') or '',
        'personality': (persona.get('tinh_cach') or {}).get('mo_ta') or '',
        'system_prompt': (persona.get('prompt') or {}).get('tra_loi') or '',
        'target_description': e.get('description') or '',
        'workflow_prompt': json.dumps(persona.get('quy_trinh_lam_viec') or [], ensure_ascii=False),
        'intent_prompt': json.dumps(persona.get('quy_tac_phan_tich') or [], ensure_ascii=False),
        'business_domain': '',
        'rag_content': e.get('training_content') or '',
        'rag_file_path': '',
        'training_content': e.get('training_content') or '',
        'persona_json': e.get('persona_json') or '{}',
        'data_table': e.get('data_table') or '',
        'data_fields_json': e.get('data_fields_json') or '[]',
        'fields': [{'field_key': f.get('key') or f.get('field_key') or f.get('label'), 'field_label': f.get('label') or f.get('field_label') or f.get('key'), 'field_type': 'text', 'required': bool(f.get('required'))} for f in fields if isinstance(f, dict)],
    }


def list_skills():
    try:
        return {'success': True, 'skills': [_legacy_item(e) for e in list_expertises()]}, 200
    except Exception as exc:
        return {'success': False, 'error': str(exc)}, 500


def add_skill(data):
    data = data or {}
    try:
        name = (data.get('name') or '').strip()
        if not name:
            return {'success': False, 'error': 'Tên chuyên môn là bắt buộc'}, 400
        fields = _fields_from_payload(data)
        table = data.get('data_table') or data.get('skill_id') or data.get('name')
        table = ensure_dynamic_table(table)
        expertise_id = create_expertise({
            'name': name,
            'job_title': data.get('description') or name,
            'description': data.get('description') or '',
            'persona_json': _persona_from_payload(data),
            'training_content': data.get('training_content') or data.get('rag_content') or '',
            'data_table': table,
            'data_fields_json': json.dumps(fields, ensure_ascii=False),
        })
        clear_skill_context()
        return {'success': True, 'message': 'Đã tạo chuyên môn AI', 'id': expertise_id}, 200
    except Exception as exc:
        return {'success': False, 'error': str(exc)}, 500


def update_skill(name, data):
    data = data or {}
    try:
        e = get_expertise(unquote(name))
        if not e:
            return {'success': False, 'error': 'Không tìm thấy chuyên môn'}, 404
        fields = _fields_from_payload(data)
        table = data.get('data_table') or e.get('data_table') or data.get('skill_id') or data.get('name')
        table = ensure_dynamic_table(table)
        update_expertise(e['id'], {
            'name': data.get('name') or e['name'],
            'job_title': data.get('description') or e.get('job_title') or '',
            'description': data.get('description') if data.get('description') is not None else e.get('description'),
            'persona_json': _persona_from_payload(data),
            'training_content': data.get('training_content') if data.get('training_content') is not None else data.get('rag_content', e.get('training_content') or ''),
            'data_table': table,
            'data_fields_json': json.dumps(fields, ensure_ascii=False) if fields else e.get('data_fields_json') or '[]',
        })
        clear_skill_context()
        return {'success': True, 'message': 'Đã cập nhật chuyên môn AI'}, 200
    except Exception as exc:
        return {'success': False, 'error': str(exc)}, 500


def delete_skill(name):
    try:
        e = get_expertise(unquote(name))
        if not e:
            return {'success': False, 'error': 'Không tìm thấy chuyên môn'}, 404
        delete_expertise(e['id'])
        clear_skill_context()
        return {'success': True, 'message': 'Đã xóa chuyên môn AI'}, 200
    except Exception as exc:
        return {'success': False, 'error': str(exc)}, 500


def toggle_skill(name):
    return {'success': True, 'message': 'Không dùng trạng thái bật/tắt'}, 200


def get_skill_fields(skill_name):
    e = get_expertise(unquote(skill_name))
    if not e:
        return {'success': True, 'fields': [], 'templates': {}}, 200
    return {'success': True, 'fields': _legacy_item(e)['fields'], 'templates': {}}, 200


def get_skill_field_templates():
    return {'success': True, 'templates': {}}, 200


def save_skill_fields(skill_name, fields):
    e = get_expertise(unquote(skill_name))
    if not e:
        return {'success': False, 'error': 'Không tìm thấy chuyên môn'}, 404
    normalized = []
    for f in fields or []:
        normalized.append({'key': f.get('field_key') or f.get('key') or f.get('field_label'), 'label': f.get('field_label') or f.get('label') or f.get('field_key'), 'required': bool(f.get('required'))})
    update_expertise(e['id'], {'data_fields_json': json.dumps(normalized, ensure_ascii=False)})
    return {'success': True, 'fields': _legacy_item(get_expertise(e['id']))['fields']}, 200

# Keep item endpoints but route to dynamic table manager.
def _content_from_payload(payload):
    payload = payload or {}
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    if 'content' in data:
        return data.get('content') or ''
    lines = []
    for k, v in data.items():
        if k in {'id', 'item_id'}:
            continue
        lines.append(f'{k}: {v}')
    return '\n'.join(lines)

def _row_id_from_payload(payload):
    payload = payload or {}
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    return data.get('id') or data.get('item_id') or data.get('ma_bien') or data.get('ma_sp') or data.get('code') or data.get('name')

def list_skill_items(skill_name, args):
    from database.dynamic_table_manager import list_dynamic_rows
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': True, 'items': [], 'total': 0}, 200
    rows = list_dynamic_rows(e['data_table'], query=(args or {}).get('query'), limit=int((args or {}).get('page_size', 200)))
    return {'success': True, 'items': [{'id': r['id'], 'data': {'id': r['id'], 'content': r['content']}, 'content': r['content']} for r in rows], 'total': len(rows)}, 200

def create_skill_item(skill_name, data):
    from database.dynamic_table_manager import upsert_dynamic_row
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False, 'errors': ['Chuyên môn chưa có bảng dữ liệu']}, 400
    row_id = _row_id_from_payload(data)
    if not row_id:
        return {'success': False, 'errors': ['Thiếu ID dữ liệu']}, 400
    upsert_dynamic_row(e['data_table'], row_id, _content_from_payload(data))
    return {'success': True, 'item': {'id': row_id}}, 200

def update_skill_item(skill_name, item_id, data):
    from database.dynamic_table_manager import upsert_dynamic_row
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False, 'errors': ['Chuyên môn chưa có bảng dữ liệu']}, 400
    upsert_dynamic_row(e['data_table'], str(item_id), _content_from_payload(data))
    return {'success': True}, 200

def delete_skill_item(skill_name, item_id):
    from database.dynamic_table_manager import delete_dynamic_row
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False}, 404
    return {'success': delete_dynamic_row(e['data_table'], str(item_id))}, 200

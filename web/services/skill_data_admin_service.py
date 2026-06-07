import json
from urllib.parse import unquote

from database.dynamic_table_manager import delete_dynamic_row, list_dynamic_rows, upsert_dynamic_row
from database.expertise_manager import get_expertise, list_expertises, update_expertise
from services import cache_service
from services.runtime_context import clear_skill_context


def _legacy_skill(e):
    try:
        persona = json.loads(e.get('persona_json') or '{}')
    except Exception:
        persona = {}
    return {
        'id': e['id'],
        'skill_id': str(persona.get('legacy_skill_id') or e['id']),
        'name': e.get('name') or '',
        'description': e.get('description') or e.get('job_title') or '',
        'data_table': e.get('data_table') or '',
        'data_fields_json': e.get('data_fields_json') or '[]',
    }


def _fields(e):
    try:
        arr = json.loads(e.get('data_fields_json') or '[]')
    except Exception:
        arr = []
    fields = []
    for idx, f in enumerate(arr if isinstance(arr, list) else []):
        if isinstance(f, str):
            key = f; label = f
        else:
            key = f.get('key') or f.get('field_key') or f.get('label') or f'field_{idx+1}'
            label = f.get('label') or f.get('field_label') or key
        fields.append({'field_key': key, 'field_label': label, 'field_type': 'text', 'required': bool(f.get('required')) if isinstance(f, dict) else False, 'display_order': idx})
    return fields


def _row_to_item(row, e):
    data = {'id': row.get('id'), 'content': row.get('content') or ''}
    fields = _fields(e) if e else []
    if fields:
        # The first/required field is the natural row id.
        id_key = _field_id_key(e) or fields[0].get('field_key')
        if id_key:
            data[id_key] = row.get('id')
        # Parse content lines of the form "Label: value" back into field values
        # so edit form/display can reuse existing data.
        label_to_key = {}
        for f in fields:
            label_to_key[str(f.get('field_label') or '').strip()] = f.get('field_key')
            label_to_key[str(f.get('field_key') or '').strip()] = f.get('field_key')
        for line in str(row.get('content') or '').splitlines():
            if ':' not in line:
                continue
            label, value = line.split(':', 1)
            key = label_to_key.get(label.strip())
            if key:
                data[key] = value.strip()
    return {'id': row.get('id'), 'data': data, 'content': row.get('content') or ''}


def _find_skill(selected_skill):
    selected_skill = unquote(selected_skill or '').strip()
    if selected_skill:
        e = get_expertise(selected_skill)
        if e:
            return e
    items = list_expertises()
    return items[0] if items else {}


def get_skill_data_page_context(selected_skill=None):
    skills = [_legacy_skill(e) for e in list_expertises()]
    e = _find_skill(selected_skill)
    rows = []
    if e and e.get('data_table'):
        rows = list_dynamic_rows(e['data_table'], limit=200)
    return {
        'skills': skills,
        'skill_name': str(e.get('id') or ''),
        'selected_skill': _legacy_skill(e) if e else {},
        'selected_skill_label': e.get('name') if e else '',
        'skill': _legacy_skill(e) if e else {},
        'fields': _fields(e) if e else [],
        'items': [_row_to_item(r, e) for r in rows],
        'items_total': len(rows),
    }


def api_get_fields(skill_name):
    e = get_expertise(unquote(skill_name))
    return {'success': True, 'fields': _fields(e) if e else []}, 200


def api_save_fields(skill_name, payload):
    e = get_expertise(unquote(skill_name))
    if not e:
        return {'success': False, 'errors': ['Không tìm thấy chuyên môn']}, 404
    payload = payload or {}
    raw_fields = payload.get('fields') or []
    if payload.get('quick_text') is not None:
        parts = [p.strip() for p in str(payload.get('quick_text') or '').replace(',', '\n').splitlines() if p.strip()]
        raw_fields = [{'key': p.lower().replace(' ', '_'), 'label': p, 'required': False} for p in parts]
    normalized = []
    for f in raw_fields:
        normalized.append({'key': f.get('key') or f.get('field_key') or f.get('label'), 'label': f.get('label') or f.get('field_label') or f.get('key'), 'required': bool(f.get('required'))})
    update_expertise(e['id'], {'data_fields_json': json.dumps(normalized, ensure_ascii=False)})
    clear_skill_context(str(e['id']))
    return {'success': True, 'fields': _fields(get_expertise(e['id']))}, 200


def api_get_items(skill_name, args):
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': True, 'fields': [], 'items': [], 'total': 0, 'page': 1, 'page_size': 200}, 200
    rows = list_dynamic_rows(e['data_table'], query=(args or {}).get('query'), limit=int((args or {}).get('page_size', 200)))
    return {'success': True, 'fields': _fields(e), 'items': [_row_to_item(r, e) for r in rows], 'total': len(rows), 'page': 1, 'page_size': 200}, 200


def _data(payload):
    payload = payload or {}
    if isinstance(payload.get('data'), dict):
        data = dict(payload.get('data') or {})
        # UI sends the dynamic row id explicitly next to data. Keep it in the
        # data dict so legacy and new backends can resolve it consistently.
        if payload.get('id') not in (None, '') and data.get('id') in (None, ''):
            data['id'] = payload.get('id')
        return data
    return payload


def _field_id_key(e=None):
    fields = _fields(e) if e else []
    required = [f for f in fields if f.get('required') or f.get('is_required')]
    chosen = (required or fields or [{}])[0]
    return chosen.get('field_key') or chosen.get('key') or ''


def _row_id(d, e=None):
    """Return the row id for the dynamic data table.

    New data tables only have (id, content). The UI renders fields from
    expertises.data_fields_json; therefore the first declared field is the
    natural row id (for example: Mã biển, Mã sản phẩm, Mã dịch vụ).
    Do not require hard-coded legacy names such as ma_bien/ma_sp.
    """
    if not isinstance(d, dict):
        return ''

    # Explicit/common id keys first.
    for key in ('id', 'item_id', 'ma_bien', 'bien_so', 'ma_sp', 'product_code', 'sku', 'code', 'name'):
        value = d.get(key)
        if value not in (None, ''):
            return str(value).strip()

    # Then use the first field declared for this expertise. Prefer required.
    fields = _fields(e) if e else []
    ordered = [f for f in fields if f.get('required')] + [f for f in fields if not f.get('required')]
    for field in ordered:
        key = field.get('field_key')
        value = d.get(key)
        if value not in (None, ''):
            return str(value).strip()

    # Final fallback: first non-empty scalar in the payload.
    for value in d.values():
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ''


def _content(d, e=None):
    # If the UI sends explicit raw content only, keep it.
    if 'content' in d and len([k for k in d.keys() if k not in {'id', 'item_id'}]) <= 1:
        return d.get('content') or ''

    # Build human-readable content using field labels from data_fields_json.
    labels = {f.get('field_key'): f.get('field_label') or f.get('field_key') for f in (_fields(e) if e else [])}
    lines = []
    for k, v in d.items():
        if k in {'item_id'}:
            continue
        # Keep the natural ID field in content too, because users expect
        # content to contain Mã biển/Mã sản phẩm as part of the record.
        if v is None or v == '':
            continue
        label = labels.get(k, k)
        lines.append(f'{label}: {v}')
    return '\n'.join(lines)


def api_create_item(skill_name, payload):
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False, 'errors': ['Chuyên môn chưa có bảng dữ liệu']}, 400
    d = _data(payload)
    rid = _row_id(d, e)
    if not rid:
        return {'success': False, 'errors': ['Thiếu ID dữ liệu']}, 400
    upsert_dynamic_row(e['data_table'], rid, _content(d, e))
    return {'success': True, 'item': {'id': rid}}, 200


def api_update_item(skill_name, item_id, payload):
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False, 'errors': ['Chuyên môn chưa có bảng dữ liệu']}, 400
    d = _data(payload)
    upsert_dynamic_row(e['data_table'], str(item_id), _content(d, e))
    return {'success': True}, 200


def api_delete_item(skill_name, item_id):
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False, 'error': 'Không tìm thấy dữ liệu'}, 404
    ok = delete_dynamic_row(e['data_table'], str(item_id))
    return {'success': ok}, 200 if ok else 404


def api_get_item(skill_name, item_id):
    e = get_expertise(unquote(skill_name))
    if not e or not e.get('data_table'):
        return {'success': False, 'error': 'Không tìm thấy dữ liệu'}, 404
    rows = [r for r in list_dynamic_rows(e['data_table'], limit=10000) if str(r['id']) == str(item_id)]
    if rows:
        r = rows[0]
        return {'success': True, 'item': _row_to_item(r, e)}, 200
    return {'success': False, 'error': 'Không tìm thấy dữ liệu'}, 404

"""Compatibility facade: UI/Page still call skill_* names, but runtime data is Chuyên môn AI in expertises."""
import json
from typing import Dict, List, Optional

from database.expertise_manager import (
    create_expertise,
    delete_expertise,
    get_expertise,
    init_expertises_table,
    list_expertises,
    migrate_old_skills_to_expertises,
    update_expertise,
)
from database.dynamic_table_manager import ensure_dynamic_table, sanitize_table_name


def init_skills_table():
    init_expertises_table()
    migrate_old_skills_to_expertises()


def migrate_skills_from_files():
    # Old Python skill-file migration removed. Keep no-op so app import does not break.
    return None


def _fields_to_legacy(fields_json):
    try:
        fields = json.loads(fields_json or '[]')
    except Exception:
        fields = []
    out = []
    for idx, f in enumerate(fields if isinstance(fields, list) else []):
        if isinstance(f, str):
            key = f
            label = f
        else:
            key = f.get('key') or f.get('field_key') or f.get('label') or f'field_{idx+1}'
            label = f.get('label') or f.get('field_label') or key
        out.append({
            'field_key': key,
            'field_label': label,
            'field_type': 'text',
            'required': bool((f or {}).get('required')) if isinstance(f, dict) else False,
            'is_entity': 1,
            'display_order': idx,
        })
    return out


def _to_legacy_skill(e: Dict) -> Dict:
    if not e:
        return {}
    # page UI stores ai_skill as this string. New records use numeric id as string.
    try:
        persona = json.loads(e.get('persona_json') or '{}')
    except Exception:
        persona = {}
    legacy_id = str(persona.get('legacy_skill_id') or e.get('id'))
    return {
        'id': e.get('id'),
        'skill_id': legacy_id,
        'name': e.get('name') or '',
        'description': e.get('description') or e.get('job_title') or '',
        'system_prompt': (persona.get('prompt') or {}).get('tra_loi') or '',
        'character_name': (persona.get('thong_tin') or {}).get('ten') or e.get('name') or '',
        'personality': (persona.get('tinh_cach') or {}).get('mo_ta') or '',
        'business_domain': '',
        'target_description': e.get('description') or '',
        'workflow_prompt': json.dumps(persona.get('quy_trinh_lam_viec') or [], ensure_ascii=False),
        'intent_prompt': json.dumps(persona.get('quy_tac_phan_tich') or [], ensure_ascii=False),
        'use_products': 0,
        'use_plates': 0,
        'use_rag': 1 if e.get('training_content') else 0,
        'is_active': 1,
        'persona_json': e.get('persona_json') or '{}',
        'training_content': e.get('training_content') or '',
        'rag_content': e.get('training_content') or '',
        'rag_file_path': '',
        'data_table': e.get('data_table') or '',
        'data_fields_json': e.get('data_fields_json') or '[]',
        'fields': _fields_to_legacy(e.get('data_fields_json')),
    }


def get_all_skills() -> List[Dict]:
    init_skills_table()
    return [_to_legacy_skill(e) for e in list_expertises()]


def get_skill_by_name(name) -> Optional[Dict]:
    e = get_expertise(name)
    return _to_legacy_skill(e) if e else None


def add_skill(skill_id=None, name=None, description='', system_prompt=None, character_name='', personality='', business_domain='', target_description='', workflow_prompt='', intent_prompt='', use_products=0, use_plates=0, use_rag=1, persona_json=None, training_content=None, data_table=None, data_fields_json=None):
    name = name or character_name or skill_id
    if not name:
        return False
    persona = None
    if persona_json:
        try:
            persona = json.loads(persona_json) if isinstance(persona_json, str) else persona_json
        except Exception:
            persona = None
    if persona is None:
        persona = {
            'legacy_skill_id': skill_id or '',
            'thong_tin': {'ten': character_name or name, 'vai_tro': description or name, 'mo_ta': description or ''},
            'tinh_cach': {'mo_ta': personality or '', 'cach_noi_chuyen': []},
            'xung_ho': {'bat_buoc_xac_dinh': True, 'mac_dinh': 'A/C', 'cau_hoi': 'Dạ em nên xưng hô với mình là anh hay chị để tư vấn cho tiện ạ?'},
            'quy_trinh_lam_viec': workflow_prompt.splitlines() if isinstance(workflow_prompt, str) else [],
            'quy_tac_phan_tich': [intent_prompt] if intent_prompt else [],
            'quy_tac_phan_hoi': [],
            'tach_tin_nhan': {'delimiter': '---MSG---'},
            'prompt': {'tra_loi': system_prompt or '', 'phan_tich': ''},
        }
    table = data_table or sanitize_table_name(description or name)
    try:
        table = ensure_dynamic_table(table)
        create_expertise({
            'name': name,
            'job_title': description or '',
            'description': description or '',
            'persona_json': json.dumps(persona, ensure_ascii=False),
            'training_content': training_content or '',
            'data_table': table,
            'data_fields_json': data_fields_json or '[]',
        })
        return True
    except Exception as exc:
        print(f'[EXPERTISE] add error={exc}')
        return False


def update_skill(old_name, **kwargs):
    e = get_expertise(old_name)
    if not e:
        return False
    data = {}
    if kwargs.get('name') is not None:
        data['name'] = kwargs.get('name')
    if kwargs.get('description') is not None:
        data['job_title'] = kwargs.get('description')
        data['description'] = kwargs.get('description')
    if kwargs.get('persona_json') is not None:
        data['persona_json'] = kwargs.get('persona_json')
    if kwargs.get('training_content') is not None:
        data['training_content'] = kwargs.get('training_content')
    if kwargs.get('data_table') is not None:
        data['data_table'] = ensure_dynamic_table(kwargs.get('data_table'))
    if kwargs.get('data_fields_json') is not None:
        data['data_fields_json'] = kwargs.get('data_fields_json')
    return update_expertise(e['id'], data)


def delete_skill(name):
    e = get_expertise(name)
    return delete_expertise(e['id']) if e else False


def toggle_skill(name):
    return True


def get_skill_rag_source(skill_name):
    skill = get_skill_by_name(skill_name) or {}
    return {'content': skill.get('training_content') or '', 'file_path': '', 'source_type': 'training_content'} if skill else {}


def upsert_skill_rag_source(skill_name, name='Tài liệu đào tạo', content='', file_path=None, source_type='training_content'):
    e = get_expertise(skill_name)
    if not e:
        return ''
    update_expertise(e['id'], {'training_content': content or ''})
    return ''


def read_skill_rag_content(skill_name):
    return (get_skill_rag_source(skill_name) or {}).get('content') or ''


def disable_skill_rag_source(skill_name):
    e = get_expertise(skill_name)
    if e:
        update_expertise(e['id'], {'training_content': ''})
    return True

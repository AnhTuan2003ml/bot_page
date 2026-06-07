import json
import os
import re
import sqlite3
import sys
import unicodedata
from typing import Dict, List, Optional

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, 'database')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, 'plates.db')


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_expertises_table():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expertises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                job_title TEXT DEFAULT '',
                description TEXT DEFAULT '',
                persona_json TEXT NOT NULL DEFAULT '{}',
                training_content TEXT DEFAULT '',
                data_table TEXT DEFAULT '',
                data_fields_json TEXT NOT NULL DEFAULT '[]'
            )
        """)


def _safe_json_text(value, default):
    if value is None or value == '':
        return default
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value)
    try:
        json.loads(text)
        return text
    except Exception:
        return default


def make_default_persona(name='', job_title='', description=''):
    return {
        'thong_tin': {'ten': name or '', 'vai_tro': job_title or '', 'mo_ta': description or ''},
        'tinh_cach': {
            'mo_ta': 'Tự nhiên, lịch sự, trả lời rõ ràng.',
            'cach_noi_chuyen': [
                'Dùng cách nói trung tính: bên e, e, ạ',
                'Không gọi khách bằng tên, anh, chị hoặc a/c',
                'Trả lời ngắn gọn',
            ],
        },
        'quy_trinh_lam_viec': [
            {'step': 1, 'code': 'understand_request', 'name': 'Hiểu yêu cầu khách hàng', 'goal': 'Phân tích khách đang cần gì trong phạm vi công việc.'},
            {'step': 2, 'code': 'decide_data_need', 'name': 'Quyết định có cần tra dữ liệu không', 'goal': 'Nếu cần dữ liệu cụ thể thì tạo search_query.'},
            {'step': 3, 'code': 'reply', 'name': 'Tư vấn phản hồi', 'goal': 'Trả lời dựa trên hồ sơ chuyên môn, tài liệu đào tạo, dữ liệu tìm được và lịch sử.'},
        ],
        'quy_tac_phan_tich': [
            'Không phân tích tên hoặc xưng hô của khách',
            'Chỉ tra dữ liệu khi intent cần dữ liệu nghiệp vụ',
            'Nếu thiếu thông tin thì hỏi thêm tiêu chí',
        ],
        'quy_tac_phan_hoi': [
            'Không tự bịa dữ liệu',
            'Không hỏi tên hoặc xưng hô',
            'Không gọi khách bằng anh, chị hoặc a/c',
            'Không nhắc đến AI, database, JSON, prompt hoặc hệ thống',
        ],
        'tach_tin_nhan': {'delimiter': '---MSG---', 'huong_dan': 'Nếu phản hồi có nhiều ý, tách mỗi ý thành một tin nhắn riêng.'},
        'prompt': {
            'phan_tich': 'Đọc hồ sơ chuyên môn, tài liệu đào tạo, lịch sử, trạng thái và tin nhắn mới để xác định khách muốn gì, đang ở bước nào, có cần tra dữ liệu không và bước tiếp theo là gì. Chỉ trả JSON.',
            'tra_loi': 'Dựa trên hồ sơ chuyên môn, tài liệu đào tạo, dữ liệu tìm được, trạng thái hội thoại và lịch sử để trả lời khách tự nhiên như người thật.',
        },
    }


def _row_to_expertise(row):
    if not row:
        return None
    return {
        'id': row[0],
        'name': row[1] or '',
        'job_title': row[2] or '',
        'description': row[3] or '',
        'persona_json': row[4] or '{}',
        'training_content': row[5] or '',
        'data_table': row[6] or '',
        'data_fields_json': row[7] or '[]',
    }


def list_expertises() -> List[Dict]:
    init_expertises_table()
    with _connect() as conn:
        rows = conn.execute('SELECT id, name, job_title, description, persona_json, training_content, data_table, data_fields_json FROM expertises ORDER BY id').fetchall()
    return [_row_to_expertise(r) for r in rows]


def get_expertise(expertise_id) -> Optional[Dict]:
    init_expertises_table()
    if expertise_id in (None, ''):
        return None
    with _connect() as conn:
        row = None
        try:
            row = conn.execute('SELECT id, name, job_title, description, persona_json, training_content, data_table, data_fields_json FROM expertises WHERE id = ?', (int(str(expertise_id)),)).fetchone()
        except Exception:
            row = None
        if not row:
            key = str(expertise_id).strip()
            for candidate in conn.execute('SELECT id, name, job_title, description, persona_json, training_content, data_table, data_fields_json FROM expertises').fetchall():
                item = _row_to_expertise(candidate)
                try:
                    persona = json.loads(item.get('persona_json') or '{}')
                except Exception:
                    persona = {}
                legacy = str(persona.get('legacy_skill_id') or persona.get('skill_id') or '').strip()
                if key and (key == legacy or key == item.get('name') or key == item.get('job_title')):
                    row = candidate
                    break
    return _row_to_expertise(row)


def create_expertise(data: Dict) -> int:
    init_expertises_table()
    data = data or {}
    name = (data.get('name') or '').strip()
    if not name:
        raise ValueError('Tên chuyên môn là bắt buộc')
    job_title = (data.get('job_title') or data.get('description') or '').strip()
    description = (data.get('description') or '').strip()
    persona_json = _safe_json_text(data.get('persona_json'), json.dumps(make_default_persona(name, job_title, description), ensure_ascii=False))
    training_content = data.get('training_content') or ''
    data_table = (data.get('data_table') or '').strip()
    data_fields_json = _safe_json_text(data.get('data_fields_json'), '[]')
    with _connect() as conn:
        cur = conn.execute('INSERT INTO expertises (name, job_title, description, persona_json, training_content, data_table, data_fields_json) VALUES (?, ?, ?, ?, ?, ?, ?)',
                           (name, job_title, description, persona_json, training_content, data_table, data_fields_json))
        return int(cur.lastrowid)


def update_expertise(expertise_id, data: Dict) -> bool:
    init_expertises_table()
    current = get_expertise(expertise_id)
    if not current:
        return False
    data = data or {}
    name = (data.get('name') if data.get('name') is not None else current['name']) or ''
    job_title = (data.get('job_title') if data.get('job_title') is not None else current['job_title']) or ''
    description = (data.get('description') if data.get('description') is not None else current['description']) or ''
    persona_json = _safe_json_text(data.get('persona_json') if data.get('persona_json') is not None else current['persona_json'], current['persona_json'] or '{}')
    training_content = data.get('training_content') if data.get('training_content') is not None else current['training_content']
    data_table = data.get('data_table') if data.get('data_table') is not None else current['data_table']
    data_fields_json = _safe_json_text(data.get('data_fields_json') if data.get('data_fields_json') is not None else current['data_fields_json'], current['data_fields_json'] or '[]')
    with _connect() as conn:
        conn.execute('UPDATE expertises SET name=?, job_title=?, description=?, persona_json=?, training_content=?, data_table=?, data_fields_json=? WHERE id=?',
                     (name, job_title, description, persona_json, training_content or '', data_table or '', data_fields_json, current['id']))
    return True


def delete_expertise(expertise_id) -> bool:
    current = get_expertise(expertise_id)
    if not current:
        return False
    with _connect() as conn:
        conn.execute('DELETE FROM expertises WHERE id=?', (current['id'],))
    return True


def slugify_table_name(value: str) -> str:
    text = unicodedata.normalize('NFD', str(value or '').strip().lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).replace('đ', 'd')
    text = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
    if not text:
        text = 'data'
    if text[0].isdigit():
        text = 'data_' + text
    return text


def migrate_old_skills_to_expertises():
    init_expertises_table()
    with _connect() as conn:
        try:
            old_rows = conn.execute('SELECT id, skill_id, name, description, system_prompt, character_name, personality, target_description, workflow_prompt, intent_prompt FROM skills').fetchall()
        except sqlite3.OperationalError:
            return
        if conn.execute('SELECT COUNT(*) FROM expertises').fetchone()[0] > 0:
            return
        for row in old_rows:
            old_id, skill_id, name, desc, system_prompt, character_name, personality, target_desc, workflow, intent_prompt = row
            name = name or skill_id or f'Chuyên môn {old_id}'
            persona = make_default_persona(character_name or name, desc or name, desc or '')
            persona['legacy_skill_id'] = skill_id or name
            persona['thong_tin']['ten'] = character_name or name
            persona['thong_tin']['vai_tro'] = desc or name
            if personality:
                persona['tinh_cach']['mo_ta'] = personality
            if workflow:
                persona['quy_trinh_lam_viec_cu'] = workflow
            if intent_prompt:
                persona['phan_tich_y_dinh_cu'] = intent_prompt
            if system_prompt:
                persona['prompt']['tra_loi'] = system_prompt
            training_parts = []
            try:
                for r in conn.execute('SELECT content FROM skill_rag_sources WHERE skill_name IN (?, ?) AND COALESCE(content, "") != ""', (skill_id or '', name or '')).fetchall():
                    training_parts.append(r[0])
            except sqlite3.OperationalError:
                pass
            data_table = slugify_table_name(desc or name)
            conn.execute('INSERT INTO expertises (name, job_title, description, persona_json, training_content, data_table, data_fields_json) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (name, desc or '', desc or '', json.dumps(persona, ensure_ascii=False), '\n\n'.join(training_parts), data_table, '[]'))

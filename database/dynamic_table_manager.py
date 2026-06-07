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
DB_PATH = os.path.join(BASE_DIR, 'database', 'plates.db')
SYSTEM_TABLES = {'expertises','pages','customer_profiles','conversation_states','conversations','ai_providers','app_settings','sqlite_sequence'}


def _connect():
    return sqlite3.connect(DB_PATH)


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize('NFD', str(value or '').lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).replace('đ', 'd')
    text = re.sub(r'[^a-z0-9]+', ' ', text).strip()
    return re.sub(r'\s+', ' ', text)


def _compact(value: str) -> str:
    return re.sub(r'\s+', '', _normalize_text(value))


def _query_tokens(query: str) -> List[str]:
    q = _normalize_text(query)
    # Common Vietnamese user shorthand: oto / o to / ô tô
    if 'oto' in _compact(q):
        q = q + ' o to oto xe oto xe o to'
    tokens = [t for t in q.split() if len(t) >= 2]
    seen, out = set(), []
    for t in tokens:
        if t not in seen:
            out.append(t); seen.add(t)
    return out


def sanitize_table_name(name: str) -> str:
    text = unicodedata.normalize('NFD', str(name or '').strip().lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch)).replace('đ','d')
    text = re.sub(r'[^a-z0-9]+', '_', text).strip('_')
    if not text:
        raise ValueError('Tên bảng dữ liệu không được rỗng')
    if text[0].isdigit():
        text = 'data_' + text
    if text in SYSTEM_TABLES:
        raise ValueError('Tên bảng dữ liệu trùng bảng hệ thống')
    return text


def _quote_identifier(name: str) -> str:
    safe = sanitize_table_name(name)
    return '"' + safe.replace('"','') + '"'


def ensure_dynamic_table(table_name: str) -> str:
    safe = sanitize_table_name(table_name)
    with _connect() as conn:
        conn.execute(f'CREATE TABLE IF NOT EXISTS {_quote_identifier(safe)} (id TEXT PRIMARY KEY, content TEXT NOT NULL)')
    return safe


def list_dynamic_rows(table_name: str, query: Optional[str]=None, limit: int=200) -> List[Dict]:
    safe = ensure_dynamic_table(table_name)
    params = []
    where = ''
    if query:
        where = 'WHERE id LIKE ? OR content LIKE ?'
        like = f'%{query}%'
        params.extend([like, like])
    params.append(int(limit or 200))
    with _connect() as conn:
        rows = conn.execute(f'SELECT id, content FROM {_quote_identifier(safe)} {where} ORDER BY id LIMIT ?', params).fetchall()
    return [{'id': r[0], 'content': r[1]} for r in rows]


def get_dynamic_row(table_name: str, row_id: str) -> Optional[Dict]:
    safe = ensure_dynamic_table(table_name)
    with _connect() as conn:
        row = conn.execute(f'SELECT id, content FROM {_quote_identifier(safe)} WHERE id=?', (str(row_id),)).fetchone()
    return {'id': row[0], 'content': row[1]} if row else None


def upsert_dynamic_row(table_name: str, row_id: str, content: str) -> bool:
    safe = ensure_dynamic_table(table_name)
    row_id = str(row_id or '').strip()
    if not row_id:
        raise ValueError('ID dữ liệu không được rỗng')
    with _connect() as conn:
        conn.execute(f'INSERT OR REPLACE INTO {_quote_identifier(safe)} (id, content) VALUES (?, ?)', (row_id, str(content or '')))
    return True


def delete_dynamic_row(table_name: str, row_id: str) -> bool:
    safe = ensure_dynamic_table(table_name)
    with _connect() as conn:
        cur = conn.execute(f'DELETE FROM {_quote_identifier(safe)} WHERE id=?', (str(row_id),))
        return cur.rowcount > 0


def search_dynamic_rows(table_name: str, query: str, limit: int=10) -> List[Dict]:
    if not table_name or not query:
        return []
    safe = ensure_dynamic_table(table_name)
    limit = int(limit or 10)

    # First try exact SQLite LIKE for speed.
    direct = list_dynamic_rows(safe, query=query, limit=limit)
    found = {r['id']: r for r in direct}
    if len(found) >= limit:
        return list(found.values())[:limit]

    # Then do accent-insensitive in-memory matching, because users type oto/thai binh
    # while content may contain Ô tô/Thái Bình. No search_text column is required.
    tokens = _query_tokens(query)
    q_compact = _compact(query)
    with _connect() as conn:
        rows = conn.execute(f'SELECT id, content FROM {_quote_identifier(safe)} ORDER BY id').fetchall()

    scored = []
    for row_id, content in rows:
        row_id = str(row_id or '')
        content = str(content or '')
        hay = _normalize_text(row_id + ' ' + content)
        hay_compact = _compact(row_id + ' ' + content)
        score = 0
        for token in tokens:
            if token in hay or token in hay_compact:
                score += 1
        if q_compact and q_compact in hay_compact:
            score += max(1, len(tokens))
        if score > 0:
            scored.append((score, row_id, content))

    scored.sort(key=lambda x: (-x[0], x[1]))
    for _, row_id, content in scored:
        if row_id not in found:
            found[row_id] = {'id': row_id, 'content': content}
        if len(found) >= limit:
            break
    return list(found.values())[:limit]

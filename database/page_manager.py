"""
Page Manager Module - Multi-page support
Quáº£n lÃ½ nhiá»u Facebook Pages vá»›i token, skill, data riÃªng biá»‡t
"""

import sqlite3
import os
import sys
import json
from typing import List, Dict, Optional
from datetime import datetime

# Get base directory (exe location when frozen, script location when running as script)
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Database path - cùng cấp với exe
DB_DIR = os.path.join(BASE_DIR, 'database')
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "plates.db")


def normalize_ai_provider(provider: str) -> str:
    value = (provider or "").strip().lower()
    if value in {"local", "local_llm", "local-llm", "ollama_local"}:
        return "ollama"
    if value in {"groq", "ollama", "openai"}:
        return value
    return "ollama"


def migrate_ai_provider_local_to_ollama():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE pages
            SET ai_provider = 'ollama', updated_at = CURRENT_TIMESTAMP
            WHERE LOWER(COALESCE(ai_provider, '')) IN ('local', 'local_llm', 'local-llm', 'ollama_local')
        """)
        rows = cursor.rowcount
        conn.commit()
        if rows:
            print(f"[DB_MIGRATE] ai_provider local -> ollama rows={rows}")
    except sqlite3.OperationalError:
        pass
    finally:
        conn.close()


def init_pages_table():
    """Khởi tạo bảng pages"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            page_id TEXT UNIQUE NOT NULL,
            page_name TEXT NOT NULL,
            page_access_token TEXT NOT NULL,
            verify_token TEXT,
            ai_skill TEXT DEFAULT 'plate_sales',
            ai_provider TEXT DEFAULT 'ollama',
            business_domain TEXT DEFAULT '',
            ai_model TEXT DEFAULT '',
            ai_provider_token TEXT DEFAULT '',
            intent_parser_provider TEXT DEFAULT '',
            intent_parser_model TEXT DEFAULT '',
            intent_parser_token TEXT DEFAULT '',
            use_llm_intent_parser TEXT DEFAULT '',
            rag_enabled TEXT DEFAULT '',
            is_active INTEGER DEFAULT 1,
            uid_nguoi_phu_trach TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Migration: add uid_nguoi_phu_trach if not exists
    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN uid_nguoi_phu_trach TEXT")
    except sqlite3.OperationalError:
        pass  # Column đã tồn tại
    
    # Migration: make verify_token nullable (old pages may have it)
    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN verify_token TEXT")
    except sqlite3.OperationalError:
        pass  # Column đã tồn tại
    
    # Migration: add app_id if not exists
    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN app_id TEXT")
    except sqlite3.OperationalError:
        pass  # Column đã tồn tại
    
    # Migration: add app_secret if not exists
    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN app_secret TEXT")
    except sqlite3.OperationalError:
        pass  # Column đã tồn tại
    
    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN intent_parser_provider TEXT")
    except sqlite3.OperationalError:
        pass

    try:
        cursor.execute("ALTER TABLE pages ADD COLUMN intent_parser_model TEXT")
    except sqlite3.OperationalError:
        pass

    for column_sql in [
        "ALTER TABLE pages ADD COLUMN business_domain TEXT DEFAULT ''",
        "ALTER TABLE pages ADD COLUMN ai_model TEXT DEFAULT ''",
        "ALTER TABLE pages ADD COLUMN ai_provider_token TEXT DEFAULT ''",
        "ALTER TABLE pages ADD COLUMN use_llm_intent_parser TEXT DEFAULT ''",
        "ALTER TABLE pages ADD COLUMN rag_enabled TEXT DEFAULT ''",
        "ALTER TABLE pages ADD COLUMN intent_parser_token TEXT DEFAULT ''",
    ]:
        try:
            cursor.execute(column_sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    migrate_ai_provider_local_to_ollama()


def init_db_with_pages():
    """Initialize database with multi-page support."""
    init_pages_table()


# ==================== PAGE CRUD ====================

import secrets

def add_page(page_id: str, page_name: str, page_access_token: str, 
             verify_token: str = '', ai_skill: str = 'plate_sales', 
             ai_provider: str = 'ollama', uid_nguoi_phu_trach: str = '',
             app_id: str = '', app_secret: str = '', is_active: int = 1,
             intent_parser_provider: str = '', intent_parser_model: str = '',
             business_domain: str = '', ai_model: str = '',
             ai_provider_token: str = '', intent_parser_token: str = '',
             use_llm_intent_parser: str = '', rag_enabled: str = '') -> bool:
    """Thêm page mới"""
    if not verify_token:
        verify_token = secrets.token_urlsafe(32)
    ai_provider = normalize_ai_provider(ai_provider)
    if intent_parser_provider:
        intent_parser_provider = normalize_ai_provider(intent_parser_provider)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO pages (
                page_id, page_name, page_access_token, verify_token, ai_skill, ai_provider,
                uid_nguoi_phu_trach, app_id, app_secret, is_active,
                intent_parser_provider, intent_parser_model,
                business_domain, ai_model, ai_provider_token, intent_parser_token,
                use_llm_intent_parser, rag_enabled
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_id, page_name, page_access_token, verify_token, ai_skill, ai_provider,
            uid_nguoi_phu_trach, app_id, app_secret, is_active,
            intent_parser_provider, intent_parser_model,
            business_domain, ai_model, ai_provider_token, intent_parser_token,
            use_llm_intent_parser, rag_enabled
        ))
        conn.commit()
        
        # Tu dong subscribe app vao page
        subscribe_page_app(page_id, page_access_token)
        
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def subscribe_page_app(page_id: str, page_access_token: str):
    """Subscribe app vao page de nhan webhooks"""
    import requests
    
    url = f'https://graph.facebook.com/v18.0/{page_id}/subscribed_apps'
    fields = 'messages,messaging_postbacks,messaging_optins,message_deliveries,message_reads,message_echoes,message_reactions,message_edits'
    
    try:
        response = requests.post(
            url,
            params={'access_token': page_access_token},
            data={'subscribed_fields': fields},
            timeout=10
        )
        result = response.json()
        
        if result.get('success'):
            print(f"[DB] Subscribed app to page {page_id} - Webhooks enabled")
        else:
            print(f"[DB] Subscribe page {page_id} failed: {result}")
    except Exception as e:
        print(f"[DB] Subscribe page {page_id} error: {e}")


def get_page(page_id: str) -> Optional[Dict]:
    """Lấy thông tin page theo page_id"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT page_id, page_name, page_access_token, verify_token,
               ai_skill, ai_provider, is_active, uid_nguoi_phu_trach, created_at, app_id, app_secret,
               COALESCE(intent_parser_provider, ''), COALESCE(intent_parser_model, ''),
               COALESCE(business_domain, ''), COALESCE(ai_model, ''),
               COALESCE(ai_provider_token, ''), COALESCE(intent_parser_token, ''),
               COALESCE(use_llm_intent_parser, ''), COALESCE(rag_enabled, '')
        FROM pages WHERE page_id = ? AND is_active = 1
    """, (page_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'page_id': row[0],
            'page_name': row[1],
            'page_access_token': row[2],
            'verify_token': row[3],
            'ai_skill': row[4],
            'ai_provider': normalize_ai_provider(row[5]),
            'is_active': row[6],
            'uid_nguoi_phu_trach': row[7],
            'created_at': row[8],
            'app_id': row[9] if len(row) > 9 else '',
            'app_secret': row[10] if len(row) > 10 else '',
            'intent_parser_provider': normalize_ai_provider(row[11]) if len(row) > 11 and row[11] else '',
            'intent_parser_model': row[12] if len(row) > 12 else '',
            'business_domain': row[13] if len(row) > 13 else '',
            'ai_model': row[14] if len(row) > 14 else '',
            'ai_provider_token': row[15] if len(row) > 15 else '',
            'intent_parser_token': row[16] if len(row) > 16 else '',
            'use_llm_intent_parser': row[17] if len(row) > 17 else '',
            'rag_enabled': row[18] if len(row) > 18 else ''
        }
    return None


def get_all_pages() -> List[Dict]:
    """Lấy tất cả pages (cả active và inactive)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT page_id, page_name, page_access_token, verify_token,
               ai_skill, ai_provider, is_active, uid_nguoi_phu_trach, created_at, app_id, app_secret,
               COALESCE(intent_parser_provider, ''), COALESCE(intent_parser_model, ''),
               COALESCE(business_domain, ''), COALESCE(ai_model, ''),
               COALESCE(ai_provider_token, ''), COALESCE(intent_parser_token, ''),
               COALESCE(use_llm_intent_parser, ''), COALESCE(rag_enabled, '')
        FROM pages
        ORDER BY is_active DESC, created_at DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            'page_id': row[0],
            'page_name': row[1],
            'page_access_token': row[2],
            'verify_token': row[3],
            'ai_skill': row[4],
            'ai_provider': normalize_ai_provider(row[5]),
            'is_active': row[6],
            'uid_nguoi_phu_trach': row[7],
            'created_at': row[8],
            'app_id': row[9] if len(row) > 9 else '',
            'app_secret': row[10] if len(row) > 10 else '',
            'intent_parser_provider': normalize_ai_provider(row[11]) if len(row) > 11 and row[11] else '',
            'intent_parser_model': row[12] if len(row) > 12 else '',
            'business_domain': row[13] if len(row) > 13 else '',
            'ai_model': row[14] if len(row) > 14 else '',
            'ai_provider_token': row[15] if len(row) > 15 else '',
            'intent_parser_token': row[16] if len(row) > 16 else '',
            'use_llm_intent_parser': row[17] if len(row) > 17 else '',
            'rag_enabled': row[18] if len(row) > 18 else ''
        }
        for row in rows
    ]


def update_page(page_id: str, **kwargs) -> bool:
    """Cập nhật thông tin page"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    allowed_fields = ['page_name', 'page_access_token', 'verify_token', 
                      'ai_skill', 'ai_provider', 'is_active', 'uid_nguoi_phu_trach',
                      'app_id', 'app_secret', 'intent_parser_provider', 'intent_parser_model',
                      'business_domain', 'ai_model', 'ai_provider_token', 'intent_parser_token',
                      'use_llm_intent_parser', 'rag_enabled']
    
    updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
    if "ai_provider" in updates:
        updates["ai_provider"] = normalize_ai_provider(updates["ai_provider"])
    if updates.get("intent_parser_provider"):
        updates["intent_parser_provider"] = normalize_ai_provider(updates["intent_parser_provider"])
    
    if not updates:
        return False
    
    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values()) + [page_id]
    
    cursor.execute(f"""
        UPDATE pages SET {set_clause}, updated_at = CURRENT_TIMESTAMP
        WHERE page_id = ?
    """, values)
    
    conn.commit()
    success = cursor.rowcount > 0
    conn.close()
    
    return success


def delete_page(page_id: str) -> bool:
    """XÃ³a page hoÃ n toÃ n khá»i database (hard delete)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM pages WHERE page_id = ?", (page_id,))
    
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    
    if deleted:
        print(f"ðŸ—‘ï¸ Hard deleted page: {page_id}")
    return deleted


def get_page_by_verify_token(verify_token: str) -> Optional[Dict]:
    """Tìm page theo verify_token (cho webhook verification)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT page_id, page_name, page_access_token, verify_token,
               ai_skill, ai_provider, is_active, COALESCE(intent_parser_provider, ''), COALESCE(intent_parser_model, '')
               , COALESCE(business_domain, ''), COALESCE(ai_model, ''),
               COALESCE(ai_provider_token, ''), COALESCE(intent_parser_token, ''),
               COALESCE(use_llm_intent_parser, ''), COALESCE(rag_enabled, '')
        FROM pages WHERE verify_token = ? AND is_active = 1
    """, (verify_token,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return {
            'page_id': row[0],
            'page_name': row[1],
            'page_access_token': row[2],
            'verify_token': row[3],
            'ai_skill': row[4],
            'ai_provider': normalize_ai_provider(row[5]),
            'is_active': row[6],
            'intent_parser_provider': normalize_ai_provider(row[7]) if len(row) > 7 and row[7] else '',
            'intent_parser_model': row[8] if len(row) > 8 else '',
            'business_domain': row[9] if len(row) > 9 else '',
            'ai_model': row[10] if len(row) > 10 else '',
            'ai_provider_token': row[11] if len(row) > 11 else '',
            'intent_parser_token': row[12] if len(row) > 12 else '',
            'use_llm_intent_parser': row[13] if len(row) > 13 else '',
            'rag_enabled': row[14] if len(row) > 14 else ''
        }
    return None


# ==================== MIGRATION ====================

def migrate_from_env():
    print("[DB_MIGRATE] migrate_from_env is deprecated; use scripts/migrate_env_to_db_once.py")
    return False
    """Migrate từ env file sang database (cho backward compatibility)"""
    # Deprecated body kept unreachable for older imports.
    # env file loaded centrally via utilsenv file_manager (correct runtime path)
    pass
    
    page_id = 'default_page'
    page_access_token = ''
    verify_token = ''
    ai_skill = 'plate_sales'
    ai_provider = normalize_ai_provider('ollama')
    
    if page_access_token and verify_token:
        # Kiểm tra đã tồn tại chưa
        existing = get_page(page_id)
        if not existing:
            add_page(
                page_id=page_id,
                page_name='Default Page',
                page_access_token=page_access_token,
                verify_token=verify_token,
                ai_skill=ai_skill,
                ai_provider=ai_provider
            )
            print(f"✅ Migrated default page from env file")


if __name__ == "__main__":
    init_db_with_pages()
    print("✅ Pages table initialized")


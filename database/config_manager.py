import os
import sqlite3
from datetime import datetime
from typing import Dict, Iterable, Optional

from utils.runtime_paths import ensure_runtime_dirs, get_runtime_path


ensure_runtime_dirs()
DB_PATH = os.path.join(get_runtime_path("database"), "plates.db")


DEFAULT_CONFIGS = {
    "PORT": {"value": "5000", "type": "int", "secret": False},
    "FLASK_DEBUG": {"value": "true", "type": "bool", "secret": False},
    "MESSAGE_QUEUE_WORKERS": {"value": "3", "type": "int", "secret": False},
    "VERIFY_TOKEN": {"value": "", "type": "string", "secret": True},
    "FACEBOOK_APP_ID": {"value": "", "type": "string", "secret": False},
    "FACEBOOK_APP_SECRET": {"value": "", "type": "string", "secret": True},
    "BUSINESS_DOMAIN": {"value": "plate_sales", "type": "string", "secret": False},
    "AI_PROVIDER": {"value": "ollama", "type": "string", "secret": False},
    "DEFAULT_AI_PROVIDER": {"value": "ollama", "type": "string", "secret": False},
    "AI_PROVIDER_TOKEN": {"value": "", "type": "string", "secret": False},
    "AI_MODEL": {"value": "", "type": "string", "secret": False},
    "GROQ_API_KEY": {"value": "", "type": "string", "secret": True},
    "GROQ_MODEL": {"value": "llama-3.3-70b-versatile", "type": "string", "secret": False},
    "GROQ_TEMPERATURE": {"value": "0.25", "type": "float", "secret": False},
    "GROQ_MAX_TOKENS": {"value": "300", "type": "int", "secret": False},
    "GROQ_INTENT_MODEL": {"value": "llama-3.1-8b-instant", "type": "string", "secret": False},
    "OPENAI_API_KEY": {"value": "", "type": "string", "secret": True},
    "OPENAI_MODEL": {"value": "gpt-4.1-mini", "type": "string", "secret": False},
    "OPENAI_TEMPERATURE": {"value": "0.25", "type": "float", "secret": False},
    "OPENAI_MAX_TOKENS": {"value": "300", "type": "int", "secret": False},
    "LOCAL_LLM_URL": {"value": "http://localhost:11434", "type": "string", "secret": False},
    "OLLAMA_MODEL": {"value": "qwen3:4b-instruct", "type": "string", "secret": False},
    "OLLAMA_TEMPERATURE": {"value": "0.25", "type": "float", "secret": False},
    "OLLAMA_MAX_TOKENS": {"value": "300", "type": "int", "secret": False},
    "OLLAMA_TIMEOUT": {"value": "60", "type": "int", "secret": False},
    "USE_LLM_INTENT_PARSER": {"value": "true", "type": "bool", "secret": False},
    "INTENT_PARSER_PROVIDER": {"value": "ollama", "type": "string", "secret": False},
    "INTENT_PARSER_TOKEN": {"value": "", "type": "string", "secret": False},
    "INTENT_PARSER_MODEL": {"value": "qwen3:4b-instruct", "type": "string", "secret": False},
    "INTENT_PARSER_TEMPERATURE": {"value": "0", "type": "float", "secret": False},
    "INTENT_PARSER_MAX_TOKENS": {"value": "160", "type": "int", "secret": False},
    "INTENT_PARSER_TIMEOUT": {"value": "45", "type": "int", "secret": False},
    "INTENT_PARSER_MIN_CONFIDENCE": {"value": "0.65", "type": "float", "secret": False},
    "RAG_ENABLED": {"value": "true", "type": "bool", "secret": False},
    "RAG_KB_MODE": {"value": "runtime", "type": "string", "secret": False},
    "RAG_TOP_K": {"value": "5", "type": "int", "secret": False},
    "RAG_MIN_SCORE": {"value": "0.05", "type": "float", "secret": False},
    "ENABLE_FILE_CONVERSATION_LOG": {"value": "false", "type": "bool", "secret": False},
    "ENABLE_RUNTIME_FILE_LOG": {"value": "false", "type": "bool", "secret": False},
    "ENABLE_CONVERSATION_DB_LOG": {"value": "false", "type": "bool", "secret": False},
    "DB_FLUSH_INTERVAL_SECONDS": {"value": "10", "type": "int", "secret": False},
    "STATE_BUFFER_MAX_DIRTY": {"value": "30", "type": "int", "secret": False},
    "CONVERSATION_LOG_BUFFER_SIZE": {"value": "50", "type": "int", "secret": False},
    "MAX_PRELOAD_ROWS": {"value": "0", "type": "int", "secret": False},
    "AI_SKILL": {"value": "plate_sales", "type": "string", "secret": False},
    "DEFAULT_SKILL": {"value": "plate_sales", "type": "string", "secret": False},
}


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def init_config_table():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS global_config (
                key TEXT PRIMARY KEY,
                value TEXT,
                value_type TEXT DEFAULT 'string',
                description TEXT DEFAULT '',
                is_secret INTEGER DEFAULT 0,
                updated_at TEXT
            )
            """
        )


def seed_default_configs(overwrite: bool = False):
    init_config_table()
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        for key, meta in DEFAULT_CONFIGS.items():
            if overwrite:
                conn.execute(
                    """
                    INSERT INTO global_config (key, value, value_type, description, is_secret, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value,
                        value_type=excluded.value_type,
                        description=excluded.description,
                        is_secret=excluded.is_secret,
                        updated_at=excluded.updated_at
                    """,
                    (key, str(meta["value"]), meta["type"], "", int(meta["secret"]), now),
                )
            else:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO global_config
                        (key, value, value_type, description, is_secret, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (key, str(meta["value"]), meta["type"], "", int(meta["secret"]), now),
                )


def get_config(key: str, default=None):
    init_config_table()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM global_config WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_config(key: str, value, value_type: str = "string", description: str = "", is_secret: bool = False):
    init_config_table()
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO global_config (key, value, value_type, description, is_secret, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                value_type=excluded.value_type,
                description=excluded.description,
                is_secret=excluded.is_secret,
                updated_at=excluded.updated_at
            """,
            (key, "" if value is None else str(value), value_type or "string", description or "", int(bool(is_secret)), now),
        )
    return True


def get_configs(keys: Optional[Iterable[str]] = None, include_secret: bool = True) -> Dict[str, Dict[str, object]]:
    init_config_table()
    params = []
    where = []
    if keys:
        keys = list(keys)
        where.append("key IN (%s)" % ",".join("?" for _ in keys))
        params.extend(keys)
    if not include_secret:
        where.append("is_secret = 0")
    sql = "SELECT key, value, value_type, description, is_secret, updated_at FROM global_config"
    if where:
        sql += " WHERE " + " AND ".join(where)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return {
        row[0]: {
            "value": row[1],
            "value_type": row[2],
            "description": row[3],
            "is_secret": bool(row[4]),
            "updated_at": row[5],
        }
        for row in rows
    }


def set_configs(config_dict: Dict[str, object]):
    init_config_table()
    now = datetime.utcnow().isoformat()
    with _connect() as conn:
        for key, raw in (config_dict or {}).items():
            meta = DEFAULT_CONFIGS.get(key, {})
            if isinstance(raw, dict):
                value = raw.get("value", "")
                value_type = raw.get("value_type") or raw.get("type") or meta.get("type", "string")
                description = raw.get("description", "")
                is_secret = raw.get("is_secret", raw.get("secret", meta.get("secret", False)))
            else:
                value = raw
                value_type = meta.get("type", "string")
                description = ""
                is_secret = meta.get("secret", False)
            conn.execute(
                """
                INSERT INTO global_config (key, value, value_type, description, is_secret, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    value_type=excluded.value_type,
                    description=excluded.description,
                    is_secret=excluded.is_secret,
                    updated_at=excluded.updated_at
                """,
                (key, "" if value is None else str(value), value_type, description, int(bool(is_secret)), now),
            )
    return True


def delete_config(key: str):
    init_config_table()
    with _connect() as conn:
        cur = conn.execute("DELETE FROM global_config WHERE key = ?", (key,))
        return cur.rowcount > 0


def get_bool_config(key: str, default: bool = False) -> bool:
    value = get_config(key, None)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_int_config(key: str, default: int = 0) -> int:
    try:
        return int(get_config(key, default))
    except (TypeError, ValueError):
        return default


def get_float_config(key: str, default: float = 0.0) -> float:
    try:
        return float(get_config(key, default))
    except (TypeError, ValueError):
        return default


def mask_secret(value) -> str:
    value = "" if value is None else str(value)
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    prefix = ""
    if value.startswith("gsk_"):
        prefix = "gsk_"
    elif value.startswith("sk-"):
        prefix = "sk-"
    if prefix and len(value) > len(prefix) + 4:
        return f"{prefix}...{value[-4:]}"
    return f"****{value[-4:]}"


def get_public_configs() -> Dict[str, str]:
    configs = get_configs(include_secret=True)
    public = {}
    for key, meta in configs.items():
        value = meta.get("value") or ""
        if meta.get("is_secret"):
            public[key] = mask_secret(value)
            public[f"{key}_SET"] = bool(value)
        else:
            public[key] = value
    return public


def get_admin_configs() -> Dict[str, str]:
    """Return raw config values for the local admin UI."""
    configs = get_configs(include_secret=True)
    return {key: meta.get("value") or "" for key, meta in configs.items()}


get_raw_configs = get_admin_configs

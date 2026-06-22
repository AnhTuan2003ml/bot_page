import atexit
import json
import sqlite3
import threading
import time
from datetime import datetime

from database.conversation_manager import DB_PATH as CONVERSATION_DB_PATH, init_conversations_table
from database.conversation_state_manager import DB_PATH as STATE_DB_PATH, init_conversation_states_table
from utils.config_service import get_runtime_bool, get_runtime_int
from utils.logger import debug


STATE_KEYS = {
    "selected_item", "selected_plate", "selected_product", "selected_province",
    "product_type", "category", "vehicle_type", "size", "color", "budget",
    "last_intent", "last_results", "pending_question", "updated_at",
}

_STATE_CACHE = {}
_LOG_BUFFER = []
_HISTORY = {}
_LOCK = threading.RLock()
_WRITER_LOCK = threading.RLock()
_STOP = threading.Event()
_WORKER_STARTED = False


def _connect(path):
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _state_key(page_id, sender_id, expertise_id):
    return (str(page_id), str(sender_id), int(expertise_id))


def _sanitize_state(state):
    clean = {key: value for key, value in (state or {}).items() if key in STATE_KEYS}
    results = clean.get("last_results")
    if isinstance(results, list):
        clean["last_results"] = results[:5]
    clean["updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat()
    return clean


def get_state(page_id, sender_id, expertise_id):
    key = _state_key(page_id, sender_id, expertise_id)
    with _LOCK:
        entry = _STATE_CACHE.get(key)
        if entry:
            return dict(entry["state"])

    init_conversation_states_table()
    with _connect(STATE_DB_PATH) as conn:
        row = conn.execute(
            "SELECT state_json FROM conversation_states WHERE page_id=? AND sender_id=? AND expertise_id=?",
            key,
        ).fetchone()
    try:
        state = json.loads(row[0] or "{}") if row else {}
    except Exception:
        state = {}
    state = _sanitize_state(state)
    now = time.time()
    with _LOCK:
        _STATE_CACHE[key] = {
            "state": state,
            "dirty": False,
            "last_updated": now,
            "last_flushed": now,
        }
    return dict(state)


def set_state(page_id, sender_id, expertise_id, state):
    key = _state_key(page_id, sender_id, expertise_id)
    now = time.time()
    with _LOCK:
        _STATE_CACHE[key] = {
            "state": _sanitize_state(state),
            "dirty": True,
            "last_updated": now,
            "last_flushed": (_STATE_CACHE.get(key) or {}).get("last_flushed", 0),
        }
        dirty_count = sum(1 for entry in _STATE_CACHE.values() if entry.get("dirty"))
    if dirty_count >= get_runtime_int("STATE_BUFFER_MAX_DIRTY", 30):
        flush_dirty_states()
    return True


def _history_key(page_id, sender_id, expertise_id):
    return _state_key(page_id, sender_id, expertise_id)


def append_history(page_id, sender_id, expertise_id, role, content):
    if role not in {"user", "assistant"} or not content:
        return
    key = _history_key(page_id, sender_id, expertise_id)
    with _LOCK:
        history = _HISTORY.setdefault(key, [])
        history.append({"role": str(role), "message": str(content)})
        del history[:-10]


def get_history(page_id, sender_id, expertise_id, limit=10):
    key = _history_key(page_id, sender_id, expertise_id)
    with _LOCK:
        history = list(_HISTORY.get(key) or [])
    return history[-int(limit or 10):]


def add_log(page_id, sender_id, expertise_id, role, message):
    append_history(page_id, sender_id, expertise_id, role, message)
    if not get_runtime_bool("ENABLE_CONVERSATION_DB_LOG", False):
        return True
    record = (
        str(page_id),
        str(sender_id),
        int(expertise_id) if expertise_id not in (None, "") else None,
        str(role),
        str(message or ""),
    )
    with _LOCK:
        _LOG_BUFFER.append(record)
        size = len(_LOG_BUFFER)
    if size >= get_runtime_int("CONVERSATION_LOG_BUFFER_SIZE", 50):
        flush_conversation_logs()
    return True


def flush_dirty_states():
    with _LOCK:
        items = [
            (key, dict(entry["state"]))
            for key, entry in _STATE_CACHE.items()
            if entry.get("dirty")
        ]
    if not items:
        return 0
    init_conversation_states_table()
    rows = [
        (page_id, sender_id, expertise_id, json.dumps(state, ensure_ascii=False))
        for (page_id, sender_id, expertise_id), state in items
    ]
    with _WRITER_LOCK:
        try:
            with _connect(STATE_DB_PATH) as conn:
                conn.executemany(
                    """
                    INSERT INTO conversation_states (page_id,sender_id,expertise_id,state_json)
                    VALUES (?,?,?,?)
                    ON CONFLICT(page_id,sender_id,expertise_id)
                    DO UPDATE SET state_json=excluded.state_json
                    """,
                    rows,
                )
        except sqlite3.OperationalError as exc:
            debug(f"[STATE_BUFFER] flush states error={exc}")
            return 0
    now = time.time()
    with _LOCK:
        for key, _ in items:
            if key in _STATE_CACHE:
                _STATE_CACHE[key]["dirty"] = False
                _STATE_CACHE[key]["last_flushed"] = now
    debug(f"[STATE_BUFFER] flushed states count={len(rows)}")
    return len(rows)


def flush_conversation_logs():
    with _LOCK:
        rows = list(_LOG_BUFFER)
        _LOG_BUFFER.clear()
    if not rows:
        return 0
    init_conversations_table()
    with _WRITER_LOCK:
        try:
            with _connect(CONVERSATION_DB_PATH) as conn:
                conn.executemany(
                    "INSERT INTO conversations (page_id,sender_id,expertise_id,role,message) VALUES (?,?,?,?,?)",
                    rows,
                )
        except sqlite3.OperationalError as exc:
            debug(f"[STATE_BUFFER] flush logs error={exc}")
            with _LOCK:
                _LOG_BUFFER[:0] = rows
            return 0
    debug(f"[STATE_BUFFER] flushed logs count={len(rows)}")
    return len(rows)


def flush_all():
    flush_dirty_states()
    flush_conversation_logs()


def _worker_loop():
    while not _STOP.wait(max(5, get_runtime_int("DB_FLUSH_INTERVAL_SECONDS", 10))):
        flush_all()


def start_db_flush_workers():
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return False
    _WORKER_STARTED = True
    thread = threading.Thread(target=_worker_loop, name="db-flush-worker", daemon=True)
    thread.start()
    debug("[STATE_BUFFER] db flush worker started")
    return True


atexit.register(flush_all)

import json, os, sqlite3, sys
if getattr(sys, 'frozen', False): BASE_DIR=os.path.dirname(sys.executable)
else: BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH=os.path.join(BASE_DIR,'database','plates.db')
def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
def init_conversation_states_table():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS conversation_states (id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL, sender_id TEXT NOT NULL, expertise_id INTEGER NOT NULL, state_json TEXT NOT NULL DEFAULT '{}', UNIQUE(page_id, sender_id, expertise_id))""")
def get_conversation_state(page_id,sender_id,expertise_id):
    from services.state_buffer import get_state
    return get_state(page_id,sender_id,expertise_id)
def upsert_conversation_state(page_id,sender_id,expertise_id,state_json):
    from services.state_buffer import set_state
    if isinstance(state_json, str):
        try: state_json=json.loads(state_json or '{}')
        except Exception: state_json={}
    return set_state(page_id,sender_id,expertise_id,state_json)
def reset_conversation_state(page_id,sender_id,expertise_id):
    with _connect() as conn: conn.execute('DELETE FROM conversation_states WHERE page_id=? AND sender_id=? AND expertise_id=?',(str(page_id),str(sender_id),int(expertise_id)))

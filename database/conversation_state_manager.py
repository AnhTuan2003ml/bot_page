import json, os, sqlite3, sys
if getattr(sys, 'frozen', False): BASE_DIR=os.path.dirname(sys.executable)
else: BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH=os.path.join(BASE_DIR,'database','plates.db')
def _connect(): return sqlite3.connect(DB_PATH)
def init_conversation_states_table():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS conversation_states (id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL, sender_id TEXT NOT NULL, expertise_id INTEGER NOT NULL, state_json TEXT NOT NULL DEFAULT '{}', UNIQUE(page_id, sender_id, expertise_id))""")
def get_conversation_state(page_id,sender_id,expertise_id):
    init_conversation_states_table()
    with _connect() as conn:
        row=conn.execute('SELECT state_json FROM conversation_states WHERE page_id=? AND sender_id=? AND expertise_id=?',(str(page_id),str(sender_id),int(expertise_id))).fetchone()
    if not row: return {}
    try: return json.loads(row[0] or '{}')
    except Exception: return {}
def upsert_conversation_state(page_id,sender_id,expertise_id,state_json):
    init_conversation_states_table()
    if not isinstance(state_json, str): state_json=json.dumps(state_json or {}, ensure_ascii=False)
    with _connect() as conn:
        conn.execute("""INSERT INTO conversation_states (page_id,sender_id,expertise_id,state_json) VALUES (?,?,?,?) ON CONFLICT(page_id,sender_id,expertise_id) DO UPDATE SET state_json=excluded.state_json""",(str(page_id),str(sender_id),int(expertise_id),state_json))
def reset_conversation_state(page_id,sender_id,expertise_id):
    with _connect() as conn: conn.execute('DELETE FROM conversation_states WHERE page_id=? AND sender_id=? AND expertise_id=?',(str(page_id),str(sender_id),int(expertise_id)))

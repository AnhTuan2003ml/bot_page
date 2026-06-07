import os, sqlite3, sys
if getattr(sys, 'frozen', False): BASE_DIR=os.path.dirname(sys.executable)
else: BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH=os.path.join(BASE_DIR,'database','plates.db')
def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn
def init_conversations_table():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL, sender_id TEXT NOT NULL, expertise_id INTEGER, role TEXT NOT NULL, message TEXT NOT NULL)""")
def add_conversation(page_id,sender_id,expertise_id,role,message):
    from services.state_buffer import add_log
    return add_log(page_id,sender_id,expertise_id,role,message)
def get_recent_conversations(page_id,sender_id,limit=10):
    # Hot path should read the in-memory window. DB history is intentionally not
    # restored per message; conversation_states is the restart recovery source.
    try:
        from services.state_buffer import get_history
        return get_history(page_id,sender_id,0,limit=limit)
    except Exception:
        pass
    init_conversations_table()
    with _connect() as conn:
        rows=conn.execute('SELECT role,message FROM conversations WHERE page_id=? AND sender_id=? ORDER BY id DESC LIMIT ?',(str(page_id),str(sender_id),int(limit or 10))).fetchall()
    rows=list(reversed(rows)); return [{'role':r[0], 'message':r[1]} for r in rows]

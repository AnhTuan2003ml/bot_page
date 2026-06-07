import os, sqlite3, sys
if getattr(sys, 'frozen', False): BASE_DIR=os.path.dirname(sys.executable)
else: BASE_DIR=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH=os.path.join(BASE_DIR,'database','plates.db')
def _connect(): return sqlite3.connect(DB_PATH)
def init_customer_profiles_table():
    with _connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS customer_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, page_id TEXT NOT NULL, sender_id TEXT NOT NULL, name TEXT DEFAULT '', pronoun TEXT DEFAULT '', UNIQUE(page_id, sender_id))""")
def get_customer_profile(page_id, sender_id):
    init_customer_profiles_table()
    with _connect() as conn:
        row=conn.execute('SELECT id,page_id,sender_id,name,pronoun FROM customer_profiles WHERE page_id=? AND sender_id=?',(str(page_id),str(sender_id))).fetchone()
    return {'id':row[0],'page_id':row[1],'sender_id':row[2],'name':row[3] or '','pronoun':row[4] or ''} if row else {'page_id':str(page_id),'sender_id':str(sender_id),'name':'','pronoun':''}
def upsert_customer_profile(page_id, sender_id, name=None, pronoun=None):
    init_customer_profiles_table(); cur=get_customer_profile(page_id,sender_id)
    new_name = cur.get('name','') if name is None else str(name or '').strip()
    new_pronoun = cur.get('pronoun','') if pronoun is None else str(pronoun or '').strip().lower()
    with _connect() as conn:
        conn.execute("""INSERT INTO customer_profiles (page_id,sender_id,name,pronoun) VALUES (?,?,?,?) ON CONFLICT(page_id,sender_id) DO UPDATE SET name=excluded.name, pronoun=excluded.pronoun""",(str(page_id),str(sender_id),new_name,new_pronoun))
    return get_customer_profile(page_id,sender_id)

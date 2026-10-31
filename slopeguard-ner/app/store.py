"""Small transactional JSON record store; PostgreSQL in deployment, SQLite locally."""
import os
import sqlite3
import threading
from contextlib import contextmanager

LOCK=threading.RLock()
URL=os.getenv('DATABASE_URL','')
PATH=os.getenv('SQLITE_PATH','slopeguard.db')

@contextmanager
def db():
    with LOCK:
        if URL:
            import psycopg
            con=psycopg.connect(URL,connect_timeout=10)
        else:
            con=sqlite3.connect(PATH,timeout=20)
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback(); raise
        finally: con.close()

def run(con,sql,args=()):
    return con.execute(sql.replace('?', '%s') if URL else sql,args)

def init():
    with db() as c:
        run(c,'CREATE TABLE IF NOT EXISTS records (kind TEXT NOT NULL, id TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(kind,id))')

def all_records(kind):
    import json
    with db() as c:
        return [json.loads(r[0]) for r in run(c,'SELECT body FROM records WHERE kind=? ORDER BY id DESC',(kind,)).fetchall()]

def get(kind,ident):
    import json
    with db() as c:
        r=run(c,'SELECT body FROM records WHERE kind=? AND id=?',(kind,ident)).fetchone()
        return json.loads(r[0]) if r else None

def put(kind,ident,body):
    import json
    with db() as c:
        run(c,'INSERT INTO records(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',(kind,ident,json.dumps(body)))

def insert_once(kind,ident,body):
    import json
    with db() as c:
        return run(c,'INSERT INTO records(kind,id,body) VALUES(?,?,?) ON CONFLICT(kind,id) DO NOTHING',(kind,ident,json.dumps(body))).rowcount == 1

"""Domain operations and transactional SQLite persistence."""
import json, os, sqlite3, threading, time
from pathlib import Path
from urllib.request import urlopen
from domain import validate, summary, transition
import domain

BASE = Path(__file__).resolve().parent
CONFIG = json.loads((BASE / 'project.json').read_text())
domain.CONFIG = CONFIG
DB = Path(os.environ.get('DATABASE_PATH', str(BASE / 'data' / 'app.db')))
LOCK = threading.RLock()

class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try: return super().__exit__(*args)
        finally: self.close()

def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=10, factory=Connection)
    conn.execute('CREATE TABLE IF NOT EXISTS records (id INTEGER PRIMARY KEY, body TEXT NOT NULL)')
    return conn

def records():
    with connect() as conn:
        return [dict(json.loads(body), id=key) for key,body in conn.execute('SELECT id,body FROM records ORDER BY id DESC')]

def save(row):
    with connect() as conn:
        conn.execute('UPDATE records SET body=? WHERE id=?',(json.dumps(row),row['id']))

def create(data):
    with LOCK:
        row = validate(data, records())
        with connect() as conn:
            key = conn.execute('INSERT INTO records(body) VALUES (?)',(json.dumps(row),)).lastrowid
        return dict(row,id=key)

def action(key, name):
    with LOCK:
        row = next((r for r in records() if r['id'] == key),None)
        if row is None: raise LookupError('Record not found')
        if name == 'check' and CONFIG['kind'] == 'uptime':
            started = time.monotonic()
            try:
                with urlopen(row['url'], timeout=3) as response:
                    row.update(healthy=200 <= response.status < 400, http_status=response.status, error=None)
            except Exception as exc: row.update(healthy=False, error=str(exc), http_status=None)
            row.update(latency_ms=round((time.monotonic()-started)*1000,2), checked_at=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
        else: row = transition(row,name)
        save(row)
        return row

def work_once():
    with LOCK:
        row = next((r for r in reversed(records()) if r.get('status') == 'queued'),None)
        if row is None: return False
        row.update(status='running', attempts=row['attempts']+1); save(row)
    try:
        payload = row['payload']
        row['result'] = {'uppercase':lambda:payload.upper(), 'word_count':lambda:len(payload.split()), 'sort_lines':lambda:'\n'.join(sorted(payload.splitlines()))}[row['operation']]()
        row['status'] = 'completed'
    except Exception as exc: row.update(status='failed', error=str(exc))
    with LOCK: save(row)
    return True

def worker():
    while True:
        work_once(); time.sleep(0.5)

"""Dependency-free local application; Python 3.11+."""
import json, os, sqlite3, threading, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
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

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, body, content_type='application/json'):
        payload = json.dumps(body).encode() if content_type == 'application/json' else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length',str(len(payload)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers(); self.wfile.write(payload)

    def do_GET(self):
        path = urlparse(self.path)
        if path.path == '/health': return self.respond(200,{'status':'ok','project':CONFIG['name']})
        if path.path == '/api/config': return self.respond(200,CONFIG)
        if path.path in ['/api/records','/api/summary']:
            rows = records()
            query = parse_qs(path.query).get('q',[''])[0].lower()
            if query: rows = [r for r in rows if query in json.dumps(r).lower()]
            return self.respond(200,summary(rows) if path.path.endswith('summary') else rows)
        files = {'/':'index.html','/style.css':'style.css','/app.js':'app.js'}
        if path.path in files:
            filename = files[path.path]
            mime = {'index.html':'text/html; charset=utf-8','style.css':'text/css','app.js':'text/javascript'}[filename]
            return self.respond(200,(BASE/'static'/filename).read_bytes(),mime)
        self.respond(404,{'error':'Not found'})

    def do_POST(self):
        try:
            size = int(self.headers.get('Content-Length','0'))
            if size < 1 or size > 32768: raise ValueError('Body must be 1 to 32768 bytes')
            data = json.loads(self.rfile.read(size))
            path = urlparse(self.path).path
            if path == '/api/records': return self.respond(201,create(data))
            parts = path.strip('/').split('/')
            if len(parts) == 4 and parts[:2] == ['api','records']:
                return self.respond(200,action(int(parts[2]),parts[3]))
            self.respond(404,{'error':'Not found'})
        except LookupError as exc: self.respond(404,{'error':str(exc)})
        except (ValueError, TypeError) as exc: self.respond(400,{'error':str(exc)})

    def do_DELETE(self):
        parts = urlparse(self.path).path.strip('/').split('/')
        if len(parts) != 3 or parts[:2] != ['api','records']: return self.respond(404,{'error':'Not found'})
        try: key = int(parts[2])
        except ValueError: return self.respond(400,{'error':'Invalid record ID'})
        with LOCK, connect() as conn:
            deleted = conn.execute('DELETE FROM records WHERE id=?',(key,)).rowcount
        self.respond(200 if deleted else 404,{'deleted':bool(deleted)})

if __name__ == '__main__':
    connect().close()
    if CONFIG['kind'] == 'jobs':
        with LOCK:
            for row in records():
                if row['status'] == 'running': row['status'] = 'queued'; save(row)
        threading.Thread(target=worker,daemon=True).start()
    host = os.environ.get('HOST','127.0.0.1'); port = int(os.environ.get('PORT',CONFIG['port']))
    print(f"{CONFIG['name']}: http://{host}:{port}",flush=True)
    ThreadingHTTPServer((host,port),Handler).serve_forever()

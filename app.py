"""Compatibility facade and durable job worker; HTTP lives in backend.api."""
import json, os, threading
from pathlib import Path
from backend import database, domain, repository, service

BASE=Path(__file__).resolve().parent
CONFIG=json.loads((BASE/'project.json').read_text(encoding='utf-8'))
domain.CONFIG=CONFIG
DB=Path(os.environ.get('DATABASE_PATH',str(BASE/'data/app.db')))
LOCK=threading.RLock()

def connect(): return database.connect(DB)
def records():
    with connect() as connection: return repository.list_all(connection)
def save(row): row.update(repository.save(DB,row))
def create(data): return service.RecordService(DB,CONFIG).create(data)[0]
def summary(rows): return domain.summary(rows)
def action(key,name):
    row=service.RecordService(DB,CONFIG).get(key)
    return service.RecordService(DB,CONFIG).act(key,name,{'role':'admin'},str(row['version']),'internal')

def work_once():
    with LOCK:
        row=next((r for r in reversed(records()) if r.get('status')=='queued'),None)
        if row is None: return False
        row.update(status='running',attempts=row['attempts']+1)
        try: save(row)
        except repository.ConflictError: return False
    try:
        payload=row['payload']
        row['result']={'uppercase':lambda:payload.upper(),'word_count':lambda:len(payload.split()),'sort_lines':lambda:'\n'.join(sorted(payload.splitlines()))}[row['operation']]()
        row['status']='completed'
    except Exception as exc: row.update(status='failed',error=str(exc))
    try: save(row)
    except (LookupError,repository.ConflictError): pass
    return True

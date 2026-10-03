"""Storage primitives; callers own transaction boundaries."""
from datetime import datetime, timezone
import json
from . import database

class ConflictError(Exception): pass
class PreconditionError(Exception): pass

def now(): return datetime.now(timezone.utc).isoformat()

def decode(row):
    return dict(json.loads(row['body']),id=row['id'],version=row['version'],created_at=row['created_at'])

def list_all(connection):
    return [decode(row) for row in connection.execute('SELECT * FROM records WHERE deleted_at IS NULL ORDER BY id DESC')]

def get(connection,key):
    row=connection.execute('SELECT * FROM records WHERE id=? AND deleted_at IS NULL',(key,)).fetchone()
    if row is None: raise LookupError('Record not found')
    return decode(row)

def payload(row): return {k:v for k,v in row.items() if k not in ['id','version','created_at']}

def insert(connection,row):
    created=now()
    key=connection.execute('INSERT INTO records(body,created_at) VALUES (?,?)',(json.dumps(payload(row),allow_nan=False),created)).lastrowid
    return dict(row,id=key,version=1,created_at=created)

def update(connection,row,expected):
    changed=connection.execute('UPDATE records SET body=?, version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL',(json.dumps(payload(row),allow_nan=False),row['id'],expected)).rowcount
    if not changed: raise ConflictError('Record changed; refresh and retry with its current version')
    return dict(row,version=expected+1)

def archive(connection,key,expected):
    changed=connection.execute('UPDATE records SET deleted_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL',(now(),key,expected)).rowcount
    if not changed: raise ConflictError('Record changed; refresh before deleting')

def audit(connection,actor,operation,record_id,request_id,metadata=None):
    connection.execute('INSERT INTO audit_events(actor_id,actor,operation,record_id,request_id,metadata,created_at) VALUES (?,?,?,?,?,?,?)',((actor or {}).get('id'),(actor or {}).get('username','system'),operation,record_id,request_id,json.dumps(metadata or {}),now()))

def save(path,row,actor=None,operation='worker.update'):
    with database.transaction(path) as connection:
        current=get(connection,row['id']); expected=row.get('version',current['version'])
        updated=update(connection,row,expected)
        audit(connection,actor,operation,row['id'],'background',{'version':updated['version']})
        return updated

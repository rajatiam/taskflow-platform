"""Business orchestration with atomic audits and optimistic concurrency."""
import hashlib, json, time
from urllib.request import urlopen
from . import database, domain, repository, security

class RecordService:
    def __init__(self,path,config): self.path=path; self.config=config

    def create(self,data,actor=None,request_id='internal',key=None):
        if key and (len(key)>128 or len(key)<8): raise ValueError('Idempotency-Key must contain 8 to 128 characters')
        fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True,allow_nan=False).encode()).hexdigest()
        with database.transaction(self.path) as connection:
            if key and actor:
                connection.execute('DELETE FROM idempotency_keys WHERE created_at<?',(int(time.time())-86400,))
                cached=connection.execute('SELECT * FROM idempotency_keys WHERE user_id=? AND key=?',(actor['id'],key)).fetchone()
                if cached:
                    if cached['fingerprint']!=fingerprint: raise repository.ConflictError('Idempotency key was already used with a different payload')
                    return json.loads(cached['response']),True
            row=domain.validate(data,repository.list_all(connection))
            result=repository.insert(connection,row)
            repository.audit(connection,actor,'record.created',result['id'],request_id,{'version':1})
            if key and actor:
                connection.execute('INSERT INTO idempotency_keys VALUES (?,?,?,?,?)',(actor['id'],key,fingerprint,json.dumps(result),int(time.time())))
            return result,False

    def get(self,key):
        with database.connect(self.path) as connection: return repository.get(connection,key)

    def list(self,q='',limit=50,offset=0):
        escaped=q.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        with database.connect(self.path) as connection:
            where="deleted_at IS NULL AND (lower(body) LIKE ? ESCAPE '\\' OR CAST(id AS TEXT) LIKE ?)"
            match='%'+escaped+'%'
            total=connection.execute('SELECT COUNT(*) FROM records WHERE '+where,(match,match)).fetchone()[0]
            rows=connection.execute('SELECT * FROM records WHERE '+where+' ORDER BY id DESC LIMIT ? OFFSET ?',(match,match,limit,offset)).fetchall()
        return {'items':[repository.decode(row) for row in rows],'total':total,'limit':limit,'offset':offset}

    def expected(self,row,header):
        if header is None: raise repository.PreconditionError('If-Match header is required; use the current record version')
        try: expected=int(header.strip('"'))
        except ValueError: raise ValueError('If-Match must contain an integer version')
        if expected!=row['version']: raise repository.ConflictError('Stale version; refresh and retry')
        return expected

    def act(self,key,action,actor,header,request_id):
        row=self.get(key); expected=self.expected(row,header)
        if action=='approve': security.require(actor,{'admin'})
        if action=='check' and self.config['kind']=='uptime':
            started=time.monotonic()
            try:
                with urlopen(row['url'],timeout=3) as response: row.update(healthy=200<=response.status<400,http_status=response.status,error=None)
            except Exception as exc: row.update(healthy=False,http_status=None,error=str(exc))
            row.update(latency_ms=round((time.monotonic()-started)*1000,2),checked_at=repository.now())
        else: row=domain.transition(row,action)
        # External I/O happens before a short CAS transaction: never hold a
        # database write lock while waiting on an HTTP endpoint.
        with database.transaction(self.path) as connection:
            result=repository.update(connection,row,expected)
            repository.audit(connection,actor,'record.'+action,key,request_id,{'version':result['version']})
        return result

    def delete(self,key,actor,header,request_id):
        with database.transaction(self.path) as connection:
            row=repository.get(connection,key); expected=self.expected(row,header)
            repository.archive(connection,key,expected)
            repository.audit(connection,actor,'record.archived',key,request_id,{'version':expected+1})
        return {'deleted':True}

"""Authenticated fixtures for business tests; no production login bypass."""
from fastapi.testclient import TestClient
from backend import database, repository, security
from backend.api import SETTINGS
import app as store

FIXTURE_HASH=security.password_hash('Fixture-password-only-2026')

class AuthorizedClient(TestClient):
    def __init__(self,application,role='admin'):
        super().__init__(application)
        with database.transaction(store.DB) as connection:
            key=connection.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',('fixture-user',FIXTURE_HASH,role,repository.now())).lastrowid
        user={'id':key,'username':'fixture-user','role':role}
        token,csrf=security.issue_session(store.DB,user)
        self.cookies.set(SETTINGS.session_cookie,token); self.cookies.set(SETTINGS.csrf_cookie,csrf)
        self.headers['X-CSRF-Token']=csrf
    def request(self,method,url,*args,**kwargs):
        if method.upper() in ['POST','DELETE'] and str(url).startswith('/api/records/'):
            parts=str(url).strip('/').split('/')
            if len(parts)>2 and parts[2].isdigit():
                row=next((r for r in store.records() if r['id']==int(parts[2])),None)
                if row: kwargs['headers']=dict(kwargs.get('headers') or {},**{'If-Match':str(row['version'])})
        return super().request(method,url,*args,**kwargs)

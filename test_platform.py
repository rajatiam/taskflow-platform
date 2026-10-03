import json, sqlite3, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend import database, repository, security, service
from backend.api import SETTINGS
from tests.helpers import FIXTURE_HASH
import app, api

PASSWORD='Fixture-password-only-2026'

class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); app.DB=Path(self.tmp.name)/'platform.db'
        self.client=TestClient(api.app)
        with database.transaction(app.DB) as connection:
            key=connection.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',('platform-admin',FIXTURE_HASH,'admin',repository.now())).lastrowid
        self.user={'id':key,'username':'platform-admin','role':'admin'}
        self.token,self.csrf=security.issue_session(app.DB,self.user)
        self.client.cookies.set(SETTINGS.session_cookie,self.token)
        self.client.headers['X-CSRF-Token']=self.csrf
        self.example=dict(app.CONFIG['example'])
    def tearDown(self): self.client.close(); self.tmp.cleanup()
    def scalar(self,sql):
        with database.connect(app.DB) as connection: return connection.execute(sql).fetchone()[0]
    def test_anonymous_access_and_request_headers(self):
        with TestClient(api.app) as anonymous:
            self.assertEqual(anonymous.get('/api/records').status_code,401)
            self.assertEqual(anonymous.get('/api/config').status_code,401)
            response=anonymous.get('/health')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
            self.assertIn('X-Request-ID',response.headers)
    def test_csrf_rejects_mutation(self):
        self.client.headers.pop('X-CSRF-Token')
        response=self.client.post('/api/records',json=self.example)
        self.assertEqual(response.status_code,403); self.assertEqual(len(app.records()),0)
    def test_registration_cannot_escalate_role(self):
        response=self.client.post('/api/auth/register',json={'username':'new-user','password':PASSWORD,'role':'admin'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM users'),1)
    def test_viewer_permissions(self):
        with database.transaction(app.DB) as connection: connection.execute("UPDATE users SET role='viewer' WHERE id=?",(self.user['id'],))
        self.assertEqual(self.client.get('/api/records').status_code,200)
        self.assertEqual(self.client.post('/api/records',json=self.example).status_code,403)
        self.assertEqual(self.client.get('/api/audit').status_code,403)
    def test_approval_requires_admin(self):
        row=app.create(self.example)
        with database.transaction(app.DB) as connection: connection.execute("UPDATE users SET role='editor' WHERE id=?",(self.user['id'],))
        result=self.client.post(f"/api/records/{row['id']}/approve",headers={'If-Match':str(row['version'])})
        self.assertEqual(result.status_code,403)
    def test_idempotency_replay_and_payload_conflict(self):
        headers={'Idempotency-Key':'durable-create-request'}
        first=self.client.post('/api/records',json=self.example,headers=headers)
        second=self.client.post('/api/records',json=self.example,headers=headers)
        self.assertEqual(first.status_code,201); self.assertEqual(first.json(),second.json())
        self.assertEqual(second.headers['Idempotency-Replayed'],'true')
        changed=dict(self.example); key=next(iter(changed)); changed[key]=str(changed[key])+'-changed'
        self.assertEqual(self.client.post('/api/records',json=changed,headers=headers).status_code,409)
        self.assertEqual(len(app.records()),1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit_events WHERE operation='record.created'"),1)
    def test_mutation_preconditions_and_archival(self):
        row=app.create(self.example); url=f"/api/records/{row['id']}"
        self.assertEqual(self.client.delete(url).status_code,428)
        self.assertEqual(self.client.delete(url,headers={'If-Match':'999'}).status_code,409)
        self.assertEqual(self.client.delete(url,headers={'If-Match':str(row['version'])}).status_code,200)
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM records WHERE deleted_at IS NOT NULL'),1)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit_events WHERE operation='record.archived'"),1)
    def test_atomic_audit_failure_rolls_back_record(self):
        with patch('backend.repository.audit',side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError): service.RecordService(app.DB,app.CONFIG).create(self.example,self.user,key='rollback-create-key')
        self.assertEqual(len(app.records()),0)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM idempotency_keys'),0)
    def test_concurrent_updates_do_not_lose_writes(self):
        row=app.create(self.example)
        def save(index):
            candidate=dict(row,engineering_note=str(index))
            try: return repository.save(app.DB,candidate)['version']
            except repository.ConflictError: return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(save,[1,2]))
        self.assertEqual(results.count(2),1); self.assertEqual(results.count('conflict'),1)
        self.assertEqual(app.records()[0]['version'],2)
    def test_legacy_database_migrations_preserve_data(self):
        path=Path(self.tmp.name)/'legacy.db'
        with sqlite3.connect(path,factory=database.Connection) as connection:
            connection.execute('CREATE TABLE records(id INTEGER PRIMARY KEY,body TEXT NOT NULL)')
            connection.execute('INSERT INTO records VALUES (?,?)',(7,json.dumps(self.example)))
        with database.connect(path) as connection:
            self.assertEqual(repository.get(connection,7)['version'],1)
            self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0],4)
        with database.connect(path) as connection: self.assertEqual(connection.execute('SELECT COUNT(*) FROM schema_migrations').fetchone()[0],4)
    def test_logout_revokes_server_session(self):
        self.assertEqual(self.client.post('/api/auth/logout').status_code,200)
        self.client.cookies.set(SETTINGS.session_cookie,self.token)
        self.assertEqual(self.client.get('/api/records').status_code,401)
    def test_session_expiry(self):
        with database.transaction(app.DB) as connection: connection.execute('UPDATE sessions SET expires_at=0')
        self.assertEqual(self.client.get('/api/records').status_code,401)
    def test_login_cookie_contract_and_no_secret_in_response(self):
        self.client.cookies.clear()
        response=self.client.post('/api/auth/login',json={'username':'platform-admin','password':PASSWORD})
        self.assertEqual(response.status_code,200)
        self.assertEqual(set(response.json()),{'id','username','role'})
        cookies=' '.join(response.headers.get_list('set-cookie'))
        self.assertIn('HttpOnly',cookies); self.assertIn('SameSite=strict',cookies)
    def test_login_throttle(self):
        self.client.cookies.clear()
        for _ in range(5): self.assertEqual(self.client.post('/api/auth/login',json={'username':'platform-admin','password':'Wrong-password-2026'}).status_code,401)
        self.assertEqual(self.client.post('/api/auth/login',json={'username':'platform-admin','password':PASSWORD}).status_code,429)
    def test_last_admin_and_immediate_role_enforcement(self):
        url=f"/api/admin/users/{self.user['id']}/role"
        self.assertEqual(self.client.patch(url,json={'role':'viewer'}).status_code,409)
        with database.transaction(app.DB) as connection:
            connection.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',('second-admin',FIXTURE_HASH,'admin',repository.now()))
        self.assertEqual(self.client.patch(url,json={'role':'viewer'}).status_code,200)
        self.assertEqual(self.client.get('/api/admin/users').status_code,403)
        self.assertEqual(self.client.post('/api/records',json=self.example).status_code,403)
    def test_pagination_validation_and_etags(self):
        for index in range(3):
            data=dict(self.example); key=next(iter(data)); data[key]=str(data[key])+f'-{index}'
            if 'reference' in data: data['reference']+=f'-{index}'
            app.create(data)
        page=self.client.get('/api/v1/records',params={'limit':1,'offset':1}).json()
        self.assertEqual(page['total'],3); self.assertEqual(len(page['items']),1)
        self.assertEqual(self.client.get('/api/v1/records',params={'limit':0}).status_code,422)
        row=app.records()[0]
        self.assertEqual(self.client.get(f"/api/records/{row['id']}").headers['ETag'],'"1"')
    def test_origin_and_body_limits(self):
        self.assertEqual(self.client.post('/api/records',json=self.example,headers={'Origin':'https://untrusted.invalid'}).status_code,403)
        self.assertEqual(self.client.post('/api/records',json={'payload':'x'*40000}).status_code,413)

if __name__=='__main__': unittest.main()

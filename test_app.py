import unittest, tempfile
from pathlib import Path
from fastapi.testclient import TestClient
import app
import api

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); app.DB = Path(self.tmp.name)/'test.db'
        self.example = dict(app.CONFIG['example'])
        self.client = TestClient(api.app)
    def tearDown(self): self.client.close(); self.tmp.cleanup()
    def test_roundtrip_and_summary(self):
        row = app.create(self.example)
        self.assertEqual(app.records()[0]['id'],row['id'])
        self.assertIsInstance(app.summary(app.records()),dict)
    def test_missing_field_rejected(self):
        self.example.pop(next(iter(self.example)))
        with self.assertRaises(ValueError): app.create(self.example)
    def test_business_rule(self):
        row = app.create(self.example); kind = app.CONFIG['kind']
        if kind == 'booking':
            with self.assertRaises(ValueError): app.create(self.example)
        elif kind == 'releases':
            app.action(row['id'],'promote')
            with self.assertRaises(ValueError): app.action(row['id'],'promote')
            app.action(row['id'],'approve'); self.assertEqual(app.action(row['id'],'promote')['environment'],'production')
        elif kind == 'jobs':
            app.work_once(); self.assertEqual(app.records()[0]['result'],'ALICE,BOB')
        elif kind == 'inventory':
            for _ in range(8): app.action(row['id'],'consume')
            with self.assertRaises(ValueError): app.action(row['id'],'consume')
            self.assertEqual(app.action(row['id'],'restock')['quantity'],1)
        elif kind in ['taskboard','support']: self.assertNotEqual(app.action(row['id'],'advance')['status'],row['status'])
        elif kind == 'cost': self.assertEqual(app.summary(app.records())['monthly_estimate'],87.6)
        elif kind == 'policy':
            self.example['public'] = True; app.create(self.example)
            self.assertEqual(app.summary(app.records())['failing'],1)
        elif kind == 'logs': self.assertEqual(app.summary(app.records())['ERROR'],1)
        elif kind == 'uptime':
            with self.assertRaises(ValueError): app.create(dict(self.example,url='file:///etc/passwd'))
    def test_http_api(self):
        self.assertEqual(self.client.get('/health').json()['status'],'ok')
        response = self.client.post('/api/records',json=self.example)
        self.assertEqual(response.status_code,201); row = response.json()
        self.assertEqual(len(self.client.get('/api/records',params={'q':str(row['id'])}).json()),1)
        self.assertTrue(self.client.delete('/api/records/'+str(row['id'])).json()['deleted'])
        self.assertEqual(self.client.delete('/api/records/'+str(row['id'])).status_code,404)
        self.assertEqual(self.client.post('/api/records',json={}).status_code,400)
    def test_invalid_transport_and_unknown_action(self):
        self.assertEqual(self.client.post('/api/records',json=[]).status_code,422)
        self.assertEqual(self.client.post('/api/records',content='broken',headers={'Content-Type':'application/json'}).status_code,422)
        row = app.create(self.example)
        self.assertEqual(self.client.post(f"/api/records/{row['id']}/unsupported").status_code,400)
        self.assertEqual(self.client.post('/api/records/999999/advance').status_code,404)
    def test_metrics_and_openapi(self):
        app.create(self.example)
        self.assertIn('portfolio_records 1',self.client.get('/metrics').text)
        schema = self.client.get('/openapi.json').json()
        self.assertIn('/api/records',schema['paths'])
    def test_domain_boundaries(self):
        if app.CONFIG['kind'] == 'booking':
            app.create(self.example)
            app.create(dict(self.example,start=self.example['end'],end='2026-10-05T11:00'))
            self.assertEqual(len(app.records()),2)
        elif app.CONFIG['kind'] == 'cost':
            with self.assertRaises(ValueError): app.create(dict(self.example,hourly_cost=float('inf')))
        elif app.CONFIG['kind'] == 'policy':
            with self.assertRaises(ValueError): app.create(dict(self.example,encrypted='true'))
        elif app.CONFIG['kind'] == 'jobs':
            self.assertFalse(app.work_once())
            for operation, payload, expected in [('word_count','one two',2),('sort_lines','z\na','a\nz')]:
                app.create(dict(self.example,operation=operation,payload=payload)); app.work_once()
                self.assertEqual(app.records()[0]['result'],expected)
        else:
            example = dict(self.example); first = next(iter(example)); example[first] = ''
            with self.assertRaises(ValueError): app.create(example)

if __name__ == '__main__': unittest.main()

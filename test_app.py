import unittest, tempfile, json, threading
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
import app

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); app.DB = Path(self.tmp.name)/'test.db'
        self.example = dict(app.CONFIG['example'])
    def tearDown(self): self.tmp.cleanup()
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
        elif kind == 'inventory': self.assertEqual(app.action(row['id'],'consume')['quantity'],7)
        elif kind in ['taskboard','support']: self.assertNotEqual(app.action(row['id'],'advance')['status'],row['status'])
        elif kind == 'cost': self.assertEqual(app.summary(app.records())['monthly_estimate'],87.6)
        elif kind == 'policy':
            self.example['public'] = True; app.create(self.example)
            self.assertEqual(app.summary(app.records())['failing'],1)
        elif kind == 'logs': self.assertEqual(app.summary(app.records())['ERROR'],1)
        elif kind == 'uptime':
            with self.assertRaises(ValueError): app.create(dict(self.example,url='file:///etc/passwd'))
    def test_http_api(self):
        server = ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        try:
            with urlopen(base+'/health') as r: self.assertEqual(json.load(r)['status'],'ok')
            request = Request(base+'/api/records',data=json.dumps(self.example).encode(),headers={'Content-Type':'application/json'})
            with urlopen(request) as r: self.assertEqual(r.status,201); row=json.load(r)
            with urlopen(base+'/api/records?q='+str(row['id'])) as r: self.assertEqual(len(json.load(r)),1)
            with urlopen(Request(base+'/api/records/'+str(row['id']),method='DELETE')) as r: self.assertTrue(json.load(r)['deleted'])
            with self.assertRaises(HTTPError) as error: urlopen(Request(base+'/api/records',data=b'{}'))
            self.assertEqual(error.exception.code,400)
        finally: server.shutdown(); server.server_close(); thread.join()

if __name__ == '__main__': unittest.main()

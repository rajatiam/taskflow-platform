"""FastAPI transport for the domain and SQLite application."""
from contextlib import asynccontextmanager
import json
import threading
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
import app as store

STOP = threading.Event()

def job_worker():
    while not STOP.is_set():
        store.work_once()
        STOP.wait(0.5)

@asynccontextmanager
async def lifespan(application):
    store.connect().close()
    thread = None
    STOP.clear()
    if store.CONFIG['kind'] == 'jobs':
        with store.LOCK:
            for row in store.records():
                if row['status'] == 'running':
                    row['status'] = 'queued'; store.save(row)
        thread = threading.Thread(target=job_worker, daemon=True)
        thread.start()
    yield
    STOP.set()
    if thread: thread.join(timeout=5)

app = FastAPI(title=store.CONFIG['name'], version='2.0.0', lifespan=lifespan)

@app.exception_handler(ValueError)
async def bad_value(request, exc):
    return JSONResponse(status_code=400, content={'error':str(exc)})

@app.exception_handler(LookupError)
async def not_found(request, exc):
    return JSONResponse(status_code=404, content={'error':str(exc)})

@app.get('/health', tags=['operations'])
def health():
    with store.connect() as connection: connection.execute('SELECT 1').fetchone()
    return {'status':'ok', 'project':store.CONFIG['name']}

@app.get('/metrics', response_class=PlainTextResponse, tags=['operations'])
def metrics():
    return '# HELP portfolio_records Stored business records\n# TYPE portfolio_records gauge\nportfolio_records ' + str(len(store.records())) + '\n'

@app.get('/api/config', tags=['configuration'])
def config(): return store.CONFIG

def filtered(q):
    return [r for r in store.records() if q.lower() in json.dumps(r).lower()]

@app.get('/api/records', tags=['records'])
def records(q: str = ''): return filtered(q)

@app.get('/api/summary', tags=['analytics'])
def summary(q: str = ''): return store.summary(filtered(q))

@app.post('/api/records', status_code=201, tags=['records'])
def create(data: dict = Body(...)): return store.create(data)

@app.delete('/api/records/{key}', tags=['records'])
def delete(key: int):
    with store.LOCK, store.connect() as connection:
        count = connection.execute('DELETE FROM records WHERE id=?', (key,)).rowcount
    if not count: raise HTTPException(404, 'Record not found')
    return {'deleted':True}

@app.post('/api/records/{key}/{action}', tags=['workflows'])
def act(key: int, action: str): return store.action(key, action)

# The Angular production bundle is served on the same origin as the API.
FRONTEND = store.BASE / 'frontend' / 'dist' / 'portfolio' / 'browser'
if (FRONTEND / 'index.html').exists():
    app.mount('/', StaticFiles(directory=FRONTEND, html=True), name='angular')
else:
    @app.get('/', response_class=HTMLResponse, include_in_schema=False)
    def frontend_help():
        return '<h1>Python API is running</h1><p>Run npm ci and npm run build in frontend/, then restart Python. For development, use npm start in frontend/.</p><a href="/docs">API documentation</a>'

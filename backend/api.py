"""FastAPI boundary: identity, authorization, concurrency, and observability."""
from contextlib import asynccontextmanager
import json, logging, re, threading, time, uuid
from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from . import configuration, database, domain, repository, security, service
from .models import Credentials, Page, RecordOut, RoleChange
import app as store

SETTINGS=configuration.settings(store.CONFIG)
LOGGER=logging.getLogger('portfolio.requests')
STOP=threading.Event()

def worker():
    while not STOP.is_set():
        try: store.work_once()
        except Exception: LOGGER.exception('background worker failed')
        STOP.wait(.5)

@asynccontextmanager
async def lifespan(application):
    store.connect().close(); STOP.clear(); thread=None
    if store.CONFIG['kind']=='jobs':
        for row in store.records():
            if row['status']=='running': row['status']='queued'; store.save(row)
        thread=threading.Thread(target=worker,daemon=True); thread.start()
    yield
    STOP.set()
    if thread: thread.join(timeout=5)

app=FastAPI(title=store.CONFIG['name'],version='3.1.0',lifespan=lifespan)

@app.middleware('http')
async def boundaries(request: Request,call_next):
    supplied=request.headers.get('X-Request-ID','')
    request.state.request_id=supplied if re.fullmatch(r'[A-Za-z0-9-]{8,64}',supplied) else uuid.uuid4().hex
    if request.method in ['POST','PUT','PATCH','DELETE']:
        origin=request.headers.get('origin')
        if origin and origin not in SETTINGS.origins: return JSONResponse({'error':'Untrusted request origin','code':'origin_rejected'},status_code=403)
        body=bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body)>32768: return JSONResponse({'error':'Request body exceeds 32 KiB','code':'body_too_large'},status_code=413)
        request._body=bytes(body)
    started=time.monotonic()
    response=await call_next(request)
    response.headers['X-Request-ID']=request.state.request_id
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    if request.url.path.startswith('/api/'): response.headers['Cache-Control']='no-store'
    LOGGER.info(json.dumps({'request_id':request.state.request_id,'method':request.method,'path':request.url.path,'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000,2)}))
    return response

def error(request,status,code,message):
    return JSONResponse({'error':str(message),'code':code,'request_id':getattr(request.state,'request_id','unknown')},status_code=status)

for exception,status,code in [(ValueError,400,'domain_validation'),(LookupError,404,'not_found'),(repository.ConflictError,409,'conflict'),(repository.PreconditionError,428,'precondition_required'),(security.AuthError,401,'unauthenticated'),(security.ForbiddenError,403,'forbidden'),(security.RateLimitError,429,'rate_limited')]:
    def handler_factory(status,code):
        async def handler(request,exc): return error(request,status,code,exc)
        return handler
    app.add_exception_handler(exception,handler_factory(status,code))

@app.exception_handler(RequestValidationError)
async def invalid_input(request,exc): return error(request,422,'invalid_input','Request fields do not match the API schema')

def current_user(request: Request):
    user=security.session(store.DB,request.cookies.get(SETTINGS.session_cookie))
    if request.method not in ['GET','HEAD','OPTIONS']: security.check_csrf(user,request.headers.get('X-CSRF-Token'))
    return user

def editor(user=Depends(current_user)):
    security.require(user,{'editor','admin'}); return user

def administrator(user=Depends(current_user)):
    security.require(user,{'admin'}); return user

def cookies(response,user):
    token,csrf=security.issue_session(store.DB,user)
    response.set_cookie(SETTINGS.session_cookie,token,max_age=3600,httponly=True,secure=SETTINGS.secure_cookie,samesite='strict')
    response.set_cookie(SETTINGS.csrf_cookie,csrf,max_age=3600,httponly=False,secure=SETTINGS.secure_cookie,samesite='strict')

@app.post('/api/auth/register',status_code=201,tags=['identity'])
def register(data: Credentials,response: Response):
    if not SETTINGS.registration_enabled: raise security.ForbiddenError('Self-registration is disabled in this environment')
    user=security.register(store.DB,data.username,data.password); cookies(response,user); return user

@app.post('/api/auth/login',tags=['identity'])
def login(data: Credentials,request: Request,response: Response):
    address=request.client.host if request.client else 'unknown'
    user=security.login(store.DB,data.username,data.password,address); cookies(response,user); return user

@app.get('/api/auth/me',tags=['identity'])
def me(user=Depends(current_user)): return {k:user[k] for k in ['id','username','role']}

@app.post('/api/auth/logout',tags=['identity'])
def logout(request: Request,response: Response,user=Depends(current_user)):
    security.logout(store.DB,request.cookies[SETTINGS.session_cookie])
    response.delete_cookie(SETTINGS.session_cookie); response.delete_cookie(SETTINGS.csrf_cookie)
    return {'signed_out':True}

@app.get('/health',tags=['operations'])
def health():
    with store.connect() as connection: version=connection.execute('PRAGMA user_version').fetchone()[0]
    return {'status':'ok','project':store.CONFIG['name'],'schema_version':version}

@app.get('/metrics',response_class=PlainTextResponse,tags=['operations'])
def metrics(): return '# HELP portfolio_records Active business records\n# TYPE portfolio_records gauge\nportfolio_records '+str(len(store.records()))+'\n'

@app.get('/api/config',tags=['configuration'])
def config(user=Depends(current_user)): return store.CONFIG

def resources(): return service.RecordService(store.DB,store.CONFIG)

@app.get('/api/records',response_model=list[RecordOut],tags=['records'])
def records(q: str='',limit: int=Query(1000,ge=1,le=1000),offset: int=Query(0,ge=0),user=Depends(current_user)):
    return resources().list(q,limit,offset)['items']

@app.get('/api/v1/records',response_model=Page,tags=['versioned records'])
def page(q: str='',limit: int=Query(50,ge=1,le=1000),offset: int=Query(0,ge=0),user=Depends(current_user)):
    return resources().list(q,limit,offset)

@app.get('/api/records/{key}',response_model=RecordOut,tags=['records'])
def record(key: int,response: Response,user=Depends(current_user)):
    row=resources().get(key); response.headers['ETag']=f'"{row["version"]}"'; return row

@app.get('/api/summary',tags=['analytics'])
def summary(q: str='',user=Depends(current_user)):
    rows=[row for row in store.records() if q.lower() in json.dumps(row).lower()]
    return domain.summary(rows)

@app.post('/api/records',response_model=RecordOut,status_code=201,tags=['records'])
def create(request: Request,response: Response,data: dict=Body(...),user=Depends(editor)):
    row,replayed=resources().create(data,user,request.state.request_id,request.headers.get('Idempotency-Key'))
    response.headers['ETag']=f'"{row["version"]}"'
    response.headers['Idempotency-Replayed']=str(replayed).lower()
    return row

@app.post('/api/records/{key}/{action}',response_model=RecordOut,tags=['workflows'])
def act(key: int,action: str,request: Request,response: Response,user=Depends(editor)):
    row=resources().act(key,action,user,request.headers.get('If-Match'),request.state.request_id)
    response.headers['ETag']=f'"{row["version"]}"'; return row

@app.delete('/api/records/{key}',tags=['records'])
def delete(key: int,request: Request,user=Depends(editor)):
    return resources().delete(key,user,request.headers.get('If-Match'),request.state.request_id)

@app.get('/api/audit',tags=['administration'])
def audit(limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),user=Depends(administrator)):
    with store.connect() as connection:
        rows=connection.execute('SELECT * FROM audit_events ORDER BY id DESC LIMIT ? OFFSET ?',(limit,offset)).fetchall()
        total=connection.execute('SELECT COUNT(*) FROM audit_events').fetchone()[0]
    return {'items':[dict(row,metadata=json.loads(row['metadata'])) for row in rows],'total':total,'limit':limit,'offset':offset}

@app.get('/api/admin/users',tags=['administration'])
def users(user=Depends(administrator)):
    with store.connect() as connection: return [dict(row) for row in connection.execute('SELECT id,username,role,active,created_at FROM users ORDER BY id')]

@app.patch('/api/admin/users/{key}/role',tags=['administration'])
def role(key: int,data: RoleChange,request: Request,user=Depends(administrator)):
    return security.change_role(store.DB,key,data.role,user,request.state.request_id)


@app.get('/api/admin/archives',tags=['administration'])
def archives(limit: int=Query(50,ge=1,le=200),offset: int=Query(0,ge=0),user=Depends(administrator)):
    return resources().archives(limit,offset)

@app.post('/api/admin/archives/{key}/restore',response_model=RecordOut,tags=['administration'])
def restore(key: int,request: Request,response: Response,user=Depends(administrator)):
    row=resources().restore(key,user,request.headers.get('If-Match'),request.state.request_id)
    response.headers['ETag']=f'"{row["version"]}"'; return row

@app.get('/api/exports/records',tags=['exports'])
def export_records(format: str=Query('json',pattern='^(json|csv)$'),q: str='',user=Depends(current_user)):
    from .exports import render
    page=resources().list(q,5001,0)
    if page['total']>5000: raise HTTPException(status_code=413,detail='Export is limited to 5000 records; narrow the search')
    return Response(render(page['items'],format),media_type='application/json' if format=='json' else 'text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{store.CONFIG["slug"]}.{format}"'})

# Custom project routes are injected here before the Angular static mount.


FRONTEND=store.BASE/'frontend/dist/portfolio/browser'
if (FRONTEND/'index.html').exists(): app.mount('/',StaticFiles(directory=FRONTEND,html=True),name='angular')
else:
    @app.get('/',response_class=HTMLResponse,include_in_schema=False)
    def frontend_help(): return '<h1>Backend ready</h1><p>Build frontend/ with npm ci and npm run build, then restart Python.</p><a href="/docs">API documentation</a>'

"""Hashed passwords, opaque revocable sessions, RBAC, and login throttling."""
import hashlib, hmac, secrets, time
from . import database, repository

ITERATIONS=600000
ROLES={'viewer','editor','admin'}

class AuthError(Exception): pass
class ForbiddenError(Exception): pass
class RateLimitError(Exception): pass

def digest(value): return hashlib.sha256(value.encode()).hexdigest()

def password_hash(password):
    salt=secrets.token_hex(16)
    result=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),ITERATIONS).hex()
    return f'pbkdf2_sha256${ITERATIONS}${salt}${result}'

def check_password(password,stored):
    try:
        algorithm,iterations,salt,expected=stored.split('$')
        if algorithm!='pbkdf2_sha256': return False
        result=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),int(iterations)).hex()
        return hmac.compare_digest(result,expected)
    except (ValueError,TypeError): return False

def public_user(row): return {k:row[k] for k in ['id','username','role']}

def register(path,username,password,role='editor'):
    if role not in ROLES: raise ValueError('Invalid role')
    hashed=password_hash(password)
    with database.transaction(path) as connection:
        if connection.execute('SELECT 1 FROM users WHERE username=?',(username,)).fetchone(): raise repository.ConflictError('Username already exists')
        key=connection.execute('INSERT INTO users(username,password_hash,role,created_at) VALUES (?,?,?,?)',(username,hashed,role,repository.now())).lastrowid
        user={'id':key,'username':username,'role':role}
        repository.audit(connection,user,'user.register',None,'authentication',{'role':role})
        return user

def issue_session(path,user,ttl=3600):
    token=secrets.token_urlsafe(48); csrf=secrets.token_urlsafe(32)
    with database.transaction(path) as connection:
        connection.execute('DELETE FROM sessions WHERE expires_at<?',(int(time.time()),))
        connection.execute('INSERT INTO sessions(token_hash,user_id,csrf_hash,expires_at) VALUES (?,?,?,?)',(digest(token),user['id'],digest(csrf),int(time.time())+ttl))
    return token,csrf

def session(path,token):
    if not token: raise AuthError('Sign in to access this workspace')
    with database.connect(path) as connection:
        row=connection.execute('SELECT u.id,u.username,u.role,s.csrf_hash FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',(digest(token),int(time.time()))).fetchone()
    if row is None: raise AuthError('Session expired or revoked')
    return dict(row)

def login(path,username,password,address):
    current=int(time.time())
    with database.transaction(path) as connection:
        connection.execute('DELETE FROM login_attempts WHERE occurred_at<?',(current-900,))
        count=connection.execute('SELECT COUNT(*) FROM login_attempts WHERE address=? AND occurred_at>=?',(address,current-900)).fetchone()[0]
        if count>=5: raise RateLimitError('Too many failed sign-ins; try again after fifteen minutes')
        row=connection.execute('SELECT * FROM users WHERE username=? AND active=1',(username,)).fetchone()
    # Derive a hash even for unknown usernames, reducing username timing leakage.
    stored=row['password_hash'] if row else f'pbkdf2_sha256${ITERATIONS}$'+('00'*16)+'$'+('00'*32)
    valid=check_password(password,stored)
    if not valid or row is None:
        with database.transaction(path) as connection:
            connection.execute('INSERT INTO login_attempts(address,occurred_at) VALUES (?,?)',(address,current))
        raise AuthError('Invalid username or password')
    user=public_user(row)
    with database.transaction(path) as connection:
        connection.execute('DELETE FROM login_attempts WHERE address=?',(address,))
        repository.audit(connection,user,'user.login',None,'authentication')
    return user

def require(user,roles):
    if user['role'] not in roles: raise ForbiddenError('Your role cannot perform this operation')

def check_csrf(user,value):
    if not value or not hmac.compare_digest(digest(value),user['csrf_hash']): raise ForbiddenError('Invalid CSRF token')

def logout(path,token):
    with database.transaction(path) as connection:
        connection.execute('DELETE FROM sessions WHERE token_hash=?',(digest(token),))

def change_role(path,key,role,actor,request_id):
    require(actor,{'admin'})
    if role not in ROLES: raise ValueError('Invalid role')
    with database.transaction(path) as connection:
        user=connection.execute('SELECT * FROM users WHERE id=?',(key,)).fetchone()
        if user is None: raise LookupError('User not found')
        admins=connection.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
        if user['role']=='admin' and role!='admin' and admins<=1: raise repository.ConflictError('The last administrator cannot be demoted')
        connection.execute('UPDATE users SET role=? WHERE id=?',(role,key))
        repository.audit(connection,actor,'user.role_changed',None,request_id,{'user_id':key,'role':role})
        return {'id':key,'username':user['username'],'role':role}

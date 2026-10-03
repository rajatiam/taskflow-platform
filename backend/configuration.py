"""Configuration has explicit development and deployment boundaries."""
from dataclasses import dataclass
import hashlib, os

@dataclass(frozen=True)
class Settings:
    port: int
    host: str
    session_cookie: str
    csrf_cookie: str
    secure_cookie: bool
    registration_enabled: bool
    origins: frozenset[str]

def settings(config):
    namespace=hashlib.sha256(config['slug'].encode()).hexdigest()[:12]
    port=int(os.environ.get('PORT',config['port']))
    production=os.environ.get('APP_ENV','development')=='production'
    defaults=[f'http://{host}:{p}' for host in ['localhost','127.0.0.1'] for p in [port,config['port']-3900]]
    origins=frozenset(filter(None,os.environ.get('ALLOWED_ORIGINS',','.join(defaults)).split(',')))
    return Settings(port,os.environ.get('HOST','127.0.0.1'),'session_'+namespace,'csrf_'+namespace,production,os.environ.get('REGISTRATION_ENABLED','false' if production else 'true')=='true',origins)

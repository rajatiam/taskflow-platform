"""Input contracts shared inside this repository, not across repositories."""
import math
from urllib.parse import urlparse

def validate_input(data,example):
    if not isinstance(data,dict): raise ValueError('JSON object required')
    unknown=set(data)-set(example)
    if unknown: raise ValueError('Unknown fields: '+', '.join(sorted(unknown)))
    result={}
    for key,sample in example.items():
        value=data.get(key)
        if isinstance(sample,bool):
            if not isinstance(value,bool): raise ValueError(key+' must be boolean')
        elif isinstance(sample,(int,float)):
            if isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 or value>1e12 or not math.isfinite(value): raise ValueError(key+' must be finite, nonnegative, and at most one trillion')
            if isinstance(sample,int) and not isinstance(value,int): raise ValueError(key+' must be an integer')
        elif not isinstance(value,str) or not value.strip() or len(value)>2000: raise ValueError(key+' requires text, up to 2000 characters')
        result[key]=value.strip() if isinstance(value,str) else value
    return result

def http_url(value):
    url=urlparse(value)
    if url.scheme not in ['http','https'] or not url.hostname or url.username or url.password: raise ValueError('HTTP(S) URL without credentials required')

def unique(records,row,fields):
    if any(all(r[f]==row[f] for f in fields) for r in records): raise ValueError('Duplicate '+', '.join(fields))

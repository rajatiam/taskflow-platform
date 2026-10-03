import csv, hashlib, io, json, math, re
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from .validation import validate_input, http_url, unique

def now(): return datetime.now(timezone.utc).isoformat()
def validate(data,records): return initialize(validate_input(data,CONFIG['example']),records)

def initialize(row,records):
    if row['status'] not in ['todo','doing','done']: raise ValueError('Status must be todo, doing, or done')
    return row
def summary(rows): return {status:sum(r['status']==status for r in rows) for status in ['todo','doing','done']}
def transition(row,action):
    if action!='advance': raise ValueError('Unsupported task action')
    if row['status']=='done': raise ValueError('Completed task cannot advance')
    return dict(row,status='doing' if row['status']=='todo' else 'done')

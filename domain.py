import json
from datetime import datetime
from urllib.parse import urlparse

def validate(data, records):
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    result = {}
    for key, example in CONFIG["example"].items():
        value = data.get(key)
        if isinstance(example, bool):
            if not isinstance(value, bool): raise ValueError(key + " must be boolean")
        elif isinstance(example, (int, float)):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not __import__('math').isfinite(value) or value < 0:
                raise ValueError(key + " must be a finite nonnegative number")
            if isinstance(example, int) and not isinstance(value, int): raise ValueError(key + " must be an integer")
        elif not isinstance(value, str) or not value.strip() or len(value) > 2000:
            raise ValueError(key + " requires text (maximum 2000 characters)")
        result[key] = value.strip() if isinstance(value, str) else value
    kind = CONFIG["kind"]
    choices = {"taskboard":("status",["todo","doing","done"]), "support":("status",["open","investigating","resolved"]), "logs":("level",["DEBUG","INFO","WARN","ERROR"]), "jobs":("operation",["uppercase","word_count","sort_lines"]), "releases":("environment",["dev"])}
    if kind in choices:
        key, allowed = choices[kind]
        if result[key] not in allowed: raise ValueError(key + " must be one of " + ', '.join(allowed))
    if kind == "support" and result["priority"] not in ["low","medium","high"]: raise ValueError("Invalid priority")
    if kind == "booking":
        try:
            start, end = datetime.fromisoformat(result['start']), datetime.fromisoformat(result['end'])
            if start.tzinfo or end.tzinfo: raise ValueError("Use local times without timezone offsets")
        except (ValueError, TypeError): raise ValueError("Use ISO local timestamps, e.g. 2026-10-05T09:00")
        if end <= start: raise ValueError("End must follow start")
        for row in records:
            if row['resource'] == result['resource'] and start < datetime.fromisoformat(row['end']) and end > datetime.fromisoformat(row['start']):
                raise ValueError("Resource already booked during this interval")
    if kind == "uptime":
        url = urlparse(result['url'])
        if url.scheme not in ['http','https'] or not url.hostname or url.username or url.password: raise ValueError("Use an HTTP(S) URL without credentials")
    if kind == "jobs": result.update(status='queued', attempts=0, result=None, error=None)
    if kind == "releases": result['history'] = ['Created in dev']
    return result

def summary(rows):
    kind = CONFIG['kind']
    if kind == 'inventory': return {'items':len(rows), 'low_stock':sum(r['quantity'] <= r['reorder_level'] for r in rows), 'units':sum(r['quantity'] for r in rows)}
    if kind == 'cost':
        spend = sum(r['hourly_cost'] * r['monthly_hours'] for r in rows)
        teams = {}
        for r in rows: teams[r['team']] = round(teams.get(r['team'],0) + r['hourly_cost'] * r['monthly_hours'],2)
        return {'monthly_estimate':round(spend,2), 'over_budget':sum(r['hourly_cost'] * r['monthly_hours'] > r['budget'] for r in rows), 'by_team':teams}
    if kind == 'policy':
        findings = [{'id':r['id'], 'name':r['name'], 'violations':[label for key,label in [('public','Public access'),('encrypted','Encryption disabled'),('backup','Backups disabled')] if (r[key] if key == 'public' else not r[key])]} for r in rows]
        return {'checked':len(rows), 'failing':sum(bool(f['violations']) for f in findings), 'findings':findings}
    field = {'taskboard':'status','support':'priority','jobs':'status','logs':'level','releases':'environment'}.get(kind)
    if field: return {value:sum(r[field] == value for r in rows) for value in sorted({r[field] for r in rows})}
    if kind == 'uptime': return {'targets':len(rows), 'healthy':sum(r.get('healthy',False) for r in rows), 'checked':sum('checked_at' in r for r in rows)}
    return {'bookings':len(rows), 'resources':len({r['resource'] for r in rows})}

def transition(row, action):
    kind = CONFIG['kind']
    if kind == 'taskboard' and action == 'advance':
        flow = ['todo','doing','done']; row['status'] = flow[min(flow.index(row['status'])+1,2)]
    elif kind == 'support' and action == 'advance':
        flow = ['open','investigating','resolved']; row['status'] = flow[min(flow.index(row['status'])+1,2)]
    elif kind == 'inventory' and action in ['restock','consume']:
        if action == 'consume' and row['quantity'] == 0: raise ValueError('No stock available')
        row['quantity'] += 1 if action == 'restock' else -1
    elif kind == 'releases' and action in ['promote','approve']:
        if action == 'approve':
            if row['environment'] != 'staging': raise ValueError('Approval requires staging')
            row['approved'] = True; row['history'].append('Approved in staging')
        else:
            if row['environment'] == 'production': raise ValueError('Already in production')
            if row['environment'] == 'staging' and not row.get('approved'): raise ValueError('Approve before production promotion')
            row['environment'] = 'staging' if row['environment'] == 'dev' else 'production'
            row['history'].append('Promoted to ' + row['environment'])
    elif kind == 'jobs' and action == 'retry':
        if row['status'] != 'failed': raise ValueError('Only failed jobs can retry')
        row.update(status='queued', error=None)
    else: raise ValueError('Unsupported action')
    return row

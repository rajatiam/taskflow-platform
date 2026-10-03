"""Versioned migrations and explicit SQLite units of work."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading

MIGRATIONS=Path(__file__).parent/'migrations'
LOCK=threading.RLock()

class Connection(sqlite3.Connection):
    def __exit__(self,*args):
        try: return super().__exit__(*args)
        finally: self.close()

def connect(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    connection=sqlite3.connect(path,timeout=15,factory=Connection)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=15000')
    migrations=sorted(MIGRATIONS.glob('*.sql'))
    latest=len(migrations)
    if connection.execute('PRAGMA user_version').fetchone()[0] != latest:
        with LOCK:
            try:
                connection.execute('BEGIN IMMEDIATE')
                connection.execute('CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)')
                current=connection.execute('PRAGMA user_version').fetchone()[0]
                if current>latest: raise RuntimeError('Database schema is newer than the application')
                for version,file in enumerate(migrations,1):
                    if version<=current: continue
                    for statement in file.read_text(encoding='utf-8').split(';'):
                        if statement.strip(): connection.execute(statement)
                    connection.execute('INSERT INTO schema_migrations(version) VALUES (?)',(version,))
                    connection.execute('PRAGMA user_version='+str(version))
                connection.commit()
            except BaseException:
                connection.rollback(); connection.close(); raise
    return connection

@contextmanager
def transaction(path):
    connection=connect(path)
    try:
        connection.execute('BEGIN IMMEDIATE')
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback(); raise
    finally: connection.close()

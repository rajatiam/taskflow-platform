CREATE TABLE audit_events(id INTEGER PRIMARY KEY, actor_id INTEGER REFERENCES users(id), actor TEXT NOT NULL, operation TEXT NOT NULL, record_id INTEGER, request_id TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX audit_events_created ON audit_events(id DESC);
CREATE TABLE idempotency_keys(user_id INTEGER NOT NULL REFERENCES users(id), key TEXT NOT NULL, fingerprint TEXT NOT NULL, response TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(user_id,key));
CREATE INDEX idempotency_expiry ON idempotency_keys(created_at);

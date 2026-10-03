ALTER TABLE records ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE records ADD COLUMN created_at TEXT;
ALTER TABLE records ADD COLUMN deleted_at TEXT;
UPDATE records SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL;
CREATE INDEX records_active ON records(deleted_at,id DESC);

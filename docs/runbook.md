# Operations runbook

## Startup and readiness

Build Angular, apply `python manage.py migrate`, create an administrator using the interactive CLI, and start `python run.py`. Check `/health` for status and schema version 4. `DATABASE_PATH` selects the persistent database location. `PORT` and `HOST` select the bind address.

Docker Compose builds both tiers into one non-root image and persists SQLite in a named volume. Compose is a local development configuration. Kubernetes examples require a persistent volume and one replica; do not scale a shared SQLite deployment to multiple writers.

## Production adaptation

Set `APP_ENV=production`, `REGISTRATION_ENABLED=false`, and `ALLOWED_ORIGINS=https://your-host.example`. Terminate TLS before using production Secure cookies. Provision administrator identity through the CLI on the persistent data volume. Configure network egress, backups, ingress limits and monitoring. Restrict operational endpoints if they are exposed publicly.

## Diagnose a failure

Use X-Request-ID to correlate the structured request log and audit event. For 409, re-read the record and retry intentionally using its latest version. For an uncertain create response, retry with the original Idempotency-Key and input. A role change takes effect on the next request. Sign-out revokes the persisted session.

For failed HTTP checks or webhook deliveries, inspect the persisted error and endpoint connectivity; calls time out after three seconds. Retryable worker execution may repeat after a crash. Do not infer exactly-once delivery.

## Backup and recovery

Use SQLite's backup API or stop the application before copying the database; copying only the main file while WAL writes are active is unsafe. Test restoration into a temporary DATABASE_PATH, run migrations and verify `/health` and representative records before switching traffic. Keep backups encrypted and outside the repository. Never commit `data/`, `.env`, session tokens or production credentials.

## Verification evidence

`python -m unittest -v` covers domain boundaries, API validation, anonymous access, CSRF, privilege escalation, viewer permissions, admin approvals, idempotency replay, stale writes, concurrent updates, atomic audit rollback, legacy migration, session expiry/revocation, cookie policy, throttling, last-admin protection, pagination and request limits. Real-browser checks exercise sign-in, creation, the project workflow, search, analytics, audit/access panels, mobile sizing, deletion and sign-out.

# API contract

`GET /health` and `GET /metrics` are public operational endpoints. Protect metrics at ingress when needed. `/docs` exposes the OpenAPI schema, not application data.

| Endpoint | Access | Behavior |
| --- | --- | --- |
| POST /api/auth/register | Local development | Create an editor; extra privilege fields rejected |
| POST /api/auth/login | Public, throttled | Set HttpOnly session and CSRF cookies |
| GET /api/auth/me | Signed in | Current username and role |
| POST /api/auth/logout | Signed in + CSRF | Revoke session |
| GET /api/v1/records | Viewer/editor/admin | Paginated items, total, limit, offset |
| GET /api/records/{id} | Viewer/editor/admin | Record plus ETag revision |
| POST /api/records | Editor/admin + CSRF | Create; optional Idempotency-Key |
| POST /api/records/{id}/{action} | Editor/admin + CSRF | Domain transition, requires If-Match; approve requires admin |
| DELETE /api/records/{id} | Editor/admin + CSRF | Soft deletion, requires If-Match |
| GET /api/audit | Admin | Paginated audit events |
| GET /api/admin/users | Admin | Workspace identities |
| PATCH /api/admin/users/{id}/role | Admin + CSRF | Change role, protect last admin |

The compatible `/api/records` list accepts `q`, `limit` and `offset`; the versioned route returns an envelope. Limits are validated. Domain JSON fields are listed in `project.json` and the README.

For a mutation, send the current record revision, for example `If-Match: "1"`, and the readable CSRF cookie value as `X-CSRF-Token`. Angular supplies both. A create can include a stable 8–128 character Idempotency-Key. Retrying with the same user, key and input returns the original record.

Errors include `error`, `code` and `request_id`. Relevant statuses: 401 session missing/expired, 403 role/CSRF/origin violation, 404 absent record, 409 stale revision or duplicate/idempotency conflict, 413 oversized body, 422 invalid input, 428 missing If-Match, 429 failed-login throttle. Successful responses include X-Request-ID; record reads and mutations include ETag.

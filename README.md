# Team Taskboard

Full-stack product development, REST, SQLite, filtering.

## Run locally

Requires Python 3.11 or newer. No packages, accounts, API keys, or paid services required.

```sh
python app.py
```

Open http://127.0.0.1:8101. Create the prefilled example to begin. Records persist in `data/app.db`.

```sh
python -m unittest -v
docker compose up --build
docker compose down
```

Docker is optional. Its named volume preserves data. `docker compose down --volumes` removes that data.

## Demonstration

Create tasks and advance todo → doing → done. Search by owner or status.

## Architecture

Browser (HTML/CSS/JavaScript) → Python HTTP + REST → domain rules → SQLite.
`app.py` handles transport/storage; `domain.py` implements validation and business rules; `static/` contains the responsive UI.
Writes are serialized within one process. SQLite transactions prevent partial writes. This starter intentionally uses Python's standard library so every repo runs offline after checkout.

## API

| Endpoint | Behavior |
| --- | --- |
| GET /health | Health probe |
| GET /api/config | Form schema |
| GET /api/records?q=text | List and search |
| POST /api/records | Validate and create JSON record |
| DELETE /api/records/id | Delete record |
| GET /api/summary | Domain metrics |
| POST /api/records/id/action | Applicable workflow action, JSON body `{}` |

Example payload:

```json
{
  "title": "Ship onboarding",
  "owner": "Rajat",
  "status": "todo"
}
```

## DevOps and deployment

Docker uses a non-root user; Compose provides persistent storage and health checks. GitHub Actions tests the API and business rules and builds the image. `deploy/kubernetes.yaml` demonstrates a single-replica Deployment, Service, persistent volume claim, resource limits, and health probes. Build/tag/push your image and replace `image: 01-team-taskboard:local` before deploying to a cluster; for local kind/minikube, load the image into the cluster first. The cluster needs a default storage class.

`HOST`, `PORT`, and `DATABASE_PATH` customize the server. Bind to loopback for the local demo. These apps have no authentication, TLS, or tenant isolation; add those and replace the standard-library HTTP server before exposing them publicly. Kubernetes examples are templates, not verified cloud deployments. Releases, cost, and policy projects use local data as explained above.

## Portfolio talking points

- Explain a business invariant and show its test.
- Trace a browser action through API validation to persistence.
- Show CI, image build, health checks, resource sizing, and recovery behavior.
- Discuss how you would add authentication, migrations, PostgreSQL, and a managed cloud deployment.

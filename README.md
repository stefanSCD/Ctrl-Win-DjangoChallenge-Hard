# CodeRun 2026 – Django Challenge

Imports soldiers from the external API, drafts them, downloads their fights and replays every fight in parallel with Celery.

## Requirements

- Python 3.14 with the virtualenv in `.venv`
- Docker (Postgres and Redis)

## Run

```powershell
docker compose up -d
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate

# terminal 1 – Celery worker (Windows needs the threads pool)
.venv\Scripts\celery.exe -A coderun2026_starter worker --pool=threads --concurrency=20 --loglevel=info

# terminal 2 – web server
.venv\Scripts\python.exe manage.py runserver
```

Open http://127.0.0.1:8000/simulate and use the buttons in order:

1. **Import people**: downloads `/people`.
2. **Draft**: one `download_draft → apply_draft` chain per batch, all batches in parallel; adds rank and health.
3. **Download fights**: one task per batch, all in parallel; stores fights and their steps.
4. **Simulate**: one task per pending fight, all in parallel.
5. **Reset health**: restores health to 100 and marks every fight as pending again.

The page refreshes itself while tasks are running.

## Configuration

Environment variables, all optional:

| Variable | Default |
| --- | --- |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | `coderun` |
| `POSTGRES_HOST` / `POSTGRES_PORT` | `localhost` / `5432` |
| `REDIS_URL` | `redis://localhost:6379` (broker db 0, results db 1) |
| `API_BASE_URL` | the CodeRun 2026 API host |
| `API_TIMEOUT` | `300` seconds |
| `API_BATCHES` | `10` |

## Design

- `Person`: API id as primary key; `rank` and `health` are added by a separate migration (`0002`).
- `Fight`: API `fight_id` as primary key, blue/red soldiers, status and winner (the soldier who dealt more total damage; a tie is a draw).
- `FightEvent`: one row per step, unique on `(fight, order)` so a retried download never duplicates events. `defender_health_after` records the defender's health after the hit.
- `Job`: status and attempt count for each download batch, shown on the page.
- Downloads retry automatically on httpx timeouts, transport errors and 5xx responses with exponential backoff (`autoretry_for`, `retry_backoff`, `max_retries`).
- Simulation: each hit runs in its own transaction: `UPDATE health = GREATEST(health - damage, 0)` with an `F()` expression, so parallel fights involving the same soldier never lose updates. An event is applied only while its `defender_health_after` is empty (row locked with `select_for_update`), so a retried or redelivered task never applies damage twice.

## Tests

```powershell
.venv\Scripts\python.exe manage.py test registry
```

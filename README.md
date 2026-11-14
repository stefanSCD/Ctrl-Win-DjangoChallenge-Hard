# Django War Simulator — Hard

A Django application that imports people, drafts them in batches, and processes fights provided by the challenge server. Celery runs imports and fights in the background. Application data is stored in PostgreSQL and Redis is used as the Celery broker and result backend. Both run in Docker.

## Installation

Requirements: Python 3.12+, Docker Desktop.

Start PostgreSQL and Redis:

```powershell
docker compose up -d
```

Create a virtual environment and apply the migrations:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python manage.py migrate
```

All settings have local defaults matching `docker-compose.yml`. They can be overridden with environment variables: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_HOST`, `POSTGRES_PORT`, `REDIS_URL`, `API_BASE_URL`, `API_TIMEOUT` (read timeout in seconds, default 300, because the server intentionally responds slowly), `API_BATCHES` (default 10) and `CELERY_WORKER_CONCURRENCY` (default 20).

## Running the application

In a terminal with the virtual environment activated:

```powershell
celery -A coderun2026_starter worker --pool=threads --concurrency=20 --loglevel=info
```

In another terminal, also with the virtual environment activated:

```powershell
python manage.py runserver
```

Open <http://127.0.0.1:8000/simulate>.

The worker uses a thread pool because the default prefork pool is not supported on Windows. Tasks are I/O bound, so threads run them concurrently.

## Importing and simulating

Use the buttons on `/simulate` in order. Each button starts background tasks and returns immediately. Progress is shown on the page, which refreshes on its own while tasks are running, and in the worker log.

1. **Import people** downloads `/people`.
2. **Draft** starts one task chain per batch, all in parallel. Each chain downloads `/draft/<batch>` and, as soon as that batch is downloaded, applies the rank and health to the people in it.
3. **Download fights** downloads every `/fight/<batch>` in parallel and stores each fight and each of its events.
4. **Simulate** starts one Celery task per fight, all in parallel. Each task replays its fight event by event and decreases the defender's health.

Each stage requires the previous one to be complete; the buttons are disabled until then. **Reset health** restores every soldier to full health and clears fight results so the simulation can be replayed.

Download tasks retry automatically with exponential backoff and jitter (up to 6 retries) on timeouts, connection errors, HTTP 5xx and 429. Other errors, such as an invalid batch id, fail immediately and are shown on the page.

## Simulation rules

- Events of a fight are applied in order. Fights run in parallel, and the same soldier can take part in several fights at once.
- Each event locks both soldiers (`SELECT ... FOR UPDATE`, always in ascending id order to avoid deadlocks), checks their health and applies the damage in a single transaction, so concurrent fights never lose or double an update. Health never drops below 0.
- A fight stops as soon as one of its soldiers is at 0 HP, either from this fight or from another one. The remaining events are marked as skipped.
- Winner: the soldier still alive when the other one is at 0 HP. If both are alive at the end, the soldier who dealt more damage in this fight wins; equal damage is a draw.
- Re-running a task never applies an event twice, because each event keeps its own status.

Because fights run concurrently, the order in which shared soldiers lose health can differ between runs, so individual results may vary slightly.

## Data model

- `Person`: id from the API, name, age, key, rank and health (rank and health added by a separate migration for drafting).
- `Job`: one row per import batch with its status, attempts and last error.
- `Fight`: blue and red soldier, batch, status and winner.
- `FightEvent`: position in the fight, attacker, defender, damage, defender health after the hit and status (pending, applied or skipped).

## API

Host: `https://coderun2026-csbwf4haa4d0gubu.westus3-01.azurewebsites.net`.

- `/people`: people with `id`, `name`, `age`, and optionally `key`.
- `/draft-info`: drafting instructions.
- `/draft/<batch>`: people's rank and health, plus `next_batch`.
- `/fight-info`: fight import instructions.
- `/fight/<batch>`: fights and events, plus `next_batch`.
- `/simulate-fight-info`: simulation page requirements.

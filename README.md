# Django War Simulator — Hard

A Django application that imports people, drafts them in batches, and processes fights provided by the challenge server. Celery runs imports and fights in the background. Application data and the task queue use SQLite, following the starter configuration.

## Installation

Use Python 3.12 and a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
```

The API address is configured by default. Optionally, load the variables from `.env.example` into your terminal before starting the processes:

```bash
set -a
source .env.example
set +a
```

Django does not load `.env` files automatically. `CHALLENGE_READ_TIMEOUT` sets the read timeout in seconds. The default is 180 because the server intentionally responds slowly.

## Running the application

In a terminal with the virtual environment activated:

```bash
python -m celery -A coderun2026_starter worker --loglevel=INFO --concurrency=8
```

In another terminal, also with the virtual environment activated:

```bash
python manage.py runserver
```

Open <http://127.0.0.1:8000/simulate>.

Use a single Celery worker with the local SQLite broker configuration. The worker's thread pool runs tasks concurrently.

## Importing and simulating

Start each stage in order. Commands immediately return a task ID while processing continues in the worker. Follow progress in the worker log or the "Import progress" section on `/simulate`.

```bash
python manage.py import_people
```

After the people import completes:

```bash
python manage.py show_instructions
python manage.py draft_people
```

After all drafting batches complete:

```bash
python manage.py show_instructions
python manage.py import_fights
```

Batches follow `next_batch` until it is `null`. Each stage requires the previous stage to be complete. Successful imports are retained; running a command again resumes the chain using batches that have already been downloaded.

Once the fight import completes, click "Simulate unfinished fights" on `/simulate`. Each fight receives its own Celery task. The page refreshes during simulation and displays events and the defender's health after each attack.

Clicking the button again does not duplicate tasks that are already queued. Failed fights can be resumed using the same button; previously processed events do not apply additional damage. If the worker is forcibly stopped, a task may remain "queued" or "running". Check the log before restarting it. This version does not include a separate service that automatically detects abandoned tasks.

Host: `https://coderun2026-csbwf4haa4d0gubu.westus3-01.azurewebsites.net`.

- `/people`: people with `id`, `name`, `age`, and optionally `key`.
- `/draft-info`: drafting instructions.
- `/draft/<batch>`: people's rank and health, plus `next_batch`.
- `/fight-info`: fight import instructions.
- `/fight/<batch>`: fights and events, plus `next_batch`.
- `/simulate-fight-info`: simulation page requirements.

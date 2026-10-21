# GoatLifts

A powerlifting progress tracker. Log squat, bench, and deadlift sessions, see your PRs at a glance, and watch your progression over time.

## Features

- Log a session (name, date, squat, bench, deadlift) with server-side input validation
- Total is calculated automatically (squat + bench + deadlift)
- PR cards for each lift and best total
- Progression chart per lifter (Chart.js)
- Full history table with delete
- Multiple lifters supported, switch between them with a dropdown
- Data persists in SQLite

## Stack

- **Backend:** Python, Flask
- **Database:** SQLite (`sqlite3` standard library, parameterized queries)
- **Frontend:** Jinja templates, HTML/CSS, a little vanilla JavaScript, Chart.js
- **Deployment:** gunicorn (see `Procfile`)

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
```

Then open http://127.0.0.1:5000.

The database file (`goatlifts.db`) is created automatically on first run. Set `DATABASE_PATH` to store it somewhere else.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (`tests/`) runs each test against a throwaway SQLite database and covers logging, total and PR calculation, input validation, per-lifter separation, and deletes.

## Project layout

```
GoatLifts/
├── app.py              # routes, validation, database access
├── templates/
│   └── index.html      # the single page
├── static/
│   └── style.css
├── tests/              # pytest suite
├── requirements.txt
└── Procfile
```

## Deploy (Render)

1. Push this repo to GitHub.
2. In Render, create a new **Web Service** from the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`

Note: on a free Render instance the filesystem is ephemeral, so the SQLite file resets when the service restarts or redeploys. For permanent data, attach a persistent disk and point `DATABASE_PATH` at it, or move to a hosted database such as Postgres.

## Possible next steps

- User accounts so each lifter only sees and edits their own data
- Estimated 1RM calculations and per-set logging
- Postgres for durable hosting

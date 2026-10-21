# GoatLifts

A powerlifting progress tracker for a club team. Each lifter logs squat, bench, and deadlift sessions, sees their PRs and progression, and checks where they stand on the team PR board.

**Live:** https://vp7765.pythonanywhere.com

## Features

- **Accounts:** sign-up gated by a team invite code, hashed passwords, session login/logout
- **Private history:** each lifter only sees and edits their own sessions
- **Team PR board:** everyone's best squat, bench, deadlift, and total, ranked by total
- **kg or lb per lifter:** weights are stored in kg; entry and display follow each lifter's choice
- Server-side input validation; total calculated automatically
- PR cards and a progression chart (Chart.js) with Total / per-lift / all-lifts views, PR points highlighted, and change since the first session
- CSRF protection on every form

## Stack

- **Backend:** Python, Flask (sessions, `werkzeug.security` password hashing)
- **Database:** SQLite (`sqlite3` standard library, parameterized queries, foreign keys)
- **Frontend:** Jinja templates, HTML/CSS, a little vanilla JavaScript, Chart.js
- **Deployment:** PythonAnywhere (WSGI); gunicorn `Procfile` for other hosts

## Configuration

Set these as environment variables:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs login sessions. Required in production; without it everyone is logged out on every restart. |
| `TEAM_INVITE_CODE` | Code new members must enter to sign up. If unset, sign-up is closed. |
| `COOKIE_SECURE` | Set to `1` when the site is served over HTTPS only. |
| `DATABASE_PATH` | Where the SQLite file lives (default: `goatlifts.db` next to `app.py`). |

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
TEAM_INVITE_CODE=dev SECRET_KEY=dev flask --app app run
```

Then open http://127.0.0.1:5000 and create an account with invite code `dev`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite (`tests/`) runs each test against a throwaway SQLite database. It covers sign-up rules, login/logout, CSRF rejection, safe redirects, logging and validation, PR math, privacy between lifters (history and deletes), the team board, and kg/lb conversion.

## Project layout

```
GoatLifts/
├── app.py              # config, auth, routes, validation, database access
├── templates/
│   ├── base.html       # top bar, unit toggle, flash messages
│   ├── index.html      # dashboard: log form, PRs, chart, history
│   ├── team.html       # team PR board
│   ├── login.html
│   └── register.html
├── static/
│   └── style.css
├── tests/              # pytest suite
├── requirements.txt
└── Procfile
```

## Deploy

### PythonAnywhere (current host)

The live site runs on PythonAnywhere's free tier, where the SQLite file sits on a persistent disk.

1. In a Bash console: `git clone` this repo, then create a virtualenv and `pip install -r requirements.txt`.
2. On the **Web** tab, add a web app with **Manual configuration** and point **Source code** and **Virtualenv** at the clone and the virtualenv. Turn on **Force HTTPS**.
3. Replace the WSGI file's contents with:
   ```python
   import os
   import sys

   os.environ["SECRET_KEY"] = "<long random string>"
   os.environ["TEAM_INVITE_CODE"] = "<code you share with the club>"
   os.environ["COOKIE_SECURE"] = "1"

   PATH = "/home/<username>/GoatLifts"
   if PATH not in sys.path:
       sys.path.insert(0, PATH)
   from app import app as application
   ```
   Keep the real values out of git. To change the invite code, edit this file and Reload.
4. Click **Reload**. To ship updates later: `git pull` in the console, then Reload.

Free web apps must be extended from the Web tab once a month or they are disabled.

### Render (alternative)

1. In Render, create a new **Web Service** from the repo and set the environment variables above.
2. Build command: `pip install -r requirements.txt`
3. Start command: `gunicorn app:app`

Note: on a free Render instance the filesystem is ephemeral, so the SQLite file resets when the service restarts or redeploys. Attach a persistent disk and point `DATABASE_PATH` at it, or move to Postgres.

## Possible next steps

- Password reset and an admin role for club officers
- Estimated 1RM calculations and per-set logging
- Rate limiting on login attempts
- Postgres for durable hosting

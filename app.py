import math
import os
import sqlite3
from contextlib import closing
from datetime import date, datetime

from flask import Flask, abort, redirect, render_template, request, url_for

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "goatlifts.db"))

MAX_KG = 600  # sanity ceiling so typos like 5000 get rejected


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create the entries table if it doesn't exist yet."""
    with closing(get_db()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE,
                logged_on TEXT NOT NULL,
                squat REAL NOT NULL,
                bench REAL NOT NULL,
                deadlift REAL NOT NULL,
                total REAL NOT NULL
            )
            """
        )


init_db()


@app.template_filter("kg")
def format_kg(value):
    """142.0 -> '142', 142.5 -> '142.5'"""
    return f"{value:g}"


def parse_entry(form):
    """Validate the submitted form. Returns (clean_values, errors)."""
    errors = []

    name = " ".join(form.get("name", "").split())
    if not name:
        errors.append("Name is required.")
    elif len(name) > 60:
        errors.append("Name must be 60 characters or fewer.")

    lifts = {}
    for key, label in (("squat", "Squat"), ("bench", "Bench"), ("deadlift", "Deadlift")):
        raw = form.get(key, "").strip()
        try:
            value = float(raw)
        except ValueError:
            errors.append(f"{label} must be a number.")
            continue
        if not math.isfinite(value) or not 0 < value <= MAX_KG:
            errors.append(f"{label} must be between 0 and {MAX_KG} kg.")
            continue
        lifts[key] = value

    raw_date = form.get("date", "").strip() or date.today().isoformat()
    try:
        logged_on = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        errors.append("Date must look like YYYY-MM-DD.")
        logged_on = None

    clean = {"name": name, "logged_on": logged_on, **lifts}
    if len(lifts) == 3:
        clean["total"] = lifts["squat"] + lifts["bench"] + lifts["deadlift"]
    return clean, errors


def build_context(selected=None, errors=None, form=None):
    """Everything the homepage needs: lifters, PRs, history, chart data."""
    with closing(get_db()) as conn:
        lifters = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM entries GROUP BY name ORDER BY MAX(id) DESC"
            )
        ]

        if selected:
            history = conn.execute(
                "SELECT * FROM entries WHERE name = ? ORDER BY logged_on DESC, id DESC",
                (selected,),
            ).fetchall()
        else:
            history = []

        # Unknown or missing lifter in the URL -> fall back to the most recent one
        if not history and lifters:
            selected = lifters[0]
            history = conn.execute(
                "SELECT * FROM entries WHERE name = ? ORDER BY logged_on DESC, id DESC",
                (selected,),
            ).fetchall()

        # Still nothing (e.g. a rejected first entry) -> no lifter section to show
        if not history:
            selected = None

    prs = None
    chart = None
    if history:
        prs = {
            "squat": max(r["squat"] for r in history),
            "bench": max(r["bench"] for r in history),
            "deadlift": max(r["deadlift"] for r in history),
            "total": max(r["total"] for r in history),
        }
        oldest_first = list(reversed(history))
        chart = {
            "labels": [r["logged_on"] for r in oldest_first],
            "squat": [r["squat"] for r in oldest_first],
            "bench": [r["bench"] for r in oldest_first],
            "deadlift": [r["deadlift"] for r in oldest_first],
            "total": [r["total"] for r in oldest_first],
        }

    return {
        "lifters": lifters,
        "selected": selected,
        "history": history,
        "prs": prs,
        "chart": chart,
        "errors": errors or [],
        "form": form or {},
        "today": date.today().isoformat(),
    }


@app.route("/")
def home():
    return render_template("index.html", **build_context(request.args.get("lifter")))


@app.route("/log", methods=["POST"])
def log_lift():
    clean, errors = parse_entry(request.form)
    if errors:
        context = build_context(clean.get("name") or None, errors, request.form)
        return render_template("index.html", **context), 400

    with closing(get_db()) as conn, conn:
        conn.execute(
            """
            INSERT INTO entries (name, logged_on, squat, bench, deadlift, total)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                clean["name"],
                clean["logged_on"],
                clean["squat"],
                clean["bench"],
                clean["deadlift"],
                clean["total"],
            ),
        )
    return redirect(url_for("home", lifter=clean["name"]))


@app.route("/delete/<int:entry_id>", methods=["POST"])
def delete_entry(entry_id):
    with closing(get_db()) as conn, conn:
        row = conn.execute("SELECT name FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            abort(404)
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    return redirect(url_for("home", lifter=row["name"]))


if __name__ == "__main__":
    app.run(debug=True)

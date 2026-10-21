import hmac
import math
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import date, datetime
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "goatlifts.db"))

# Without a fixed SECRET_KEY, sessions are signed with a random key and everyone
# gets logged out whenever the server restarts. Set it in production.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
# Sign-up is closed unless a team invite code is configured.
app.config["INVITE_CODE"] = os.environ.get("TEAM_INVITE_CODE")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("COOKIE_SECURE") == "1"

MAX_KG = 600  # sanity ceiling so typos like 5000 get rejected
LB_PER_KG = 2.20462
UNITS = ("kg", "lb")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create the tables if they don't exist yet."""
    with closing(get_db()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                unit TEXT NOT NULL DEFAULT 'kg' CHECK (unit IN ('kg', 'lb')),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS lifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                logged_on TEXT NOT NULL,
                squat REAL NOT NULL,
                bench REAL NOT NULL,
                deadlift REAL NOT NULL,
                total REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS lifts_by_user ON lifts (user_id, logged_on);
            """
        )


init_db()


# ---------- units ----------

def to_kg(value, unit):
    return value / LB_PER_KG if unit == "lb" else value


def from_kg(value, unit):
    """Convert a stored kg value for display, rounded to one decimal."""
    return round(value * LB_PER_KG if unit == "lb" else value, 1)


@app.template_filter("weight")
def format_weight(value_kg, unit="kg"):
    """142.0 -> '142', 142.5 -> '142.5', converted to the viewer's unit."""
    return f"{from_kg(value_kg, unit):g}"


# ---------- auth + CSRF ----------

@app.before_request
def load_user_and_check_csrf():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        with closing(get_db()) as conn:
            g.user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:
            session.clear()

    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        if not hmac.compare_digest(sent, session.get("csrf_token", "")):
            abort(400, "Your form expired. Go back, refresh, and try again.")


@app.context_processor
def inject_globals():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    unit = g.user["unit"] if g.get("user") else "kg"
    return {"csrf_token": session["csrf_token"], "user": g.get("user"), "unit": unit}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def start_session(user_id):
    """Log a user in with a fresh session (prevents session fixation)."""
    session.clear()
    session["user_id"] = user_id
    session["csrf_token"] = secrets.token_urlsafe(32)


def parse_registration(form, invite_code):
    """Validate the sign-up form. Returns (clean_values, errors)."""
    errors = []

    username = form.get("username", "").strip().lower()
    if not 3 <= len(username) <= 30 or not all(c.isalnum() or c in "._-" for c in username):
        errors.append("Username must be 3-30 characters: letters, numbers, dots, dashes, or underscores.")

    display_name = " ".join(form.get("display_name", "").split())
    if not display_name:
        errors.append("Name is required.")
    elif len(display_name) > 60:
        errors.append("Name must be 60 characters or fewer.")

    password = form.get("password", "")
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    elif password != form.get("confirm", ""):
        errors.append("Passwords don't match.")

    if not invite_code:
        errors.append("Sign-up is closed right now.")
    elif not hmac.compare_digest(form.get("invite_code", "").strip(), invite_code):
        errors.append("That invite code isn't right. Ask a club officer for the current one.")

    return {"username": username, "display_name": display_name, "password": password}, errors


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("home"))
    if request.method == "GET":
        return render_template("register.html", errors=[], form={})

    clean, errors = parse_registration(request.form, app.config["INVITE_CODE"])
    if not errors:
        try:
            with closing(get_db()) as conn, conn:
                cursor = conn.execute(
                    "INSERT INTO users (username, display_name, password_hash) VALUES (?, ?, ?)",
                    (clean["username"], clean["display_name"], generate_password_hash(clean["password"])),
                )
                user_id = cursor.lastrowid
        except sqlite3.IntegrityError:
            errors.append("That username is taken.")
    if errors:
        return render_template("register.html", errors=errors, form=request.form), 400

    start_session(user_id)
    return redirect(url_for("home"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("home"))
    if request.method == "GET":
        return render_template("login.html", error=None, form={})

    username = request.form.get("username", "").strip().lower()
    with closing(get_db()) as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not check_password_hash(row["password_hash"], request.form.get("password", "")):
        return render_template("login.html", error="Wrong username or password.", form=request.form), 401

    start_session(row["id"])
    next_url = request.args.get("next", "")
    # Only follow local paths, never another site.
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("home")
    return redirect(next_url)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- lifts ----------

def parse_entry(form, unit="kg"):
    """Validate the submitted lift form (weights in `unit`). Returns (clean_values_in_kg, errors)."""
    errors = []
    max_in_unit = from_kg(MAX_KG, unit)

    lifts = {}
    for key, label in (("squat", "Squat"), ("bench", "Bench"), ("deadlift", "Deadlift")):
        raw = form.get(key, "").strip()
        try:
            value = float(raw)
        except ValueError:
            errors.append(f"{label} must be a number.")
            continue
        if not math.isfinite(value) or not 0 < value <= max_in_unit:
            errors.append(f"{label} must be between 0 and {max_in_unit:g} {unit}.")
            continue
        lifts[key] = to_kg(value, unit)

    raw_date = form.get("date", "").strip() or date.today().isoformat()
    try:
        logged_on = datetime.strptime(raw_date, "%Y-%m-%d").date().isoformat()
    except ValueError:
        errors.append("Date must look like YYYY-MM-DD.")
        logged_on = None

    clean = {"logged_on": logged_on, **lifts}
    if len(lifts) == 3:
        clean["total"] = lifts["squat"] + lifts["bench"] + lifts["deadlift"]
    return clean, errors


def build_context(user, errors=None, form=None):
    """Everything the dashboard needs: PRs, history, chart data (all for one user)."""
    with closing(get_db()) as conn:
        history = conn.execute(
            "SELECT * FROM lifts WHERE user_id = ? ORDER BY logged_on DESC, id DESC",
            (user["id"],),
        ).fetchall()

    unit = user["unit"]
    prs = None
    chart = None
    if history:
        prs = {lift: max(r[lift] for r in history) for lift in ("squat", "bench", "deadlift", "total")}
        oldest_first = list(reversed(history))
        chart = {
            "unit": unit,
            "dates": [r["logged_on"] for r in oldest_first],
            **{lift: [from_kg(r[lift], unit) for r in oldest_first]
               for lift in ("squat", "bench", "deadlift", "total")},
        }

    return {
        "history": history,
        "prs": prs,
        "chart": chart,
        "errors": errors or [],
        "form": form or {},
        "today": date.today().isoformat(),
    }


@app.route("/")
@login_required
def home():
    return render_template("index.html", **build_context(g.user))


@app.route("/log", methods=["POST"])
@login_required
def log_lift():
    clean, errors = parse_entry(request.form, g.user["unit"])
    if errors:
        return render_template("index.html", **build_context(g.user, errors, request.form)), 400

    with closing(get_db()) as conn, conn:
        conn.execute(
            """
            INSERT INTO lifts (user_id, logged_on, squat, bench, deadlift, total)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (g.user["id"], clean["logged_on"], clean["squat"], clean["bench"],
             clean["deadlift"], clean["total"]),
        )
    flash("Session logged.")
    return redirect(url_for("home"))


@app.route("/delete/<int:lift_id>", methods=["POST"])
@login_required
def delete_lift(lift_id):
    with closing(get_db()) as conn, conn:
        # Scoping by user_id means someone else's entry looks exactly like a missing one.
        deleted = conn.execute(
            "DELETE FROM lifts WHERE id = ? AND user_id = ?", (lift_id, g.user["id"])
        ).rowcount
    if not deleted:
        abort(404)
    return redirect(url_for("home"))


@app.route("/settings/unit", methods=["POST"])
@login_required
def set_unit():
    unit = request.form.get("unit")
    if unit not in UNITS:
        abort(400)
    with closing(get_db()) as conn, conn:
        conn.execute("UPDATE users SET unit = ? WHERE id = ?", (unit, g.user["id"]))
    next_url = request.form.get("next", "")
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = url_for("home")
    return redirect(next_url)


@app.route("/team")
@login_required
def team():
    """Team PR board: each lifter's best of each lift. Histories stay private."""
    with closing(get_db()) as conn:
        board = conn.execute(
            """
            SELECT u.id, u.display_name,
                   MAX(l.squat) AS squat, MAX(l.bench) AS bench,
                   MAX(l.deadlift) AS deadlift, MAX(l.total) AS total,
                   COUNT(l.id) AS sessions, MAX(l.logged_on) AS last_logged
            FROM users u
            JOIN lifts l ON l.user_id = u.id
            GROUP BY u.id
            ORDER BY total DESC, u.display_name
            """
        ).fetchall()
    return render_template("team.html", board=board)


if __name__ == "__main__":
    app.run(debug=True)

from datetime import date

from werkzeug.datastructures import MultiDict

from app import parse_entry
from conftest import csrf, query


# ---------- accounts ----------

def test_dashboard_requires_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_register_logs_you_in_and_hashes_the_password(client, register):
    response = register()

    assert response.status_code == 302
    assert b"Vance Penny" in client.get("/").data
    [user] = query("SELECT * FROM users")
    assert user["username"] == "vance"
    assert "squat-bench-dead" not in user["password_hash"]


def test_register_needs_the_team_invite_code(client, register):
    response = register(invite_code="wrong")
    assert response.status_code == 400
    assert b"invite code isn" in response.data
    assert query("SELECT * FROM users") == []


def test_signup_is_closed_without_an_invite_code(client, register):
    client.application.config["INVITE_CODE"] = None
    response = register(invite_code="")
    assert b"Sign-up is closed" in response.data


def test_register_validates_input(client, register):
    response = register(username="a!", display_name="", password="short")
    page = response.get_data(as_text=True)
    assert response.status_code == 400
    assert "Username must be 3-30 characters" in page
    assert "Name is required." in page
    assert "Password must be at least 8 characters." in page


def test_password_confirmation_must_match(client, register):
    response = register(confirm="something-else")
    assert b"Passwords don" in response.data


def test_usernames_are_unique_ignoring_case(client, register, post):
    register(username="vance")
    post("/logout")
    response = register(username="VANCE")
    assert response.status_code == 400
    assert b"That username is taken." in response.data


def test_login_and_logout(client, register, post):
    register()
    post("/logout")
    assert client.get("/").status_code == 302

    bad = post("/login", username="vance", password="wrong-password")
    assert bad.status_code == 401
    assert b"Wrong username or password." in bad.data

    good = post("/login", username="Vance", password="squat-bench-dead")
    assert good.status_code == 302
    assert client.get("/").status_code == 200


def test_login_only_redirects_to_local_paths(client, register, post):
    register()
    post("/logout")
    response = client.post("/login?next=https://evil.example",
                           data={"username": "vance", "password": "squat-bench-dead",
                                 "csrf_token": csrf(client)})
    assert response.headers["Location"] == "/"


def test_posts_without_a_csrf_token_are_rejected(client, register, post):
    register()
    response = client.post("/log", data={"squat": "100", "bench": "80", "deadlift": "120"})
    assert response.status_code == 400
    assert query("SELECT * FROM lifts") == []


# ---------- logging lifts ----------

def test_log_saves_entry_for_the_logged_in_user(client, register, log):
    register()
    response = log(squat="150", bench="102.5", deadlift="190")

    assert response.status_code == 302
    [row] = query("SELECT * FROM lifts")
    [user] = query("SELECT id FROM users")
    assert row["user_id"] == user["id"]
    assert row["logged_on"] == "2026-10-01"
    assert row["total"] == 442.5


def test_invalid_input_is_rejected_and_nothing_is_saved(client, register, log):
    register()
    response = log(squat="abc", bench="5000", deadlift="-1", date="10/01/2026")

    assert response.status_code == 400
    page = response.get_data(as_text=True)
    assert "Squat must be a number." in page
    assert "Bench must be between 0 and 600 kg." in page
    assert "Deadlift must be between 0 and 600 kg." in page
    assert "Date must look like YYYY-MM-DD." in page
    assert query("SELECT * FROM lifts") == []


def test_rejected_first_entry_does_not_crash(client, register, log):
    register()
    response = log(bench="5000")
    assert response.status_code == 400
    assert b'value="150"' in response.data   # keeps what the user typed


def test_non_finite_numbers_are_rejected():
    form = MultiDict({"squat": "nan", "bench": "inf", "deadlift": "100"})
    _, errors = parse_entry(form)
    assert "Squat must be between 0 and 600 kg." in errors
    assert "Bench must be between 0 and 600 kg." in errors


def test_blank_date_defaults_to_today():
    form = MultiDict({"date": "", "squat": "100", "bench": "80", "deadlift": "120"})
    clean, errors = parse_entry(form)
    assert errors == []
    assert clean["logged_on"] == date.today().isoformat()


def test_prs_are_the_best_of_each_lift_across_sessions(client, register, log):
    register()
    log(date="2026-09-01", squat="160", bench="95", deadlift="180")
    log(date="2026-10-01", squat="150", bench="100", deadlift="200")

    page = client.get("/").get_data(as_text=True)

    assert '<span class="pr-value">160<small>kg</small></span>' in page
    assert '<span class="pr-value">100<small>kg</small></span>' in page
    assert '<span class="pr-value">200<small>kg</small></span>' in page
    assert '<span class="pr-value">450<small>kg</small></span>' in page
    assert "progress-chart" in page


def test_chart_needs_at_least_two_sessions(client, register, log):
    register()
    log()
    page = client.get("/").get_data(as_text=True)
    assert "progress-chart" not in page
    assert "Log at least two sessions" in page


# ---------- privacy between lifters ----------

def test_lifters_only_see_their_own_history(client, register, log, post):
    register(username="one", display_name="Lifter One")
    log(squat="111")
    post("/logout")
    register(username="two", display_name="Lifter Two")
    log(squat="222")

    page = client.get("/").get_data(as_text=True)
    assert ">222<" in page
    assert ">111<" not in page


def test_cannot_delete_someone_elses_entry(client, register, log, post):
    register(username="one")
    log()
    [row] = query("SELECT id FROM lifts")
    post("/logout")
    register(username="two")

    assert post(f"/delete/{row['id']}").status_code == 404
    assert len(query("SELECT * FROM lifts")) == 1


def test_delete_removes_your_own_entry(client, register, log, post):
    register()
    log()
    [row] = query("SELECT id FROM lifts")

    assert post(f"/delete/{row['id']}").status_code == 302
    assert query("SELECT * FROM lifts") == []


def test_team_board_ranks_by_total_and_shows_only_prs(client, register, log, post):
    register(username="one", display_name="Lifter One")
    log(date="2026-09-01", squat="100", bench="60", deadlift="140")
    post("/logout")
    register(username="two", display_name="Lifter Two")
    log(squat="200", bench="120", deadlift="250")

    page = client.get("/team").get_data(as_text=True)

    assert page.index("Lifter Two") < page.index("Lifter One")
    assert ">570<" in page and ">300<" in page
    assert "2026-09-01" not in page   # no session dates leak onto the board


# ---------- units ----------

def test_pound_users_enter_and_see_pounds_but_kg_is_stored(client, register, log, post):
    register()
    post("/settings/unit", unit="lb", next="/")
    log(squat="315", bench="225", deadlift="405")

    [row] = query("SELECT * FROM lifts")
    assert round(row["squat"], 1) == 142.9

    page = client.get("/").get_data(as_text=True)
    assert '<span class="pr-value">315<small>lb</small></span>' in page
    assert '<span class="pr-value">945<small>lb</small></span>' in page


def test_unit_must_be_kg_or_lb(client, register, post):
    register()
    assert post("/settings/unit", unit="stone").status_code == 400


def test_pages_embed_the_csrf_token_in_forms(client):
    page = client.get("/login").get_data(as_text=True)
    assert f'name="csrf_token" value="{csrf(client)}"' in page

from datetime import date

from werkzeug.datastructures import MultiDict

from app import parse_entry
from conftest import rows


def test_home_with_no_data(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"No sessions logged yet" in response.data


def test_log_saves_entry_and_calculates_total(client, log):
    response = log(squat="150", bench="102.5", deadlift="190")

    assert response.status_code == 302
    assert "lifter=Vance+Penny" in response.headers["Location"]
    [row] = rows()
    assert row["name"] == "Vance Penny"
    assert row["logged_on"] == "2026-10-01"
    assert row["total"] == 442.5


def test_invalid_input_is_rejected_and_nothing_is_saved(client, log):
    response = log(name="", squat="abc", bench="5000", deadlift="-1", date="10/01/2026")

    assert response.status_code == 400
    page = response.get_data(as_text=True)
    assert "Name is required." in page
    assert "Squat must be a number." in page
    assert "Bench must be between 0 and 600 kg." in page
    assert "Deadlift must be between 0 and 600 kg." in page
    assert "Date must look like YYYY-MM-DD." in page
    assert rows() == []


def test_rejected_form_keeps_what_the_user_typed(client, log):
    response = log(name="Vance Penny", bench="5000")
    assert b'value="Vance Penny"' in response.data


def test_non_finite_numbers_are_rejected():
    form = MultiDict({"name": "A", "squat": "nan", "bench": "inf", "deadlift": "100"})
    _, errors = parse_entry(form)
    assert "Squat must be between 0 and 600 kg." in errors
    assert "Bench must be between 0 and 600 kg." in errors


def test_blank_date_defaults_to_today_and_name_whitespace_is_collapsed():
    form = MultiDict({"name": "  Vance   Penny ", "date": "",
                      "squat": "100", "bench": "80", "deadlift": "120"})
    clean, errors = parse_entry(form)
    assert errors == []
    assert clean["name"] == "Vance Penny"
    assert clean["logged_on"] == date.today().isoformat()


def test_prs_are_the_best_of_each_lift_across_sessions(client, log):
    log(date="2026-09-01", squat="160", bench="95", deadlift="180")
    log(date="2026-10-01", squat="150", bench="100", deadlift="200")

    page = client.get("/?lifter=Vance Penny").get_data(as_text=True)

    assert '<span class="pr-value">160</span>' in page   # squat from session 1
    assert '<span class="pr-value">100</span>' in page   # bench from session 2
    assert '<span class="pr-value">200</span>' in page   # deadlift from session 2
    assert '<span class="pr-value">450</span>' in page   # best total (150+100+200)
    assert "progress-chart" in page


def test_chart_needs_at_least_two_sessions(client, log):
    log()
    page = client.get("/?lifter=Vance Penny").get_data(as_text=True)
    assert "progress-chart" not in page
    assert "Log at least two sessions" in page


def test_lifter_lookup_ignores_case(client, log):
    log(name="Vance Penny")
    page = client.get("/?lifter=vance penny").get_data(as_text=True)
    assert "Squat PR" in page


def test_lifters_are_kept_separate(client, log):
    log(name="Lifter One", squat="100")
    log(name="Lifter Two", squat="250")
    page = client.get("/?lifter=Lifter One").get_data(as_text=True)
    assert '<span class="pr-value">100</span>' in page
    assert '<span class="pr-value">250</span>' not in page


def test_delete_removes_entry(client, log):
    log()
    [row] = rows()

    response = client.post(f"/delete/{row['id']}")

    assert response.status_code == 302
    assert rows() == []


def test_delete_missing_entry_returns_404(client):
    assert client.post("/delete/999").status_code == 404

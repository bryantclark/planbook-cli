import json

import pytest
import responses

from planbook.client import API_BASE


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    home.mkdir()
    xdg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("PLANBOOK_TOKEN", raising=False)
    return xdg


@pytest.fixture
def session_file(isolated_config):
    session_dir = isolated_config / "planbook"
    session_dir.mkdir(parents=True)
    path = session_dir / "token.json"
    # A syntactically valid JWT so token decoding has something to chew on.
    path.write_text('{"token": "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ7fSJ9.sig"}')
    return path


DATE = "09/03/2026"


def parse_stdout(capsys):
    captured = capsys.readouterr()
    return json.loads(captured.out), captured


def stub(endpoint, body):
    """Register one POST response for a Planbook endpoint."""
    responses.post(f"{API_BASE}{endpoint}", json=body)


def class_wire_record(teach_days=("m", "t", "w", "r", "f")):
    """A class as /getClasses2 returns it. Teach flags are "Y"/"N" strings."""
    raw = {"cId": 123, "cN": "Biology", "cSd": "08/31/2026", "cEd": "06/06/2027"}
    for prefix in ["m", "t", "w", "r", "f", "s", "u"]:
        raw[f"{prefix}T"] = "Y" if prefix in teach_days else "N"
        raw[f"{prefix}St"] = f"{prefix}-start"
        raw[f"{prefix}Et"] = f"{prefix}-end"
    return raw


def schedule_row(teach=(), start_times=None, end_times=None, yn=False, **overrides):
    """One classSchedule row as /getClass returns it: 20 Sunday-indexed slots."""
    row = {"scheduleStart": "08/31/2026", "additionalClassDays": [], "scheduleId": 9}
    for n in range(1, 21):
        taught = n in teach
        row[f"day{n}Teach"] = ("Y" if taught else "N") if yn else taught
        row[f"day{n}StartTime"] = (start_times or {}).get(n, "")
        row[f"day{n}EndTime"] = (end_times or {}).get(n, "")
    row.update(overrides)
    return row


def class_record(rows=(), **overrides):
    """A /getClass record, whose classSchedule rows carry the real schedule."""
    record = {
        "className": "Bio",
        "classStartDate": "08/31/2026",
        "classSchedule": list(rows),
    }
    record.update(overrides)
    return record


def lesson_record(**overrides):
    """One lesson as /getLessonsEvents returns it inside a day's objects."""
    record = {"classId": 1, "lessonId": 5}
    record.update(overrides)
    return record


def lesson_day(date=DATE, *lessons, **overrides):
    """One day of a /getLessonsEvents week."""
    day = {"date": date, "objects": list(lessons)}
    day.update(overrides)
    return day


def lesson_days(*days):
    """The /getLessonsEvents envelope."""
    return {"days": list(days)}


def saved_lesson(date=DATE, **overrides):
    """The common case: one day holding one lesson."""
    return lesson_days(lesson_day(date, lesson_record(**overrides)))


def student_record(**overrides):
    record = {"studentId": 7, "firstName": "Ada", "lastName": "L"}
    record.update(overrides)
    return record


def roster(*students):
    return {"students": list(students)}


def unit_record(**overrides):
    record = {"unitId": 5, "subjectId": 1, "unitTitle": "U"}
    record.update(overrides)
    return record


def unit_list(*units):
    return {"units": list(units)}


def todo_record(**overrides):
    record = {"toDoId": 7, "toDoText": "Old"}
    record.update(overrides)
    return record


def todo_list(*todos):
    return {"toDos": list(todos)}


def event_record(**overrides):
    record = {"eventId": 3, "eventTitle": "Assembly", "eventDate": "09/01/2026"}
    record.update(overrides)
    return record


def event_list(*events):
    return {"events": list(events)}

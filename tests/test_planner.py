"""Planner unit tests. Run: uv run --with pytest python -m pytest tests/test_planner.py -q"""
import os
import sys
import tempfile
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest  # noqa: E402
from open_llm_vtuber.planner import PlannerStore, parse_when, plan_day  # noqa: E402

NOW = datetime(2026, 9, 24, 10, 7)


@pytest.fixture
def store():
    d = tempfile.mkdtemp()
    return PlannerStore(os.path.join(d, "p.db"))


@pytest.mark.parametrize("text,expected", [
    ("15:00", datetime(2026, 9, 24, 15, 0)),
    ("3pm", datetime(2026, 9, 24, 15, 0)),
    ("9am", datetime(2026, 9, 25, 9, 0)),            # already past -> tomorrow
    ("12am", datetime(2026, 9, 25, 0, 0)),
    ("tomorrow 09:30", datetime(2026, 9, 25, 9, 30)),
    ("tonight", datetime(2026, 9, 24, 20, 0)),
    ("2026-09-30 18:45", datetime(2026, 9, 30, 18, 45)),
    ("2026-09-30T18:45", datetime(2026, 9, 30, 18, 45)),
    ("in 45 minutes", NOW + timedelta(minutes=45)),
    ("in 2 hours", NOW + timedelta(hours=2)),
])
def test_parse_when(text, expected):
    assert parse_when(text, NOW) == expected


def test_parse_when_empty_and_bad():
    assert parse_when("", NOW) is None
    assert parse_when(None, NOW) is None
    with pytest.raises(ValueError):
        parse_when("whenever", NOW)
    with pytest.raises(ValueError):
        parse_when("25:00", NOW)


def test_edf_order_and_late_flag(store):
    a = store.add("Undated low", None, 30, "low", now=NOW)
    b = store.add("Invoice", parse_when("11:00", NOW), 60, "high", now=NOW)
    c = store.add("Call supplier", parse_when("10:30", NOW), 15, now=NOW)
    d = store.add("Undated high", None, 20, "high", now=NOW)
    plan = plan_day(store.for_day(now=NOW), NOW)
    order = [bl.task.id for bl in plan.blocks]
    assert order == [c.id, b.id, d.id, a.id]           # deadlines first, then priority
    assert plan.blocks[0].start == datetime(2026, 9, 24, 10, 10)  # rounded up to 5 min
    # call 10:10-10:25, buffer, invoice 10:30-11:30 -> 30 min late
    assert plan.blocks[1].late_by_min == 30
    assert any("miss its 11:00 deadline" in s for s in plan.suggestions())


def test_delegated_not_scheduled(store):
    t = store.add("Research competitors", None, 90, delegate_to="Vivian", now=NOW)
    store.update(t.id, status="delegated")
    store.add("Lunch", parse_when("12:30", NOW), 30, now=NOW)
    plan = plan_day(store.for_day(now=NOW), NOW)
    assert [b.task.title for b in plan.blocks] == ["Lunch"]
    assert [x.title for x in plan.delegated] == ["Research competitors"]


def test_complete_cancel_and_carry_over(store):
    y = NOW - timedelta(days=1)
    old = store.add("Yesterday leftover", None, 20, now=y)
    done = store.add("Done thing", None, 10, now=NOW)
    gone = store.add("Dropped", None, 10, now=NOW)
    store.complete(done.id, now=NOW)
    store.update(gone.id, status="cancelled")
    titles = [t.title for t in store.for_day(now=NOW)]
    assert "Yesterday leftover" in titles and "Done thing" in titles and "Dropped" not in titles
    open_titles = [t.title for t in store.for_day(include_closed=False, now=NOW)]
    assert open_titles == ["Yesterday leftover"]
    assert store.get(old.id).status == "open"


def test_overflow_suggests_moving(store):
    for i in range(6):
        store.add(f"Big job {i}", None, 90, now=NOW)
    late_now = NOW.replace(hour=18)
    plan = plan_day(store.for_day(now=NOW), late_now)
    assert plan.overflow
    assert any(s.startswith("Move to tomorrow") for s in plan.suggestions())


def test_update_due_resets_reminder(store):
    t = store.add("Pay rent", parse_when("17:00", NOW), now=NOW)
    store.update(t.id, reminded=2)
    t2 = store.update(t.id, due=parse_when("18:00", NOW))
    assert t2.reminded == 0 and t2.due == "2026-09-24T18:00"

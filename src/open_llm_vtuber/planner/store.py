"""SQLite task store. One file, safe for two processes (MCP server + web server) via WAL."""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, date, time
from typing import Optional, List

PRIORITIES = {"high": 1, "normal": 2, "low": 3}
PRIORITY_NAMES = {v: k for k, v in PRIORITIES.items()}
STATUSES = ("open", "done", "delegated", "cancelled")

DEFAULT_DB = os.environ.get(
    "PLANNER_DB",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "planner.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    title         TEXT    NOT NULL,
    notes         TEXT    NOT NULL DEFAULT '',
    day           TEXT    NOT NULL,              -- YYYY-MM-DD the task belongs to
    due           TEXT,                          -- ISO datetime or NULL
    estimate_min  INTEGER NOT NULL DEFAULT 30,
    priority      INTEGER NOT NULL DEFAULT 2,    -- 1 high, 2 normal, 3 low
    status        TEXT    NOT NULL DEFAULT 'open',
    delegate_to   TEXT    NOT NULL DEFAULT '',
    planned_start TEXT,
    planned_end   TEXT,
    reminded      INTEGER NOT NULL DEFAULT 0,    -- 0 none, 1 "due soon", 2 "overdue"
    created_at    TEXT    NOT NULL,
    done_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_tasks_day ON tasks(day, status);
"""


@dataclass
class Task:
    id: int
    title: str
    notes: str
    day: str
    due: Optional[str]
    estimate_min: int
    priority: int
    status: str
    delegate_to: str
    planned_start: Optional[str]
    planned_end: Optional[str]
    reminded: int
    created_at: str
    done_at: Optional[str]

    @property
    def due_dt(self) -> Optional[datetime]:
        return datetime.fromisoformat(self.due) if self.due else None

    @property
    def priority_name(self) -> str:
        return PRIORITY_NAMES.get(self.priority, "normal")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["priority_name"] = self.priority_name
        return d

    def short(self) -> str:
        bits = [f"#{self.id} {self.title}"]
        if self.due:
            bits.append(f"due {self.due_dt.strftime('%a %H:%M')}")
        bits.append(f"~{self.estimate_min}min")
        if self.priority != 2:
            bits.append(self.priority_name)
        if self.delegate_to:
            bits.append(f"-> {self.delegate_to}")
        if self.status != "open":
            bits.append(f"[{self.status}]")
        return ", ".join(bits)


_REL = re.compile(r"^in\s+(\d+(?:\.\d+)?)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours)$")
_HM = re.compile(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$")


def parse_when(text: Optional[str], now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse a due time. Accepts 'YYYY-MM-DD HH:MM', ISO, 'HH:MM', '3pm', 'tomorrow 09:30',
    'tonight', 'in 45 minutes', 'in 2 hours'. Bare times already past roll to tomorrow.
    Empty -> None."""
    if text is None or not str(text).strip():
        return None
    now = now or datetime.now()
    s = str(text).strip().lower()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return datetime.fromisoformat(s.replace("t", " "))
    m = _REL.match(s)
    if m:
        n, unit = float(m.group(1)), m.group(2)
        return now + (timedelta(hours=n) if unit.startswith("h") else timedelta(minutes=n))
    base, word = now.date(), None
    for w, offset, default in (("today", 0, "17:00"), ("tonight", 0, "20:00"), ("tomorrow", 1, "17:00")):
        if s.startswith(w):
            base, word = base + timedelta(days=offset), w
            s = s[len(w):].strip() or default
            break
    m = _HM.match(s)
    if not m:
        raise ValueError(f"Can't understand time '{text}'. Use 'YYYY-MM-DD HH:MM' or 'HH:MM'.")
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        raise ValueError(f"Invalid time '{text}'.")
    dt = datetime.combine(base, time(h, mi))
    if word is None and dt < now - timedelta(minutes=1):
        dt += timedelta(days=1)
    return dt


class PlannerStore:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        return c

    @staticmethod
    def _row(r: sqlite3.Row) -> Task:
        return Task(**dict(r))

    # ---------- writes ----------
    def add(self, title: str, due: Optional[datetime] = None, estimate_min: int = 30,
            priority: str = "normal", notes: str = "", delegate_to: str = "",
            now: Optional[datetime] = None) -> Task:
        now = now or datetime.now()
        title = (title or "").strip()
        if not title:
            raise ValueError("Task title is empty.")
        day = (due or now).date().isoformat()
        c = self._conn()
        try:
            with c:
                cur = c.execute(
                    "INSERT INTO tasks (title, notes, day, due, estimate_min, priority, delegate_to, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (title, notes or "", day, due.isoformat(timespec="minutes") if due else None,
                     max(5, int(estimate_min or 30)), PRIORITIES.get(priority, 2), delegate_to or "",
                     now.isoformat(timespec="seconds")),
                )
            return self.get(cur.lastrowid, c)
        finally:
            c.close()

    def update(self, task_id: int, **fields) -> Task:
        allowed = {"title", "notes", "due", "estimate_min", "priority", "status", "delegate_to",
                   "planned_start", "planned_end", "reminded", "day", "done_at"}
        sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "status" in sets and sets["status"] not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        if "due" in sets and isinstance(sets["due"], datetime):
            sets["day"] = sets["due"].date().isoformat()
            sets["due"] = sets["due"].isoformat(timespec="minutes")
            sets["reminded"] = 0
        if "priority" in sets and isinstance(sets["priority"], str):
            sets["priority"] = PRIORITIES.get(sets["priority"], 2)
        if not sets:
            return self.get(task_id)
        c = self._conn()
        try:
            with c:
                q = ", ".join(f"{k} = ?" for k in sets)
                n = c.execute(f"UPDATE tasks SET {q} WHERE id = ?", (*sets.values(), task_id)).rowcount
            if not n:
                raise KeyError(f"No task #{task_id}")
            return self.get(task_id, c)
        finally:
            c.close()

    def complete(self, task_id: int, now: Optional[datetime] = None) -> Task:
        now = now or datetime.now()
        return self.update(task_id, status="done", done_at=now.isoformat(timespec="seconds"))

    def reopen(self, task_id: int) -> Task:
        c = self._conn()
        try:
            with c:
                c.execute("UPDATE tasks SET status='open', done_at=NULL WHERE id=?", (task_id,))
            return self.get(task_id, c)
        finally:
            c.close()

    # ---------- reads ----------
    def get(self, task_id: int, c: Optional[sqlite3.Connection] = None) -> Task:
        own = c is None
        c = c or self._conn()
        try:
            r = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not r:
                raise KeyError(f"No task #{task_id}")
            return self._row(r)
        finally:
            if own:
                c.close()

    def for_day(self, day: Optional[date] = None, include_closed: bool = True,
                now: Optional[datetime] = None) -> List[Task]:
        """Tasks for a day, plus anything still open from earlier days (carried over)."""
        now = now or datetime.now()
        d = (day or now.date()).isoformat()
        c = self._conn()
        try:
            rows = c.execute(
                "SELECT * FROM tasks WHERE (day = ? OR (day < ? AND status = 'open')) "
                "AND status != 'cancelled' "
                "ORDER BY status != 'open', COALESCE(planned_start, due, '9999'), priority, id",
                (d, d),
            ).fetchall()
        finally:
            c.close()
        tasks = [self._row(r) for r in rows]
        return tasks if include_closed else [t for t in tasks if t.status == "open"]

"""HTTP API for the client's Today panel and due-time reminders (localhost only, like the rest)."""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .store import PlannerStore, parse_when
from .scheduler import plan_day

REMIND_BEFORE_MIN = 10


class NewTask(BaseModel):
    title: str
    due_time: Optional[str] = ""
    estimate_minutes: int = 30
    priority: str = "normal"
    notes: str = ""


def init_planner_routes() -> APIRouter:
    router = APIRouter(prefix="/planner")
    store = PlannerStore()

    def _get(task_id: int):
        try:
            return store.get(task_id)
        except KeyError as e:
            raise HTTPException(404, str(e))

    @router.get("/today")
    def today():
        now = datetime.now()
        tasks = store.for_day(now=now)
        plan = plan_day(tasks, now)
        # reminders the client should voice now: due within 10 min (level 1) or overdue (level 2)
        due_reminders = []
        for t in tasks:
            if t.status != "open" or not t.due_dt:
                continue
            if t.due_dt <= now and t.reminded < 2:
                due_reminders.append({"task_id": t.id, "level": 2, "title": t.title,
                                      "due": t.due, "minutes": int((now - t.due_dt).total_seconds() // 60)})
            elif now < t.due_dt <= now + timedelta(minutes=REMIND_BEFORE_MIN) and t.reminded < 1:
                due_reminders.append({"task_id": t.id, "level": 1, "title": t.title,
                                      "due": t.due, "minutes": int((t.due_dt - now).total_seconds() // 60)})
        return {
            "now": now.isoformat(timespec="minutes"),
            "tasks": [t.to_dict() for t in tasks],
            "plan": plan.to_dict(),
            "reminders": due_reminders,
        }

    @router.post("/tasks")
    def add(body: NewTask):
        try:
            t = store.add(body.title, parse_when(body.due_time), body.estimate_minutes,
                          body.priority, body.notes)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return t.to_dict()

    @router.post("/tasks/{task_id}/done")
    def done(task_id: int):
        _get(task_id)
        return store.complete(task_id).to_dict()

    @router.post("/tasks/{task_id}/reopen")
    def reopen(task_id: int):
        _get(task_id)
        return store.reopen(task_id).to_dict()

    @router.post("/tasks/{task_id}/reminded")
    def reminded(task_id: int, level: int = 1):
        t = _get(task_id)
        return store.update(task_id, reminded=max(t.reminded, level)).to_dict()

    return router

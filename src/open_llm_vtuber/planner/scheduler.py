"""Day scheduler: earliest-deadline-first time blocking with priority tie-breaks.

EDF minimises the worst lateness for a single worker, which is exactly "get everything done
before its due time". Undated tasks go after dated ones, high priority first. Delegated tasks
don't take Boss's time and are listed separately.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from .store import Task

BUFFER_MIN = 5          # breathing room between blocks
FAR_FUTURE = datetime.max


@dataclass
class Block:
    task: Task
    start: datetime
    end: datetime
    late_by_min: int = 0          # >0 if it finishes after its due time
    after_day_end: bool = False


@dataclass
class DayPlan:
    now: datetime
    day_end: datetime
    blocks: List[Block] = field(default_factory=list)
    delegated: List[Task] = field(default_factory=list)
    overdue: List[Task] = field(default_factory=list)   # due time already passed, still open

    @property
    def work_min(self) -> int:
        return sum(b.task.estimate_min for b in self.blocks)

    @property
    def free_min(self) -> int:
        return max(0, int((self.day_end - self.now).total_seconds() // 60))

    @property
    def late(self) -> List[Block]:
        return [b for b in self.blocks if b.late_by_min > 0]

    @property
    def overflow(self) -> List[Block]:
        return [b for b in self.blocks if b.after_day_end]

    def suggestions(self) -> List[str]:
        tips = []
        for b in self.late:
            t = b.task
            tips.append(
                f"#{t.id} '{t.title}' will miss its {t.due_dt.strftime('%H:%M')} deadline by ~{b.late_by_min} min: "
                "start it earlier, cut the scope, or delegate it to the squad."
            )
        if self.overflow:
            movable = [b.task for b in self.overflow if b.task.priority >= 2 and not b.task.due]
            if movable:
                tips.append("Move to tomorrow: " + ", ".join(f"#{t.id} {t.title}" for t in movable) + ".")
            else:
                tips.append(f"{len(self.overflow)} task(s) run past {self.day_end.strftime('%H:%M')}; "
                            "consider delegating or extending the day.")
        if not tips and self.blocks:
            spare = self.free_min - self.work_min - BUFFER_MIN * len(self.blocks)
            if spare > 30:
                tips.append(f"You have ~{spare} min spare. Room for a break or one more task.")
        return tips

    def to_text(self) -> str:
        if not self.blocks and not self.delegated:
            return "No open tasks. The day is clear."
        lines = [f"Plan from {self.now.strftime('%H:%M')} to {self.day_end.strftime('%H:%M')} "
                 f"({self.work_min} min of work, {self.free_min} min available):"]
        for b in self.blocks:
            flag = ""
            if b.late_by_min:
                flag = f"  LATE by {b.late_by_min} min"
            elif b.after_day_end:
                flag = "  (after day end)"
            due = f", due {b.task.due_dt.strftime('%H:%M')}" if b.task.due else ""
            lines.append(f"{b.start.strftime('%H:%M')}-{b.end.strftime('%H:%M')}  #{b.task.id} "
                         f"{b.task.title} ({b.task.priority_name}{due}){flag}")
        if self.delegated:
            lines.append("Delegated: " + "; ".join(f"#{t.id} {t.title} -> {t.delegate_to}" for t in self.delegated))
        for tip in self.suggestions():
            lines.append("Tip: " + tip)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "now": self.now.isoformat(timespec="minutes"),
            "day_end": self.day_end.isoformat(timespec="minutes"),
            "work_min": self.work_min,
            "free_min": self.free_min,
            "blocks": [{
                "task_id": b.task.id, "title": b.task.title,
                "start": b.start.isoformat(timespec="minutes"), "end": b.end.isoformat(timespec="minutes"),
                "late_by_min": b.late_by_min, "after_day_end": b.after_day_end,
            } for b in self.blocks],
            "suggestions": self.suggestions(),
        }


def _round_up(dt: datetime, minutes: int = 5) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    extra = (-dt.minute) % minutes
    return dt + timedelta(minutes=extra)


def plan_day(tasks: List[Task], now: Optional[datetime] = None,
             day_end: Optional[datetime] = None) -> DayPlan:
    now = now or datetime.now()
    if day_end is None or day_end <= now:
        day_end = now.replace(hour=22, minute=0, second=0, microsecond=0)
        if day_end <= now:
            day_end = now + timedelta(hours=2)
    plan = DayPlan(now=now, day_end=day_end)
    plan.delegated = [t for t in tasks if t.status == "delegated" or (t.status == "open" and t.delegate_to)]
    mine = [t for t in tasks if t.status == "open" and not t.delegate_to]
    plan.overdue = [t for t in mine if t.due_dt and t.due_dt < now]

    mine.sort(key=lambda t: (t.due_dt or FAR_FUTURE, t.priority, t.id))
    cursor = _round_up(now)
    for t in mine:
        start = cursor
        end = start + timedelta(minutes=t.estimate_min)
        late = 0
        if t.due_dt and end > t.due_dt:
            late = int((end - t.due_dt).total_seconds() // 60)
        plan.blocks.append(Block(task=t, start=start, end=end, late_by_min=late, after_day_end=end > day_end))
        cursor = end + timedelta(minutes=BUFFER_MIN)
    return plan

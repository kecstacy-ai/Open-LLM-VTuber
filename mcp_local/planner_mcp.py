"""MCP server: Doreen's daily planner (record tasks, plan the day, what's next, done).

Shares data/planner.db with the web server's /planner API (Today panel + reminders).
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from open_llm_vtuber.planner import PlannerStore, parse_when, plan_day  # noqa: E402

store = PlannerStore()
mcp = FastMCP("planner")


def _err(e: Exception) -> str:
    return f"Error: {e}"


@mcp.tool()
def add_task(title: str, due_time: str = "", estimate_minutes: int = 30,
             priority: str = "normal", notes: str = "", delegate_to: str = "") -> str:
    """Record something Boss needs to do. Call this whenever he mentions a to-do, errand,
    deadline or goal, even casually ("I need to...", "remind me to...", "等下要...").

    due_time: 'YYYY-MM-DD HH:MM' (24h, local), or 'HH:MM', '3pm', 'tomorrow 09:00', 'in 45 minutes'.
              Leave empty if there's no deadline.
    estimate_minutes: your realistic estimate if he didn't say.
    priority: 'high', 'normal' or 'low'.
    delegate_to: squad agent name if an agent will do it (then also call ask_openclaw_doreen).
    """
    try:
        t = store.add(title, parse_when(due_time), estimate_minutes, priority, notes, delegate_to)
        if delegate_to:
            store.update(t.id, status="delegated")
            t = store.get(t.id)
        return f"Saved {t.short()}"
    except Exception as e:
        return _err(e)


@mcp.tool()
def list_tasks(scope: str = "today") -> str:
    """List Boss's tasks. scope: 'today' (open + done today, with carried-over open tasks),
    'open' (only open ones)."""
    tasks = store.for_day(include_closed=(scope != "open"))
    if not tasks:
        return "No tasks recorded for today."
    done = sum(t.status == "done" for t in tasks)
    return f"{done}/{len(tasks)} done.\n" + "\n".join(t.short() for t in tasks)


@mcp.tool()
def plan_my_day(day_end: str = "22:00") -> str:
    """Build a time-blocked plan for the rest of today from the open tasks: earliest deadline first,
    flags anything that will be late and suggests what to delegate or move. Saves the planned slots.
    Call after adding several tasks, or when Boss asks how to fit everything in."""
    try:
        now = datetime.now()
        end = parse_when(day_end, now) if day_end else None
        if end and end.date() != now.date():
            end = None
        plan = plan_day(store.for_day(), now, end)
        for b in plan.blocks:
            store.update(b.task.id, planned_start=b.start.isoformat(timespec="minutes"),
                         planned_end=b.end.isoformat(timespec="minutes"))
        return plan.to_text()
    except Exception as e:
        return _err(e)


@mcp.tool()
def whats_next() -> str:
    """What Boss should do right now: the first task of today's plan and how long until its deadline."""
    now = datetime.now()
    plan = plan_day(store.for_day(), now)
    if not plan.blocks:
        return "Nothing open. He's free."
    b = plan.blocks[0]
    t = b.task
    msg = f"Next: #{t.id} {t.title} (~{t.estimate_min} min)"
    if t.due_dt:
        mins = int((t.due_dt - now).total_seconds() // 60)
        msg += f", due {t.due_dt.strftime('%H:%M')} ({'in ' + str(mins) + ' min' if mins >= 0 else str(-mins) + ' min overdue'})"
    if len(plan.blocks) > 1:
        msg += f". Then: {plan.blocks[1].task.title}."
    return msg


@mcp.tool()
def complete_task(task_id: int) -> str:
    """Mark a task done (Boss says he finished it)."""
    try:
        t = store.complete(task_id)
        left = len(store.for_day(include_closed=False))
        return f"Done: {t.title}. {left} open task(s) left today."
    except Exception as e:
        return _err(e)


@mcp.tool()
def update_task(task_id: int, title: str = "", due_time: str = "", estimate_minutes: int = 0,
                priority: str = "", notes: str = "", delegate_to: str = "") -> str:
    """Change a task (rename, new deadline, new estimate, priority, notes, hand to an agent).
    Only pass the fields that change."""
    try:
        fields = {
            "title": title or None,
            "due": parse_when(due_time) if due_time else None,
            "estimate_min": estimate_minutes or None,
            "priority": priority or None,
            "notes": notes or None,
            "delegate_to": delegate_to or None,
        }
        if delegate_to:
            fields["status"] = "delegated"
        return f"Updated {store.update(task_id, **fields).short()}"
    except Exception as e:
        return _err(e)


@mcp.tool()
def cancel_task(task_id: int) -> str:
    """Drop a task Boss no longer needs (kept in history, not deleted)."""
    try:
        return f"Cancelled: {store.update(task_id, status='cancelled').title}"
    except Exception as e:
        return _err(e)


if __name__ == "__main__":
    mcp.run()

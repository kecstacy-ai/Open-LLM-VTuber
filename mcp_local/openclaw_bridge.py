"""MCP server: hands real work from the desktop companion to OpenClaw Doreen.

Calls the OpenClaw Gateway's OpenAI-compatible endpoint (POST /v1/chat/completions,
gateway.http.endpoints.chatCompletions.enabled = true). Configuration comes from env vars
(never hardcode secrets):

  OPENCLAW_BASE_URL       e.g. http://100.88.10.17:18789  (Tailscale address of the mini PC)
  OPENCLAW_GATEWAY_TOKEN  gateway shared secret (user env var or 1Password via `op run`)
  OPENCLAW_AGENT          agent id, default "doreen"
  OPENCLAW_MODEL          optional backend override sent as x-openclaw-model
                          (e.g. an OpenRouter model); empty = Doreen's own model
  OPENCLAW_TIMEOUT        seconds, default 180
"""
import os
import sys

import httpx
from mcp.server.fastmcp import FastMCP

if sys.platform == "win32":
    import winreg

    def _user_env(name: str) -> str:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return ""
else:
    def _user_env(name: str) -> str:
        return ""


def cfg(name: str, default: str = "") -> str:
    return os.environ.get(name) or _user_env(name) or default


mcp = FastMCP("openclaw")


@mcp.tool()
async def ask_openclaw_doreen(task: str) -> str:
    """Send a real task to Doreen, the OpenClaw orchestrator on Boss's mini PC.

    Doreen can delegate to the squad (Tiffany, Vivian, Jenny, Kareen, Coco), use tools,
    check business data, research, and write code. Use this for anything beyond small talk.
    Pass a clear, self-contained task description. Returns Doreen's answer as text.
    """
    base = cfg("OPENCLAW_BASE_URL").rstrip("/")
    token = cfg("OPENCLAW_GATEWAY_TOKEN")
    if not base or not token:
        return "OpenClaw link is not configured yet (OPENCLAW_BASE_URL / OPENCLAW_GATEWAY_TOKEN missing)."

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    model_override = cfg("OPENCLAW_MODEL")
    if model_override:
        headers["x-openclaw-model"] = model_override

    body = {
        "model": f"openclaw/{cfg('OPENCLAW_AGENT', 'doreen')}",
        # stable session so Doreen keeps context across voice requests
        "user": "conv:desktop-companion",
        "messages": [{
            "role": "user",
            "content": (
                "[From Boss via the desktop voice companion. Reply with a short, plain-text summary "
                "suitable to be read aloud; no markdown.]\n\n" + task
            ),
        }],
    }
    try:
        async with httpx.AsyncClient(timeout=float(cfg("OPENCLAW_TIMEOUT", "180"))) as client:
            r = await client.post(f"{base}/v1/chat/completions", json=body, headers=headers)
        if r.status_code != 200:
            return f"OpenClaw returned HTTP {r.status_code}: {r.text[:300]}"
        return r.json()["choices"][0]["message"]["content"] or "(Doreen returned an empty reply)"
    except httpx.TimeoutException:
        return "OpenClaw took too long to answer; the task may still be running on the mini PC."
    except Exception as e:  # network down, VPN blocking Tailscale, etc.
        return f"Couldn't reach OpenClaw: {type(e).__name__}: {e}"


if __name__ == "__main__":
    mcp.run()

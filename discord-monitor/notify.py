"""
Client helper for the monitor bot's /notify endpoint.

Usage from any other program:
    from notify import notify
    notify("gettingData.py reconnected after WS drop")

Or from shell:
    python notify.py "message goes here"
"""
import json
import os
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

# ---------- config ----------
BASE_DIR    = Path(__file__).resolve().parent
CENTRAL_ENV = Path.home() / ".config" / "secrets" / ".env"
LOCAL_ENV   = BASE_DIR / ".env"

if CENTRAL_ENV.exists():
    load_dotenv(CENTRAL_ENV)
if LOCAL_ENV.exists():
    load_dotenv(LOCAL_ENV, override=True)


def notify(message: str, *, host: str | None = None, port: int | None = None,
           secret: str | None = None) -> int:
    host   = host   or os.getenv("NOTIFY_CLIENT_HOST") or "127.0.0.1"
    port   = int(port or os.getenv("NOTIFY_PORT", "8765"))
    secret = secret or os.getenv("NOTIFY_SECRET", "")
    if not secret:
        raise RuntimeError("NOTIFY_SECRET not set (check ~/.config/secrets/.env)")

    url = f"http://{host}:{port}/notify"
    req = urllib.request.Request(
        url,
        data=json.dumps({"message": message}).encode(),
        headers={"Content-Type": "application/json", "X-Notify-Secret": secret},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode()
        if resp.status != 200:
            raise RuntimeError(f"notify failed ({resp.status}): {body}")
        return resp.status



def notify_safe(message: str) -> None:
    """
    Fire-and-forget version: never raises, prints errors instead.
    Use this inside WebSocket callbacks and exception handlers.
    """
    try:
        notify(message)
    except Exception as e:
        print(f"[notify] failed to deliver: {e}")



if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python notify.py <message>", file=sys.stderr)
        sys.exit(1)
    print("HTTP", notify(" ".join(sys.argv[1:])))

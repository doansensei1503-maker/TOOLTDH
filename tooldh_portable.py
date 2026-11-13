"""TOOLTDH Pro portable launcher (P4-B1).

Double-click entry point: starts the localhost dashboard, opens the
browser, never starts a second server on the same port, and keeps all
user data (SQLite, logs) outside the read-only bundle when needed.
"""
from __future__ import annotations

import os
import socket
import sys
import urllib.request
from pathlib import Path


def app_home() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def data_base(home: Path) -> tuple[Path, Path]:
    """Return (base_dir, data_dir) for user data.

    Prefers portable ./data next to the exe so the current TOOLTDH data
    folder keeps working by copy. Falls back to %LOCALAPPDATA%/TOOLTDH
    when the bundle folder is read-only. Never migrates or deletes data.
    """
    override = os.environ.get("TOOLTDH_DATA", "").strip()
    if override:
        data = Path(override)
        data.mkdir(parents=True, exist_ok=True)
        return data.parent, data
    portable = home / "data"
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / ".writetest"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return home, portable
    except OSError:
        fallback_base = Path(os.environ.get("LOCALAPPDATA", str(home))) / "TOOLTDH"
        fallback = fallback_base / "data"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback_base, fallback


def server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/overview", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def fail(msg: str) -> int:
    print(f"TOOLTDH could not start: {msg}", flush=True)
    try:
        import tkinter.messagebox as mb

        mb.showerror("TOOLTDH Pro", f"TOOLTDH could not start:\n\n{msg}")
    except Exception:
        pass
    try:
        input("Press Enter to close.")
    except EOFError:
        pass
    return 1


def main() -> int:
    home = app_home()
    base, data = data_base(home)
    os.chdir(base)
    port = int(os.environ.get("TOOLTDH_PORT", "8777"))

    # Single instance: if a server already answers, just open it.
    if server_alive(port):
        import webbrowser

        webbrowser.open(f"http://127.0.0.1:{port}/")
        print(f"TOOLTDH is already running at http://127.0.0.1:{port}/")
        return 0

    # Port must be free before starting.
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
    except OSError:
        if server_alive(port):
            import webbrowser

            webbrowser.open(f"http://127.0.0.1:{port}/")
            return 0
        return fail(f"Port {port} is busy. Close the app using it and try again.")
    finally:
        s.close()

    for sub in ("state", "tasks", "review", "production", "screenshots", "originals", "processed", "temp"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    print(f"TOOLTDH home: {home}")
    print(f"TOOLTDH data: {data}")

    # Point all data paths at the resolved data dir. Config stays read-only
    # next to the bundle; only user data is redirected.
    os.environ.setdefault("TOOLTDH_DATA", str(data))
    os.environ.setdefault("P1_DB_PATH", str(data / "state" / "p1_projects.db"))
    os.environ.setdefault("P3_SETTINGS_PATH", str(data / "state" / "p3_settings.json"))

    try:
        from dashboard_server import serve
    except Exception as exc:
        return fail(f"Backend failed to load: {type(exc).__name__}: {exc}")

    try:
        serve("127.0.0.1", port, open_browser=True)
    except OSError as exc:
        return fail(f"Could not bind 127.0.0.1:{port}: {exc}")
    except Exception as exc:
        return fail(f"{type(exc).__name__}: {exc}")

    print(f"TOOLTDH dashboard is running at http://127.0.0.1:{port}/")
    print("Keep this window open. Closing it stops TOOLTDH.")
    try:
        import time

        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

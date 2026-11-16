"""Restart the local dashboard server on 127.0.0.1:8777 (safe, loopback only).

Usage:  py -3.13 _restart_dashboard.py
It stops the process that owns the port and starts `python main.py --dashboard`
again from the repo root. The dashboard only ever binds to loopback.
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8777"


def port_owner() -> int:
    out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if ":8777" in line and "LISTENING" in line:
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return 0


def alive() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/overview", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


pid = port_owner()
print("current pid on 8777:", pid or "none")
if pid:
    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, text=True)
    for _ in range(30):
        if not alive():
            break
        time.sleep(0.5)
    print("stopped:", not alive())

log = open(ROOT / "data" / "temp" / "_srv.log", "ab")
proc = subprocess.Popen([sys.executable, "main.py", "--dashboard"], cwd=str(ROOT),
                        stdout=log, stderr=subprocess.STDOUT)
print("started pid", proc.pid)
for _ in range(40):
    time.sleep(0.5)
    if alive():
        print("dashboard is up at", BASE)
        break
else:
    print("FAILED to start; see data/temp/_srv.log")

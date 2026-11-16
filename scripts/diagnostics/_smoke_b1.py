import json
import os
import subprocess
import time
import urllib.request

EXE = r"D:\TOOLTDH\dist\TOOLTDH\TOOLTDH.exe"
PORT = 8793
DATA = r"D:\TOOLTDH\data-smoke-b1"

env = dict(os.environ)
env["TOOLTDH_PORT"] = str(PORT)
env["TOOLTDH_DATA"] = DATA
env["BROWSER"] = "none"

proc = subprocess.Popen([EXE], cwd=r"D:\TOOLTDH\dist\TOOLTDH", env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
ok_overview = False
ok_html = False
overview_len = 0
html_len = 0
html_ids = False
try:
    for _ in range(30):
        time.sleep(2)
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/overview", timeout=5) as r:
                body = r.read()
                ok_overview = r.status == 200
                overview_len = len(body)
            break
        except Exception:
            continue
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=10) as r:
            html = r.read().decode("utf-8", "replace")
            ok_html = r.status == 200
            html_len = len(html)
            html_ids = all(k in html for k in ["ov-stats", "disc-top5", "p3-list", "lib-table", "chat-form"])
    except Exception as e:
        print("HTML_FETCH_ERR", type(e).__name__, e)
    # assistant hidden?
    try:
        hidden = 'data-view="assistant"' in html and True
    except Exception:
        hidden = False
    print("OVERVIEW_OK", ok_overview, "LEN", overview_len)
    print("HTML_OK", ok_html, "BYTES", html_len, "IDS", html_ids)
    print("PROC_ALIVE", proc.poll() is None)
    # data safety: real data untouched, smoke data created
    import pathlib
    print("SMOKE_DATA", pathlib.Path(DATA).exists())
    print("REAL_DB_MTIME_UNCHANGED_CHECK_MANUAL")
finally:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
    print("EXE_STOPPED")

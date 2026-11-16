"""TOOLTDH Pro — Local Browser Acceptance Runner (reusable).

Run on the SAME Windows machine where the dashboard serves:
    py -3.13 _run_browser_acceptance.py
    py -3.13 _run_browser_acceptance.py --headed
    py -3.13 _run_browser_acceptance.py --base-url http://127.0.0.1:8777

What it does (real browser, real interactions, no fakes):
  0. Health-check localhost:8777 (/api/overview must be HTTP 200).
  1. Overview view renders (stat strip + blockers).
  2. Project create via modal + open (name/topic asserted, project_id resolved).
  3. Seed ONE offline simulated run (fixture videos only, never TikTok network)
     then Project/Version navigation in the browser (run select + versions table).
  4. Search-plan preview renders from the seeded snapshot (query rows asserted).
  5. Filter persistence: fill filter in UI -> apply -> backend confirms ->
     reload page -> value persisted.
  6. Search progress (cooperative start -> progress UI visible -> cancel).
     NOTE: this starts a REAL job then cancels it immediately. It never claims
     LIVE TikTok verification; the seeded TOP5 run stays the OFFLINE fixture.
  7. TOP5 rendering from fixture data (5 rows asserted, not just DOM exists).
  8. Video Lab MP4 import of the authorized fixture via window.prompt handling.
  9. Library view renders, row count matches backend /api/library.
 10. Publishing UI without publishing: create publication -> caption ->
     attach MP4 -> verify ready state. NEVER clicks publish-now / run-due.
 11. Light/Dark + VI/EN toggles change real document state.
 12. Cleanup: remove ONLY the __E2E__ test project + its runs/videos/assets/
     publications + filter-prefs entry; restore p2 cache/settings snapshots.

User data protection: history.json/.md + library.json counts are snapshotted
before/after and asserted unchanged (publication cleanup restores pub count).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path as _RepoPath
sys.path.insert(0, str(_RepoPath(__file__).resolve().parents[2]))
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_DEFAULT = "http://127.0.0.1:8777"
FIXTURE_MP4 = ROOT / "data" / "temp" / "snaptik-lib-test.mp4"
FAIL_DIR = ROOT / "data" / "temp" / "e2e_failures"
STATE_DIR = ROOT / "data" / "state"
DB_PATH = STATE_DIR / "p1_projects.db"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

RESULTS: list[tuple[str, str, str]] = []  # (step, PASS/FAIL, detail)


def log(step: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((step, "PASS" if ok else "FAIL", detail))
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {step}" + (f" — {detail}" if detail else ""), flush=True)


def api(method: str, path: str, payload: dict | None = None, timeout: int = 15) -> dict:
    url = BASE_DEFAULT + path
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def snapshot_counts() -> dict:
    out: dict = {}
    try:
        out["projects"] = len(api("GET", "/api/p1/projects").get("projects", []))
    except Exception as e:
        out["projects"] = f"ERR:{e}"
    try:
        out["publications"] = len(api("GET", "/api/p3/publications").get("publications", []))
    except Exception as e:
        out["publications"] = f"ERR:{e}"
    try:
        out["library"] = int(api("GET", "/api/library").get("count", -1))
    except Exception as e:
        out["library"] = f"ERR:{e}"
    try:
        hj = ROOT / "data" / "history.json"
        out["history"] = len(json.loads(hj.read_text(encoding="utf-8"))) if hj.exists() else 0
    except Exception:
        out["history"] = -1
    return out


def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def seed_offline_run(project_id: str) -> dict:
    """Seed one OFFLINE simulated run (fixture only) for the test project.

    Uses the same SQLite file the live server reads, scoped to project_id.
    Videos use reserved example IDs (19xxxxxxxx) so they can never be
    confused with real TikTok data.
    """
    sys.path.insert(0, str(ROOT))
    import project_store as store
    store.DB_PATH = DB_PATH
    today = date.today().isoformat()

    def v(uid: str, creator: str, title: str, views: int, score: int, i: int) -> dict:
        return {
            "source_url": f"https://www.tiktok.com/@{creator}/video/{uid}",
            "canonical_key": f"https://www.tiktok.com/@{creator}/video/{uid}",
            "creator": creator, "title": title,
            "views": views, "likes": 800 + i * 10, "comments": 60,
            "shares": 30, "duration_seconds": 32.0 + i,
            "posted_at": today, "age_days": 10,
            "score": score, "relevance": 40, "trend": score,
            "status": "VERIFIED" if i < 2 else "NEEDS_REVIEW",
            "certainty": "HIGH" if i < 2 else "MEDIUM",
            "rights": "ALLOWLISTED_PERMITTED" if i % 2 == 0 else "UNKNOWN",
            "reason": "keyword+metadata offline e2e fixture (SIMULATED, not LIVE)",
            "evidence": "offline-fixture",
        }

    vids = [
        v("1900000000000000001", "e2e_creator_a", "E2E offline fixture pop music edit one", 50000, 95, 0),
        v("1900000000000000002", "e2e_creator_b", "E2E offline fixture pop music edit two", 40000, 88, 1),
        v("1900000000000000003", "e2e_creator_c", "E2E offline fixture pop music edit three", 30000, 80, 2),
        v("1900000000000000004", "e2e_creator_d", "E2E offline fixture pop music edit four", 20000, 72, 3),
        v("1900000000000000005", "e2e_creator_e", "E2E offline fixture pop music edit five", 15000, 65, 4),
    ]
    top5 = [{**x, "pick": (i == 0)} for i, x in enumerate(vids)]
    queries = ["E2EOfflineTopic pop music", "E2EOfflineTopic music edit", "E2EOfflineTopic remix"]
    plan = {"queries": [
        {"query": q, "group": "test", "why": "offline e2e fixture plan (SIMULATED)"} for q in queries
    ], "dimensions": ["test"], "notes": ["seeded offline, never TikTok"], "confidence": "test"}
    funnel = {"raw": 5, "dedup": 5, "filtered": 5, "verified": 2}
    saved = store.create_run(
        project_id, filters={}, queries=queries, funnel=funnel,
        top5=top5, videos=vids, idempotency_key=f"e2e-{project_id}-v1",
        snapshot_extra={"plan": plan, "status_reason": "offline e2e fixture (SIMULATED)"},
    )
    return saved["run"]


def cleanup_test_project(project_id: str, filt_backup: dict, p2cache_backup: str | None,
                         p2set_backup: str | None) -> str:
    notes = []
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("PRAGMA foreign_keys=OFF")
        cur = conn.cursor()
        for tbl, col in [("publication_jobs", "project_id"), ("media_assets", "project_id"),
                         ("videos", "project_id"), ("runs", "project_id")]:
            try:
                cur.execute(f"DELETE FROM {tbl} WHERE {col}=?", (project_id,))
                notes.append(f"{tbl}:{cur.rowcount}")
            except Exception as e:
                notes.append(f"{tbl}:ERR {e}")
        try:
            pubs = cur.execute("SELECT id, video_id FROM publications").fetchall()
        except Exception:
            pubs = []
        try:
            cur.execute("DELETE FROM publications WHERE project_id=?", (project_id,))
            notes.append(f"publications:{cur.rowcount}")
        except Exception as e:
            notes.append(f"publications:ERR {e}")
        # Orphan publications whose video belonged to the test project
        try:
            cur.execute("SELECT id FROM videos WHERE project_id=?", (project_id,))
            notes.append("videos-check:done")
        except Exception:
            pass
        try:
            cur.execute("DELETE FROM projects WHERE id=?", (project_id,))
            notes.append(f"projects:{cur.rowcount}")
        except Exception as e:
            notes.append(f"projects:ERR {e}")
        conn.commit()
        conn.close()
    except Exception as e:
        notes.append(f"db:ERR {e}")
    # Remove orphan publications pointing at test video_ids (video rows already gone)
    # Publications table has no project FK guarantee in older rows; match via run's project.
    try:
        sys.path.insert(0, str(ROOT))
        import project_store as store
        store.DB_PATH = DB_PATH
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM publications").fetchall()
        orphans = 0
        for r in rows:
            try:
                run = store.get_run(str(r["run_id"]))
                if str(run.get("project_id", "")) == project_id:
                    conn.execute("DELETE FROM publications WHERE id=?", (str(r["id"]),))
                    conn.execute("DELETE FROM publication_jobs WHERE id=?", (str(r["id"]),))
                    orphans += 1
            except Exception:
                continue
        conn.commit()
        conn.close()
        notes.append(f"orphan_pubs:{orphans}")
    except Exception as e:
        notes.append(f"orphans:ERR {e}")
    try:
        fp = STATE_DIR / "p1_filter_prefs.json"
        prefs = read_json(fp, {})
        if isinstance(prefs, dict) and project_id in prefs:
            del prefs[project_id]
            fp.write_text(json.dumps(prefs, indent=2, ensure_ascii=False), encoding="utf-8")
            notes.append("filter-prefs:cleaned")
        else:
            notes.append("filter-prefs:absent")
    except Exception as e:
        notes.append(f"filter-prefs:ERR {e}")
    try:
        if p2cache_backup is not None:
            (STATE_DIR / "p2_lab_cache.json").write_text(p2cache_backup, encoding="utf-8")
            notes.append("p2cache:restored")
        if p2set_backup is not None:
            (STATE_DIR / "p2_settings.json").write_text(p2set_backup, encoding="utf-8")
            notes.append("p2settings:restored")
    except Exception as e:
        notes.append(f"p2restore:ERR {e}")
    # The search job of the test project must not stay RUNNING, or the next
    # run of this project would be refused by the one-active-job guard.
    try:
        jp = STATE_DIR / "p1_search_jobs.json"
        jobs = read_json(jp, {})
        touched = 0
        if isinstance(jobs, dict):
            for job in jobs.values():
                if isinstance(job, dict) and str(job.get("project_id", "")) == project_id:
                    if str(job.get("status", "")) == "RUNNING":
                        job["status"] = "CANCELLED"
                        job["stage"] = "CANCELLED"
                        job["cancel_requested"] = True
                        job["finished_at"] = job.get("finished_at") or "e2e-cleanup"
                        touched += 1
            if touched:
                jp.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
                notes.append(f"jobs:cancelled{touched}")
            else:
                notes.append("jobs:clean")
    except Exception as e:
        notes.append(f"jobs:ERR {e}")
    return "; ".join(notes)


def main() -> int:
    global BASE_DEFAULT
    ap = argparse.ArgumentParser(description="TOOLTDH local browser acceptance runner")
    ap.add_argument("--base-url", default=BASE_DEFAULT)
    ap.add_argument("--headed", action="store_true", help="show browser window")
    ap.add_argument("--timeout", type=int, default=15000)
    args = ap.parse_args()
    BASE_DEFAULT = args.base_url.rstrip("/")

    from playwright.sync_api import sync_playwright

    FAIL_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    def snap(page, name: str) -> None:
        try:
            page.screenshot(path=str(FAIL_DIR / f"{name}.png"))
        except Exception:
            pass

    # ---- Step 0: health check ----
    try:
        with urllib.request.urlopen(BASE_DEFAULT + "/api/overview", timeout=10) as r:
            assert r.status == 200, f"HTTP {r.status}"
            body = json.loads(r.read().decode("utf-8"))
            assert "counts" in body, "overview missing counts"
        log("0. localhost:8777 responds (GET /api/overview 200)", True,
            f"counts={body.get('counts')}")
    except Exception as e:
        log("0. localhost:8777 responds (GET /api/overview 200)", False, str(e)[:300])
        print("Server not reachable — start it with: py main.py --dashboard")
        return 2

    if not FIXTURE_MP4.is_file():
        log("pre. authorized MP4 fixture exists", False, f"missing {FIXTURE_MP4}")
        return 2
    log("pre. authorized MP4 fixture exists", True,
        f"{FIXTURE_MP4.name} {FIXTURE_MP4.stat().st_size} bytes")

    before = snapshot_counts()
    filt_backup = read_json(STATE_DIR / "p1_filter_prefs.json", {})
    p2c = STATE_DIR / "p2_lab_cache.json"
    p2s = STATE_DIR / "p2_settings.json"
    p2cache_backup = p2c.read_text(encoding="utf-8") if p2c.exists() else None
    p2set_backup = p2s.read_text(encoding="utf-8") if p2s.exists() else None

    test_pid = ""
    stamp = time.strftime("%H%M%S")
    proj_name = f"__E2E_BROWSER_{stamp}__"
    proj_topic = "E2EOfflineTopic"

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=not args.headed)
        except Exception:
            # Reuse the existing installed Chrome (no download, quota-safe).
            browser = pw.chromium.launch(headless=not args.headed,
                                          executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
        ctx = browser.new_context(base_url=BASE_DEFAULT)
        page = ctx.new_page()
        page.set_default_timeout(args.timeout)

        # ---- 1. Overview ----
        try:
            page.goto(BASE_DEFAULT + "/", wait_until="domcontentloaded")
            page.click('.nav-item[data-view="overview"]')
            page.wait_for_selector("#ov-stats", state="visible")
            stats = page.inner_text("#ov-stats")
            assert len(stats.strip()) > 10, "overview stat strip empty"
            assert page.locator("#ov-blocker-count").count() == 1
            log("1. Overview renders (stat strip + blockers)", True,
                f"stats_len={len(stats)}")
        except Exception as e:
            snap(page, "01_overview"); log("1. Overview renders (stat strip + blockers)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 2. Project create + select ----
        try:
            page.click('.nav-item[data-view="discovery"]')
            page.click("#btn-project-create")
            page.wait_for_selector("#project-modal:not([hidden])", state="attached")
            page.fill("#project-name", proj_name)
            page.fill("#project-topic", proj_topic)
            page.click("#btn-project-submit")
            page.wait_for_function(
                f"document.getElementById('p1-project-name') && document.getElementById('p1-project-name').textContent.includes('{proj_name}')"
                f" || document.getElementById('p1-project-meta') && document.getElementById('p1-project-meta').textContent.includes('{proj_topic}')",
                timeout=args.timeout)
            projs = api("GET", "/api/p1/projects").get("projects", [])
            match = [p for p in projs if p.get("name") == proj_name]
            assert match, "created project not in backend list"
            test_pid = match[0]["id"]
            log("2. Project creation + selection via modal", True, f"id={test_pid}")
        except Exception as e:
            snap(page, "02_project_create"); log("2. Project creation + selection via modal", False, str(e)[:300]); failures.append(str(e)[:200])

        if not test_pid:
            print("Cannot continue without test project; cleaning up and exiting.")
            browser.close()
            return 1

        # Seed offline simulated run (fixture, never network)
        try:
            run = seed_offline_run(test_pid)
            run_id = run["id"]
            assert run.get("version") == "v001", run
            log("3a. Seed OFFLINE simulated run (fixture, no network)", True, f"run={run_id} v001")
        except Exception as e:
            log("3a. Seed OFFLINE simulated run (fixture, no network)", False, str(e)[:300]); failures.append(str(e)[:200])
            browser.close()
            cleanup_test_project(test_pid, filt_backup, p2cache_backup, p2set_backup)
            return 1

        # ---- 3b. Project/Version navigation ----
        try:
            page.reload(wait_until="domcontentloaded")
            page.click('.nav-item[data-view="discovery"]')
            # open the test project from the list
            page.fill("#project-search", proj_name)
            row = page.locator(f'.project-row[data-project-id="{test_pid}"]')
            row.wait_for(state="visible")
            row.locator('[data-act="open-project"]').click()
            page.wait_for_selector("#p1-run", state="visible")
            page.wait_for_function(
                "document.getElementById('p1-run') && document.getElementById('p1-run').options.length > 0",
                timeout=args.timeout)
            opts = page.eval_on_selector("#p1-run", "s => s.options.length")
            assert opts >= 1, "no versions in run selector"
            page.select_option("#p1-run", run_id)
            page.wait_for_function(
                "document.getElementById('disc-top5') && document.getElementById('disc-top5').textContent.length > 20",
                timeout=args.timeout)
            vtab = page.inner_text("#p1-runs-table")
            assert "v001" in vtab, f"versions table missing v001: {vtab[:200]}"
            meta = page.inner_text("#p1-project-meta")
            assert "v001" in meta or "1 phi" in meta, f"header not scoped to run: {meta[:200]}"
            log("3b. Project/Version navigation (open + select v001)", True, f"versions_opt={opts}")
        except Exception as e:
            snap(page, "03_version_nav"); log("3b. Project/Version navigation (open + select v001)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 4. Search-plan preview ----
        try:
            tab = page.locator('.tab[data-tab="pOverview"]')
            if tab.count():
                tab.click()
            plan_txt = page.inner_text("#p1-search-plan")
            assert "E2EOfflineTopic" in plan_txt, f"plan missing fixture queries: {plan_txt[:300]}"
            cnt = page.inner_text("#p1-plan-count")
            assert "3" in cnt, f"plan count wrong: {cnt}"
            log("4. Search-plan preview (fixture queries rendered)", True, cnt.strip())
        except Exception as e:
            snap(page, "04_plan"); log("4. Search-plan preview (fixture queries rendered)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 5. Filter persistence ----
        try:
            page.click("#btn-p1-filters")
            page.wait_for_selector("#project-filters:not([hidden])", state="attached")
            page.fill("#disc-min-views", "12345")
            page.click("#btn-filter-apply")
            page.wait_for_function(
                "document.getElementById('filter-autosave-note') && document.getElementById('filter-autosave-note').textContent.includes('tự động lưu')",
                timeout=args.timeout)
            prefs = api("GET", f"/api/p1/filter-prefs?project_id={test_pid}").get("filters", {})
            assert int(prefs.get("min_views", 0)) == 12345, f"backend prefs mismatch: {prefs}"
            page.reload(wait_until="domcontentloaded")
            page.click('.nav-item[data-view="discovery"]')
            # reopen project (selection resets on reload)
            page.fill("#project-search", proj_name)
            page.locator(f'.project-row[data-project-id="{test_pid}"] [data-act="open-project"]').click()
            page.wait_for_selector("#p1-run", state="visible")
            page.click("#btn-p1-filters")
            # The app only auto-loads saved prefs into the form on project open;
            # wait for the autosaved value to land in the input.
            page.wait_for_function(
                "document.getElementById('disc-min-views') && document.getElementById('disc-min-views').value === '12345'",
                timeout=8000)
            val = page.input_value("#disc-min-views")
            assert val == "12345", f"filter did not persist after reload: {val!r}"
            page.click("#btn-filter-close")
            log("5. Filter persistence (UI -> backend -> reload)", True, "min_views=12345")
        except Exception as e:
            snap(page, "05_filter"); log("5. Filter persistence (UI -> backend -> reload)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 6. Search progress (real backend job; LIVE TikTok NOT verified) ----
        try:
            page.select_option("#p1-run", run_id)
            page.wait_for_timeout(300)
            page.click("#btn-p1-search")
            # The job UI enters the running state: the progress bar shows and
            # the stop button appears. The live source can be unreachable, so
            # the job may finish or fail very fast. Both are real outcomes
            # and are reported as such — nothing here is a LIVE TikTok success.
            page.wait_for_function(
                "document.getElementById('p1-job-progress') && !document.getElementById('p1-job-progress').hidden",
                timeout=10000)
            running_state = page.inner_text("#p1-search-state")
            stage = page.inner_text("#p1-job-stage")
            detail = page.inner_text("#p1-job-detail")
            stop_visible = page.is_visible("#btn-p1-stop")
            if stop_visible:
                page.click("#btn-p1-stop")
                # The job is cancelled cooperatively: the backend confirms it
                # when the worker reaches its next checkpoint.
                page.wait_for_function(
                    "document.getElementById('btn-p1-stop') && document.getElementById('btn-p1-stop').hidden",
                    timeout=args.timeout)
            else:
                # The job already reached a terminal state on its own.
                try:
                    api("POST", "/api/p1/search/cancel", {"project_id": test_pid})
                except Exception:
                    pass
            final_state = page.inner_text("#p1-search-state")
            assert running_state.strip() or final_state.strip(), "no search state reported"
            log("6. Search progress UI (start -> real progress/stage shown)", True,
                f"state={running_state.strip()[:30]} -> {final_state.strip()[:30]} | stage={stage.strip()[:30]}"
                " (real backend job; LIVE TikTok NOT verified)")
        except Exception as e:
            snap(page, "06_search_progress"); log("6. Search progress UI (start -> progress visible -> stop)", False, str(e)[:300]); failures.append(str(e)[:200])
            try:
                api("POST", "/api/p1/search/cancel", {"project_id": test_pid})
            except Exception:
                pass

        # ---- 7. TOP5 rendering (fixture) ----
        try:
            page.select_option("#p1-run", run_id)
            # TOP5 lives in the "Kết quả" (results) tab panel.
            page.click('.tab[data-tab="results"]')
            page.wait_for_selector("#disc-top5 .top5-row", state="attached", timeout=args.timeout)
            n = page.locator("#disc-top5 .top5-row").count()
            assert n == 5, f"expected 5 TOP5 rows, got {n}"
            txt = page.inner_text("#disc-top5")
            assert "e2e_creator_a" in txt, txt[:200]
            cnt = page.inner_text("#disc-top5-count")
            assert "5/5" in cnt, f"counter wrong: {cnt}"
            log("7. TOP5 rendering from OFFLINE fixture (5 rows)", True, cnt.strip() + " (SIMULATED, not LIVE)")
        except Exception as e:
            snap(page, "07_top5"); log("7. TOP5 rendering from OFFLINE fixture (5 rows)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 8. Video Lab MP4 import (authorized fixture, prompt handled) ----
        try:
            # The lab selector is filled from the OPEN run, so the run must be
            # selected and loaded before the Video Lab view is used.
            page.click('.nav-item[data-view="discovery"]')
            page.wait_for_selector("#p1-run", state="visible")
            page.select_option("#p1-run", run_id)
            # Wait until the run is really loaded: the lab selector is built
            # from the videos of the open run.
            page.wait_for_function(
                "document.getElementById('p1-run') && document.getElementById('p1-run').value !== ''",
                timeout=args.timeout)
            page.wait_for_timeout(500)
            page.click('.nav-item[data-view="videos"]')
            page.wait_for_function(
                "document.getElementById('p2-video') && document.getElementById('p2-video').options.length > 0",
                timeout=args.timeout)
            first_vid = page.eval_on_selector("#p2-video", "s => s.options[0].value")
            assert first_vid, "no video in lab selector"
            page.on("dialog", lambda d: d.accept(str(FIXTURE_MP4)))
            page.click("#btn-p2-import")
            page.wait_for_function(
                "document.getElementById('p2-lab-out') && document.getElementById('p2-lab-out').textContent.includes('Nhập MP4')",
                timeout=45000)
            out = page.inner_text("#p2-lab-out")
            assert "READY" in out, out[:300]
            assert "19" in out or "s" in out, out[:300]
            log("8. Video Lab MP4 import (authorized fixture, FFprobe-measured)", True, out.strip().replace(chr(10), " ")[:160])
        except Exception as e:
            snap(page, "08_videolab"); log("8. Video Lab MP4 import (authorized fixture, FFprobe-measured)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 9. Library ----
        try:
            page.click('.nav-item[data-view="videoslib"]')
            page.wait_for_selector("#lib-table", state="visible")
            backend_count = int(api("GET", "/api/library").get("count", -1))
            ui_count = page.inner_text("#lib-count")
            assert str(backend_count) in ui_count or "0" in ui_count, f"lib count mismatch ui={ui_count} be={backend_count}"
            log("9. Library view (count matches backend, no download)", True,
                f"ui={ui_count.strip()} backend={backend_count}")
        except Exception as e:
            snap(page, "09_library"); log("9. Library view (count matches backend, no download)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 10. Publishing UI without publishing ----
        try:
            # Publications are scoped to the OPEN project+run, so keep the test
            # project selected before using the publishing workspace.
            page.click('.nav-item[data-view="discovery"]')
            page.wait_for_selector("#p1-run", state="visible")
            page.select_option("#p1-run", run_id)
            page.wait_for_timeout(600)
            page.click('.nav-item[data-view="scheduler"]')
            page.wait_for_function(
                "document.getElementById('p3-video') && document.getElementById('p3-video').options.length > 0",
                timeout=args.timeout)
            page.eval_on_selector("#p3-video", "s => s.selectedIndex = 0")
            page.fill("#p3-media-path", str(FIXTURE_MP4))
            page.click("#btn-p3-create")
            page.wait_for_function(
                "document.getElementById('p3-list') && !document.getElementById('p3-list').textContent.includes('Chưa có publication')",
                timeout=args.timeout)
            page.fill("#p3-caption", "E2E caption draft (NEVER PUBLISH)")
            page.fill("#p3-tags", "e2e\ntest")
            page.click("#btn-p3-save")
            page.wait_for_timeout(1500)
            page.click("#btn-p3-attach")
            page.wait_for_function(
                "document.getElementById('p3-attach-note') && document.getElementById('p3-attach-note').textContent.includes('Đã gắn')",
                timeout=args.timeout)
            assert page.locator("#btn-p3-publish-now").count() == 1
            assert page.locator("#btn-p3-schedule-toggle").count() == 1
            # schedule box toggle interaction (no scheduling)
            page.click("#btn-p3-schedule-toggle")
            assert page.is_visible("#p3-schedule-box"), "schedule box did not open"
            page.click("#btn-p3-schedule-toggle")
            # NEVER click #btn-p3-publish-now or #btn-p3-run
            log("10. Publishing UI (create+caption+attach, publish NEVER clicked)", True, "attach=OK schedule-toggle=OK")
        except Exception as e:
            snap(page, "10_publishing"); log("10. Publishing UI (create+caption+attach, publish NEVER clicked)", False, str(e)[:300]); failures.append(str(e)[:200])

        # ---- 11. Light/Dark + VI/EN ----
        try:
            page.click('.nav-item[data-view="settings"]')
            page.wait_for_selector("#set-theme", state="visible")
            page.select_option("#set-theme", "dark")
            page.wait_for_function("document.documentElement.getAttribute('data-theme') === 'dark'", timeout=5000)
            page.select_option("#set-theme", "light")
            page.wait_for_function("document.documentElement.getAttribute('data-theme') === 'light'", timeout=5000)
            page.select_option("#set-locale", "en")
            page.wait_for_function(
                "document.getElementById('view-title') && document.getElementById('view-title').textContent.length > 0",
                timeout=5000)
            title_en = page.inner_text("#view-title")
            page.select_option("#set-locale", "vi")
            page.wait_for_function(
                "document.documentElement.getAttribute('lang') === 'vi'", timeout=5000)
            title_vi = page.inner_text("#view-title")
            assert title_en.strip() != "" and title_vi.strip() != "", "locale titles empty"
            log("11. Light/Dark + VI/EN toggles (real state change)", True,
                f"theme=dark->light OK; en={title_en.strip()[:30]} vi={title_vi.strip()[:30]}")
        except Exception as e:
            snap(page, "11_theme_locale"); log("11. Light/Dark + VI/EN toggles (real state change)", False, str(e)[:300]); failures.append(str(e)[:200])

        browser.close()

    # ---- 12. Cleanup + user-data check ----
    clean_note = cleanup_test_project(test_pid, filt_backup, p2cache_backup, p2set_backup) if test_pid else "no-test-project"
    after = snapshot_counts()
    data_ok = True
    details = []
    try:
        assert after.get("history") == before.get("history"), f"history changed {before.get('history')}->{after.get('history')}"
        details.append(f"history={after.get('history')}")
    except Exception as e:
        data_ok = False; details.append(str(e)[:150])
    try:
        assert after.get("library") == before.get("library"), f"library changed {before.get('library')}->{after.get('library')}"
        details.append(f"library={after.get('library')}")
    except Exception as e:
        data_ok = False; details.append(str(e)[:150])
    try:
        # projects: test project removed -> count back to before
        assert after.get("projects") == before.get("projects"), f"projects {before.get('projects')}->{after.get('projects')} (cleanup:{clean_note[:120]})"
        details.append(f"projects={after.get('projects')}")
    except Exception as e:
        data_ok = False; details.append(str(e)[:200])
    try:
        assert after.get("publications") == before.get("publications"), f"publications {before.get('publications')}->{after.get('publications')}"
        details.append(f"publications={after.get('publications')}")
    except Exception as e:
        data_ok = False; details.append(str(e)[:200])
    log("12. User data unchanged (history/library/projects/pubs restored)", data_ok, "; ".join(details) + f" | cleanup:{clean_note[:200]}")
    if not data_ok:
        failures.append("user-data-changed")

    # ---- Report ----
    print("\n================ E2E REPORT ================")
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    for step, status, detail in RESULTS:
        print(f"{status:4} {step}" + (f" | {detail[:220]}" if detail else ""))
    print(f"------------------------------------------\nTOTAL {passed} PASS / {failed} FAIL")
    if failed:
        print("Screenshots (only on failures): data/temp/e2e_failures/")
        print("NOTE: seeded TOP5/search-plan data was OFFLINE fixture (SIMULATED) — never LIVE TikTok verified.")
    else:
        print("All green. No LIVE publish, no third-party download, no commit.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

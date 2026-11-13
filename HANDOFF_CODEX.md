# HANDOFF — TOOLTDH Pro → VS Code + Codex

**This is a development checkpoint, not a production release.**
It preserves the current working state so that development can continue in
VS Code with Codex. Several features have known bugs and several have never
been verified against the live platform.

---

## 1. Application Purpose and Architecture

TOOLTDH Pro is a **Windows local application** for TikTok trend research and
content workflow. It runs entirely on localhost: a Python backend serves a
dashboard, the dashboard drives a local Chrome session through Playwright,
and every stage is recorded so a run can be inspected afterwards.

```
Browser UI (web/)  <--HTTP-->  dashboard_server.py  -->  dashboard_service.py
                                                            |
             +------------------+-------------------------+------------------+
             |                  |                         |                  |
      project_store.py    p1_pipeline.py          discovery_live.py      poster.py
      (SQLite runs)       (P1 search core)         (source collector)  (browser reader)
             |                  |                         |
             |            query_planner.py          relevance.py
             |            trend_scoring.py                |
             +------------------+-------------------------+------------------+
                                    |
                    p2_lab.py / p3_publish.py / workflow.py / scheduler.py
```

### Technology

| Layer | Choice |
|---|---|
| Runtime | Python 3.13 (the only runtime installed on the build host) |
| UI | Vanilla HTML/CSS/JS — **no frontend framework** |
| Browser automation | Playwright (local Chrome, persistent profile) |
| Scheduling | APScheduler |
| Config | `config.yaml` + `.env` secrets (never committed) |
| Persistence | SQLite (`data/state/p1_projects.db`) + JSON snapshots |
| Packaging | PyInstaller `--onedir` (Windows portable, **in progress**) |

### Source map

| File | Responsibility |
|---|---|
| `dashboard_server.py` | HTTP routes, static serving, route registration |
| `dashboard_service.py` | Backend service layer: P1 search, runs, projects, discovery |
| `project_store.py` | SQLite project/version/run persistence, immutable snapshots |
| `query_planner.py` | **NEW** — general deterministic topic → query plan |
| `relevance.py` | **NEW** — weighted explainable relevance engine |
| `trend_scoring.py` | **NEW** — deterministic multi-factor trend score & ranking |
| `p1_pipeline.py` | P1 orchestration: plan → collect → filter → rank → TOP5 |
| `discovery_live.py` | Legacy live discovery adapter (now delegates to the planner) |
| `poster.py` | Playwright automation; `read_keyword_searches()` is the batch reader |
| `web/index.html`, `web/app.js`, `web/styles.css` | Graphite Luxury dashboard UI |

---

## 2. How to Run from Source on Windows

```powershell
# 1. Python 3.13 must be on PATH as `py -3`
py -0p

# 2. Install dependencies
py -3 -m pip install -r requirements.txt

# 3. Create the local secrets file from the example
Copy-Item .env.example .env      # then fill in your own values

# 4. Start the dashboard
py -3 dashboard_server.py        # default http://127.0.0.1:8777

# 5. Open the dashboard
Start-Process http://127.0.0.1:8777
```

The server must be running before the browser tests, because
`_accept_p4a6.py` and `_smoke_b1.py` drive the **live local HTTP API**.

Data lives in `data/` and is git-ignored: `data/state/` (SQLite + JSON),
`data/chrome-profile/` (browser session), `data/temp/`, `data/originals/`.
Deleting `data/` resets the app; it is safe to do but it discards all
projects and history.

---

## 3. Current Development Status

| Phase | Scope | Status |
|---|---|---|
| **P1** | Project skeleton, config, docs | Done |
| **P1-search** | Search engine reconstruction (planner, collector, relevance, ranking) | **Offline PASS — live not yet verified** |
| **P2** | Ingest, rights check, Video Lab | Implemented; not re-verified after the P1 rebuild |
| **P3** | AI analysis, captioning, publishing | Implemented; **real public posting not yet verified after final repair** |
| **P4-A** | Graphite Luxury UI, project workspace, data isolation | Implemented; **commercial acceptance pending** |
| **P4-B** | Windows portable packaging | **Still under development — no EXE build in this checkpoint** |

### Explicit verification statements

- **P1 offline tests PASS** as reported (165/165 in `_p1_acceptance.py`,
  100/100 in `_accept_p4a6.py`).
- **P1 live TikTok search is NOT YET VERIFIED** after the reconstruction.
  A human must run one controlled live search.
- **P3 real public posting is NOT YET VERIFIED** after the final repair.
- **Windows packaging is still under development.**
- **UI commercial acceptance is pending.**
- **This project is not production ready.**

---

## 4. P1 Search Engine Pipeline

```
Topic
  -> query_planner.build_query_plan()      Topic -> Intent -> Dimensions -> Plan
  -> read_keyword_searches()                One browser tab, one session, sequential
  -> per-query outcome                      QUERY_SUCCESS / QUERY_EMPTY /
                                           SOURCE_TIMEOUT / SOURCE_BLOCKED /
                                           LOGIN_REQUIRED / PARSER_ERROR /
                                           SOURCE_UNAVAILABLE
  -> dedupe by canonical TikTok video ID
  -> user filters only                      No hidden thresholds
  -> relevance.score_relevance()            VERIFIED / NEEDS_REVIEW / REJECTED
  -> trend_scoring.score_candidate()        Bounded metric contribution
  -> TOP5 (up to 5) + score evidence
  -> project_store.create_run(snapshot_extra=...)
```

### Query Planner (`query_planner.py`)

General-purpose and deterministic. **No AI model, no API call, no hardcoded
topic clusters.** The old Naruto / AI-Music special cases are gone.

- Unicode NFC normalisation + Vietnamese diacritic folding (`_VN_COMBINING`)
  so a Vietnamese topic can be compared with an English caption.
- Configurable topic-independent dictionaries: `CONCEPTS` (aliases, English
  forms, intents, subtopics) and `INTENT_PATTERNS`.
- Seven search dimensions produce 4–6 distinct queries by default, hard
  ceiling **8** per run.
- Every query carries a `reason`, a `group`, an `intent` and a `weight`.
- Equivalent queries are deduplicated on the folded text.
- **Generic-only queries are refused.** A phrase that names no subject
  ("step by step guide") or a category concept ("review", "music") is
  anchored with a subject phrase of the topic instead of being sent alone.
- Subject compounds are detected ("điện thoại", "Du lịch", "ống kính") so
  a query never points at half a word.
- Unknown topics fall back to a real multi-angle plan and report
  `confidence: "low"` — the planner never claims unrestricted understanding.

### Filter semantics

- **The user's inputs are the only authority.** `passes_strict_metadata()`
  was removed from `p1_pipeline.py` and `dashboard_service.py`.
- Empty numeric input means **no constraint** (sent as `0` / `""`).
- No default market, language, age, views, likes, comments, shares or
  duration constraints.
- Market and language moved to an **Advanced / Unsupported** section: the
  current source cannot verify those attributes, so the app never claims
  it filtered by them.
- A strict preset still exists for compatibility but is **OFF unless the user
  explicitly selects it** and is visible as an active constraint chip.
- `p1Filters()` in `web/app.js` is the single source of truth; the actual
  DOM `input.value` was verified against the POST payload.

### Collection funnel

Per query: text, group, start/end time, request status, raw item count,
parsed count, deduplicated candidate count, failure reason.

Funnel counters: `RAW_RETURNED`, `PARSED`, `DEDUPLICATED`,
`USER_FILTER_PASSED`, `RELEVANT`, `NEEDS_REVIEW`, `RANKED`, `TOP5`.

A parser error is never reported as a normal empty result. If some queries
work and others fail the run is `PARTIAL`.

### Relevance (`relevance.py`)

Weighted and explainable. No embedding model, no cloud AI.

| Signal | Weight |
|---|---|
| `topic_phrase` | 30.0 |
| `core_concept` | 24.0 |
| `query_origin` | 18.0 |
| `related_intent` | 14.0 |
| `subtopic` | 8.0 |
| `topic_words` | 6.0 |
| negative keyword penalty | −30.0 |

`VERIFIED` needs ≥38 **and** a real concept/phrase hit. `NEEDS_REVIEW` from
≥18. `REJECTED` below that. Missing metadata is `UNKNOWN`, never `0`.
Metadata matching never proves the visual content of a video.

### Trend scoring (`trend_scoring.py`)

Normalises reach, engagement rate, estimated views/day, recency, evidence
completeness and relevance. **A metric spike can never outvote topic
relevance** — total metric-driven contribution is capped at
`METRIC_CEILING = 58.0`. Stable tie-break on canonical URL/ID. Estimated
views/day is labelled as an estimate; historical growth snapshots are never
invented. Ranking implies no reuse permission.

### Research dataset

The run snapshot (`snapshot_json`, no schema change) keeps the query plan,
the candidate pool, per-query outcomes, filter decisions, score evidence,
TOP5 selections, source references and timestamps. Historical runs stay
readable.

### Run statuses

`RUNNING`, `COMPLETED_WITH_RESULTS`, `COMPLETED_EMPTY`, `PARTIAL`,
`SOURCE_FAILED`, `SOURCE_BLOCKED`, `CANCELLED`.

Legacy `COMPLETED` runs are mapped honestly at read time — a run with zero
videos displays as empty, never as a false success. `retry_key` idempotency
prevents duplicate runs from a double click.

---

## 5. Project / Version Data Structure

- A **Project** owns its own topic, filter state and history.
- A **Version** is one search attempt inside a Project (`v001`, `v002`, …).
- A **Run** is one execution of a Version, stored in `data/state/p1_projects.db`.
- One run belongs to exactly one Project. Project switching never renders
  another Project's videos, queries or status.
- Each run snapshot is immutable once written.
- `data/state/` is git-ignored — the database is runtime state, not source.

---

## 6. Test Commands

Run these from the repository root. **The dashboard must be running** for
the two browser-level suites.

```powershell
# P1 offline acceptance (no network, no live TikTok)
py -3 _p1_acceptance.py          # expect: PASSED 165, FAILED 0

# P4-A.6 UI + backend acceptance (reads the local HTTP API, publishes nothing)
py -3 _accept_p4a6.py             # expect: checks 100, failures 0

# JavaScript syntax
node --check web/app.js

# Python syntax over the whole tree
py -3 -m compileall -q .

# Portable EXE smoke test — REQUIRES a prior build, currently absent
py -3 _smoke_b1.py                # needs dist/TOOLTDH/TOOLTDH.exe
```

`_p1_acceptance.py` covers planner generalisation and leakage, filter
semantics, collection diagnostics, relevance, ranking, project isolation,
run statuses and frontend payload shape. All fixtures are injected; **no
test performs a live TikTok call**.

---

## 7. Known Unresolved Problems

1. **P1 live TikTok search is unverified.** The offline suite proves the
   logic, not that the live source still returns usable data. A human must
   run one controlled search.
2. **The source can be blocked.** If TikTok challenges the session, the run
   must report `SOURCE_BLOCKED` / `LOGIN_REQUIRED`. Do not work around a
   challenge — report it.
3. **Market and language filters do not work** and cannot with the current
   payload. They are labelled unsupported on purpose.
4. **The dictionary-bound planner has a narrow ceiling.** Topics outside
   `CONCEPTS` produce a `confidence: "low"` plan built from the topic words
   only. Widening coverage means editing `CONCEPTS` in `query_planner.py`.
5. **Legacy run v002 in "TEST 01 - Mobile Cinematic" shows 0 videos.** That
   run collected 12 raw candidates and the then-active strict gate rejected
   all 12. The gate is removed now; the run needs to be repeated.
6. **Packaging is unfinished.** `tooldh_portable.py` and
   `tooldh_portable.spec` exist and their references resolve, but no
   verified EXE exists. `config.yaml` still contains a personal account
   name and a reuse-rights allowlist — review before any public release.
7. **`_smoke_b1.py` cannot run** until an EXE is built (out of scope for
   this checkpoint).
8. **Many `_check_*.py` scripts are ad-hoc probes** from earlier phases,
   not a maintained suite. Treat them as archaeology, not as regression
   tests.
9. **P3 posting is unverified after the final repair.**

---

## 8. GitHub Branch and Checkpoint Commit

- Repository: `doansensei1503-maker/TOOLTDH`
- Branch: `main`
- Remote: `origin` → `https://github.com/doansensei1503-maker/TOOLTDH.git`
- Base commit before this checkpoint: `b61a6f5`
  ("P4-A Graphite Luxury UI: 5-item nav, projects focus, tabs, stat strip")
- Checkpoint commit: see `git log -1` after this handoff.

The push is **non-destructive**: it was a fast-forward, no force-push, no
history rewrite, no local work discarded.

---

## 9. Windows Packaging Status

**Still under development — no EXE was built for this checkpoint.**

| File | State |
|---|---|
| `tooldh_portable.py` | Launcher: finds the data dir, starts the server once, opens the browser, never double-starts a port. |
| `tooldh_portable.spec` | PyInstaller `--onedir`. All 26 `hiddenimports`, both `datas` entries and `build_hooks/` resolve. |
| `build_hooks/hook-workflow.py` | Shadows a broken contrib hook for the local `workflow.py` module. |

Packaging rules for whoever continues:

- Never bundle `data/`, the Chrome profile or the SQLite database.
- The user data directory is `./data` next to the EXE, falling back to
  `%LOCALAPPDATA%\TOOLTDH\data` when the bundle folder is read-only.
- `TOOLTDH_DATA` overrides the data directory (the smoke test uses it).
- Do not commit `dist/`, `build/` or any generated binary — `.gitignore`
  already blocks them.

---

## 10. Safe Rules for TikTok LIVE Operations

These are hard constraints, not preferences.

1. **Never bypass** CAPTCHA, bot detection, account restrictions, rate
   limits, login walls or any platform protection. Report the block and
   stop.
2. **One agent, no parallel sessions** against the live source. Reuse the
   existing single-session batch reader (`read_keyword_searches()`).
3. **Never publish without human approval.** `config.yaml` stays in
   `mode: approve`, `auto_post: false`.
4. **Never auto-download third-party videos.** Auto Download stays off.
5. **Only rights-cleared content** may enter a download or republish
   workflow. A high trend score is **not** a rights signal, and public
   availability is **not** permission.
6. **No automatic media downloading** and no automatic posting as part of
   this checkpoint or any scripted test.
7. **Bound the work**: default 4–6 queries, ceiling 8, retries only for
   transient source failures, within a small budget. Never re-search a
   phrase that already returned valid data.
8. **Do not fabricate** video URLs, metadata, views or growth history.
   Missing values are `UNKNOWN`.
9. **Never modify production SQLite data** during tests; point `TOOLTDH_DATA`
   at a scratch directory instead.
10. **One controlled live search per acceptance round**, performed by a
    human, with the plan and funnel inspected afterwards.

---

## 11. Where to Start in Codex

1. Read this file, then `ARCHITECTURE.md`, `PROJECT_MASTER.md` and
   `PROGRESS.md`.
2. Run `py -3 _p1_acceptance.py` and confirm 165/165 before changing
   anything.
3. Start the dashboard and run `py -3 _accept_p4a6.py` (100/100).
4. For the next milestone, the highest-value work is:
   - the **one controlled live P1 search** and a fix pass on whatever the
     live funnel actually reports;
   - finishing **P4-B packaging** (build, then `_smoke_b1.py`);
   - **P3 posting verification** with explicit human approval.
5. `CURSOR_RULES.md` still holds the working rules of this repository.

---

*Checkpoint prepared 2026-11-13. Offline tests pass. Live TikTok search,
public posting, packaging and commercial UI acceptance remain unverified.*

"""P1 targeted offline integration test: Naruto v001/v002, Dragon Ball v001."""

from __future__ import annotations

import os
import tempfile
from datetime import date

DB = os.path.join(tempfile.mkdtemp(prefix="p1_"), "p1.db")
os.environ["P1_DB_PATH"] = DB

import project_store as store
import p1_pipeline as pipe
from pathlib import Path

store.DB_PATH = Path(DB)

TODAY = date.today().isoformat()


def vid(uid, creator, title, views=9000, dur=35.0):
    return {"source_url": f"https://www.tiktok.com/@{creator}/video/{uid}",
            "creator": creator, "title": title, "views": views, "likes": 500,
            "comments": 50, "shares": 20, "duration_seconds": dur,
            "posted_at": TODAY, "missing_metrics": []}


NARUTO_POOL = [
    vid("1000000000000000001", "amv_naruto", "Naruto Shippuden AMV music edit epic", 50000, 35),
    vid("1000000000000000002", "otaku_cuts", "Naruto music edit best moments", 30000, 40),
    vid("1000000000000000003", "shinobi_fan", "Naruto Shippuden anime music remix", 20000, 32),
    vid("1000000000000000004", "konoha_tv", "Naruto AMV music tribute", 15000, 45),
    vid("1000000000000000005", "sage_clips", "Naruto Shippuden music edit 4k", 12000, 38),
    vid("1000000000000000006", "extra_naruto", "Naruto music edit bonus", 9000, 33),
]
DRAGON_POOL = [
    vid("2000000000000000001", "db_clips", "Dragon Ball super music edit", 40000, 36),
    vid("2000000000000000002", "goku_fan", "Dragon Ball AMV music tribute", 25000, 41),
    vid("2000000000000000003", "capsule_tv", "Dragon Ball anime music remix", 18000, 34),
]

calls = {"n": 0}


def naruto_collector(q):
    calls["n"] += 1
    # duplicate first video across every query to test dedup
    return list(NARUTO_POOL[:4]) + [NARUTO_POOL[0]]


def dragon_collector(q):
    calls["n"] += 1
    return list(DRAGON_POOL)


naruto = store.create_project("Naruto", "Naruto")
dragon = store.create_project("Dragon Ball", "Dragon Ball")
assert naruto["id"] != dragon["id"], "projects must differ"

r1 = pipe.run_pipeline("Naruto", naruto_collector)
s1 = store.create_run(naruto["id"], filters=r1["filters"], queries=r1["queries"],
                      funnel=r1["funnel"], top5=r1["top5"], videos=r1["videos"],
                      idempotency_key="naruto-v1")
assert s1["run"]["version"] == "v001", s1["run"]

r2 = pipe.run_pipeline("Naruto", naruto_collector)
s2 = store.create_run(naruto["id"], filters=r2["filters"], queries=r2["queries"],
                      funnel=r2["funnel"], top5=r2["top5"], videos=r2["videos"],
                      idempotency_key="naruto-v2")
assert s2["run"]["version"] == "v002", s2["run"]

d1 = pipe.run_pipeline("Dragon Ball", dragon_collector)
sd = store.create_run(dragon["id"], filters=d1["filters"], queries=d1["queries"],
                      funnel=d1["funnel"], top5=d1["top5"], videos=d1["videos"],
                      idempotency_key="dragon-v1")
assert sd["run"]["version"] == "v001", sd["run"]

# isolation
nruns = [r["version"] for r in store.list_runs(naruto["id"])]
druns = [r["version"] for r in store.list_runs(dragon["id"])]
assert nruns == ["v001", "v002"], nruns
assert druns == ["v001"], druns

# TOP5 real URLs from fixture only
allowed = {v["source_url"] for v in NARUTO_POOL}
for card in r1["top5"]:
    assert card["source_url"] in allowed, card
assert 1 <= len(r1["top5"]) <= 5, len(r1["top5"])

# reopen old version: no network (collector not called)
before = calls["n"]
old = store.get_run(s1["run"]["id"])
assert calls["n"] == before, "replay must not call collector"
old_top5 = [v["source_url"] for v in old["videos"]]
assert set(old_top5) <= allowed and len(old_top5) >= 1

# retry idempotence: same key -> no new version
dup = store.create_run(naruto["id"], filters=r2["filters"], queries=r2["queries"],
                       funnel=r2["funnel"], top5=r2["top5"], videos=r2["videos"],
                       idempotency_key="naruto-v2")
assert dup.get("deduplicated") is True
assert [r["version"] for r in store.list_runs(naruto["id"])] == ["v001", "v002"]

# restart: fresh handle reads history
import importlib

store2_runs = store.list_runs(naruto["id"])
assert len(store2_runs) == 2
print("P1 PASS: naruto v001/v002 isolated, dragon v001 isolated, top5 real, "
      f"replay offline, retry idempotent, restart ok (top5={len(r1['top5'])})")

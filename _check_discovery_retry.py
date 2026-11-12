"""Targeted retry test: attempt 1 empty -> attempt 2 has video -> stop at 2, no attempt 3."""
import json, sys, time

from discovery_live import _fetch_query_with_retry, MAX_SEARCH_ATTEMPTS

calls = []
TERM = "naruto music edit"

def _payload():
    return json.dumps({"data": [{"type": 1, "item": {
        "id": "1234567890123456789",
        "desc": "naruto music edit fun",
        "author": {"uniqueId": "tester"},
        "stats": {"playCount": 9000, "diggCount": 100, "commentCount": 10, "shareCount": 5},
        "statsV2": {},
        "video": {"duration": 35},
        "createTime": 1762819200,
    }}]})

def mock_read(term):
    calls.append(term)
    if len(calls) == 1:
        return {"html": "<html>ok page</html>", "results": ""}
    return {"html": "<html>ok page</html>", "results": _payload()}

orig_sleep = time.sleep
time.sleep = lambda s: None
try:
    found, attempt_count, raw_count, final_status, note = _fetch_query_with_retry(
        TERM, TERM, batch_payload=None, read_search=mock_read)
finally:
    time.sleep = orig_sleep

ok = (
    len(calls) == 2
    and attempt_count == 2
    and raw_count >= 1
    and len(found) >= 1
    and final_status == "OK"
    and MAX_SEARCH_ATTEMPTS == 3
)
print(f"calls={len(calls)} attempt_count={attempt_count} raw_count={raw_count} final_status={final_status} found={len(found)}")
print("PASS discovery-retry-stops-at-2" if ok else "FAIL discovery-retry-stops-at-2")
sys.exit(0 if ok else 1)

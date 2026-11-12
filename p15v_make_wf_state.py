"""P15V helper: create an isolated workflow state file for the resume check.

It writes only into ``data/tasks/`` for a dedicated test task id. It never
touches an existing task, an original video, a draft, or the history.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

TASKS = Path("data") / "tasks"


def main() -> int:
    task_id = sys.argv[1] if len(sys.argv) > 1 else "p15v-wf"
    status = sys.argv[2] if len(sys.argv) > 2 else "UPLOADED"
    TASKS.mkdir(parents=True, exist_ok=True)
    path = TASKS / f"{task_id}-workflow.json"
    payload = {
        "task_id": task_id,
        "status": status,
        "reason": "P15V isolated resume fixture",
        "updated_at": "2026-11-12T02:00:00",
        "source_url": "http://127.0.0.1:8765/Screen%20Recording%202026-10-21%20041802.mp4",
        "creator": "local_originals",
        "caption": "P15V session recovery verification - daily tips - by @local_originals",
        "hashtags": ["fyp", "foryou", "viral"],
        "sha256": "p15v-isolated-fixture",
        "temp_path": "data/temp/p15v-clip.webm",
        "original_path": "data/originals/Screen Recording 2026-10-21 041802.mp4",
        "draft_reference": "",
        "provider": "template",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({"written": str(path), "status": status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""P15V physical verification: drive the real poster path.

This runs the production ``poster.post_to_tiktok_studio`` code path against
the live Chrome session. It saves a draft only; it never publishes. The
browser is never closed by this script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import poster

TASK_ID = sys.argv[1] if len(sys.argv) > 1 else "p15v-check1"
VIDEO = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data") / "temp" / "p15v-clip.webm"
CAPTION = "P15V session recovery verification - daily tips - by @local_originals"
HASHTAGS = ["fyp", "foryou", "viral", "trending", "dailytips", "howto", "shorts", "tiktok"]

import yaml

CONFIG = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}


def main() -> int:
    result = poster.post_to_tiktok_studio(
        TASK_ID,
        CAPTION,
        VIDEO,
        CONFIG,
        approved=True,
        hashtags=HASHTAGS,
        keep_browser_open=True,
        log=print,
        wait_for_user=None,
        resume=True,
    )
    print("=== RESULT ===")
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

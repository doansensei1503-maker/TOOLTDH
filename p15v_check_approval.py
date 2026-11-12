"""P15V check 8: verify the approval gate in workflow.run_workflow.

The poster is replaced by a stub that returns a real DRAFT_SAVED outcome,
so the approval gate in ``workflow.run_workflow`` is exercised with the real
configuration and the real discovery, download, and scoring code.

No browser is opened, nothing is uploaded, and nothing is published.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

import workflow

CONFIG = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}


class StubPoster:
    """Return a DRAFT_SAVED outcome without touching a browser."""

    calls: list[dict] = []

    def __call__(self, task_id, caption, video_path, config, **kwargs):
        self.calls.append({"task_id": task_id, "caption": caption, **kwargs})
        from poster import PosterResult

        return PosterResult(
            task_id=task_id,
            status="DRAFT_SAVED",
            caption=caption,
            video_path=str(video_path),
            message="Draft saved in TikTok Studio; waiting for human approval before publish.",
            state={
                "status": "DRAFT_SAVED",
                "draft_reference": "https://www.tiktok.com/tiktokstudio/content?tab=draft",
                "mode": config.get("mode"),
            },
        )


def main() -> int:
    stub = StubPoster()
    result = workflow.run_workflow(
        CONFIG,
        Path("data") / "p15v-candidates.json",
        "p15v-approval",
        poster=stub,
        approval=None,
        keep_browser_open=False,
        wait_for_user=None,
    )
    payload = result.to_dict()
    print("=== workflow result ===")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print()
    print("=== acceptance ===")
    print("status == AWAITING_APPROVAL :", payload["status"] == "AWAITING_APPROVAL")
    print("posted_url empty             :", payload["posted_url"] == "")
    print("requires_user_action False   :", payload["requires_user_action"] is False)
    print("poster called once           :", len(stub.calls) == 1)
    print("poster got approved=True     :", bool(stub.calls) and stub.calls[0].get("approved") is True)
    print("auto_post in config          :", CONFIG.get("auto_post"))
    print("history.json exists          :", Path("data/history.json").exists())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

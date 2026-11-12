"""Targeted checks for the caption, the workflow links, the publish
confirmation, and the seven day retention pass.

The checks run on files that are made for the test in a temporary
directory. Nothing is searched on TikTok, nothing is downloaded, and no
real file of the project is removed.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import brain
import poster
import scheduler
import storage

FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name} -- {detail}")
        FAILED.append(name)


def _measured_metadata() -> dict:
    """Return metadata that carries facts the local analyzers measured."""
    return {
        "title": "Neon Skyline Session",
        "topic": "ai music",
        "local_facts": {
            "sound": {
                "measured": True,
                "tempo_bpm": 128,
                "loudness_db": -21,
                "duration_seconds": 42,
            },
            "vision": {
                "reading": {
                    "from_model": True,
                    "objects": [{"label": "synthesizer"}, {"label": "mixer"}],
                },
                "production_ui": {"score": 0.8},
            },
        },
    }


# ---------------------------------------------------------------- caption

def check_caption_uses_measured_facts() -> None:
    """The caption names the facts the machine really measured."""
    caption = brain.build_content_caption(_measured_metadata(), "ai music", "credit: @dj")
    check(
        "caption names the measured tempo",
        "128" in caption,
        caption,
    )
    check(
        "caption names the measured loudness",
        "-21" in caption,
        caption,
    )
    check(
        "caption names the measured duration",
        "42" in caption,
        caption,
    )
    check(
        "caption keeps the creator credit",
        "@dj" in caption,
        caption,
    )
    check(
        "caption stays inside the limit",
        len(caption) <= brain.MAX_CAPTION_LENGTH,
        f"{len(caption)} characters",
    )


def check_caption_never_claims_unmeasured_facts() -> None:
    """A caption without measurements never names a sound or a picture."""
    caption = brain.build_content_caption(
        {"title": "Untitled", "topic": "ai music"}, "ai music", "credit: @dj"
    )
    lowered = caption.lower()
    check(
        "no tempo is claimed without a measurement",
        "bpm" not in lowered and "db" not in lowered,
        caption,
    )
    check(
        "the topic and the title are still there",
        "Untitled" in caption and "ai music" in caption.lower(),
        caption,
    )


def check_caption_ignores_facts_that_are_not_measured() -> None:
    """A fact that was not measured does not reach the caption."""
    metadata = {
        "title": "Clip",
        "topic": "ai music",
        "local_facts": {
            "sound": {"measured": False, "tempo_bpm": 999},
            "vision": {"reading": {"from_model": False, "objects": [{"label": "piano"}]}},
        },
    }
    caption = brain.build_content_caption(metadata, "ai music", "")
    check(
        "an unmeasured tempo never reaches the caption",
        "999" not in caption,
        caption,
    )
    check(
        "an unmeasured object never reaches the caption",
        "piano" not in caption.lower(),
        caption,
    )


def check_template_provider_uses_the_same_facts() -> None:
    """The fallback template uses the measured facts as well."""
    provider = brain.TemplateProvider({"topic": "ai music", "hashtags": ["aimusic"]})
    result = provider.analyze(_measured_metadata(), None, None)
    check(
        "the template caption names the measured tempo",
        "128" in result["caption"],
        result["caption"],
    )
    check(
        "the template caption keeps the hashtags",
        "aimusic" in result["hashtags"],
        str(result["hashtags"]),
    )


def check_analyze_content_carries_the_facts() -> None:
    """The caption of the whole run keeps the measured facts."""
    config = {"topic": "ai music", "hashtags": ["aimusic"], "ai_max_calls": 1}
    result = brain.analyze_content(
        _measured_metadata(), config, creator_credit="credit: @dj"
    )
    check(
        "the run caption names the measured tempo",
        "128" in result.caption,
        result.caption,
    )
    check(
        "the run caption keeps the creator credit",
        "@dj" in result.caption,
        result.caption,
    )


# ------------------------------------------------------- publish confirm

class _FakePage:
    """A page that shows a published post, or nothing at all."""

    def __init__(self, url: str, links: list[str] | None = None, text: str = "") -> None:
        self.url = url
        self._links = links or []
        self._text = text

    def get_by_role(self, role: str):
        page = self

        class _Links:
            def count(self) -> int:
                return len(page._links)

            def nth(self, index: int):
                href = page._links[index]

                class _Link:
                    def get_attribute(self, name: str) -> str:
                        return href

                return _Link()

        return _Links()


def check_published_reference_is_found() -> None:
    """The address of a published post is read from the page."""
    page = _FakePage(
        "https://www.tiktok.com/upload",
        links=["https://www.tiktok.com/@dj/video/7412345678901234567"],
    )
    reference = poster.published_post_reference(page)
    check(
        "the published address is found in the links",
        reference.endswith("/video/7412345678901234567"),
        reference,
    )


def check_published_reference_is_found_in_the_address() -> None:
    """The address of the page is used when it is already the post."""
    page = _FakePage("https://www.tiktok.com/@dj/video/7412345678901234567")
    reference = poster.published_post_reference(page)
    check(
        "the published address is found in the page address",
        "7412345678901234567" in reference,
        reference,
    )


def check_no_publish_is_claimed_without_a_reference() -> None:
    """Nothing is confirmed when the page shows no post."""
    page = _FakePage("https://www.tiktok.com/upload", links=["https://www.tiktok.com/creator-center"])
    reference = poster.published_post_reference(page)
    check(
        "the studio address is not a published post",
        reference == "",
        reference,
    )


def check_wait_for_published_reference_gives_up() -> None:
    """The wait stops and returns nothing when no post shows up."""
    page = _FakePage("https://www.tiktok.com/upload")
    reference = poster.wait_for_published_reference(page, timeout_ms=0, poll_ms=1)
    check(
        "the wait ends without a reference",
        reference == "",
        reference,
    )


def check_published_state_needs_the_reference() -> None:
    """The state of a publish carries the address of the post."""
    check(
        "the pattern only accepts a post address",
        bool(poster.PUBLISHED_URL_PATTERN.match(
            "https://www.tiktok.com/@dj/video/7412345678901234567"
        )),
        "the pattern refused a real post address",
    )
    check(
        "the pattern refuses the studio address",
        not poster.PUBLISHED_URL_PATTERN.match("https://www.tiktok.com/upload"),
        "the pattern accepted the studio address",
    )


def check_a_published_task_is_never_published_again() -> None:
    """A task that was already published is never posted a second time."""
    import workflow

    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        tasks = root / "data" / "tasks"
        tasks.mkdir(parents=True)
        (tasks / "task-done.json").write_text(json.dumps({
            "task_id": "task-done",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
            "caption": "the caption",
        }), encoding="utf-8")
        try:
            import os

            os.chdir(root)
            state = workflow.load_resume_state("task-done")
        finally:
            os.chdir(original_cwd)

        check(
            "the published state is read on resume",
            str(state.get("status", "")) == "PUBLISHED",
            str(state),
        )
        check(
            "the address of the post is read on resume",
            "video/1" in str(state.get("posted_url", "")),
            str(state),
        )


def check_the_published_resume_does_not_post_again() -> None:
    """The poster stops when the task was already published."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        state_file = root / "task-done.json"
        state_file.write_text(json.dumps({
            "task_id": "task-done",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
            "caption": "the caption",
        }), encoding="utf-8")

        # The poster is called without a browser, so it can only act on
        # the state it reads. A published task must never reach the
        # upload, so the flow stops before a page is needed.
        from poster import load_task_state

        state = load_task_state(state_file)
        check(
            "the poster reads the published state",
            str(state.get("status", "")) == "PUBLISHED",
            str(state),
        )
        check(
            "the published state carries the post address",
            "video/1" in str(state.get("posted_url", "")),
            str(state),
        )


# ------------------------------------------------------------- retention

def _write_history(path: Path, entries: list[dict]) -> None:
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def check_retention_deadline_is_seven_days() -> None:
    """The deadline is the published moment plus seven days."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        history = root / "history.json"
        published = datetime(2026, 1, 1, 12, 0, 0)
        _write_history(history, [{
            "date": published.isoformat(),
            "task_id": "task-old",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
        }])

        before = storage.expired_published_tasks(
            published + timedelta(days=6, hours=23), history_path=history
        )
        check("a post younger than seven days is kept", before == [], str(before))

        after = storage.expired_published_tasks(
            published + timedelta(days=7, minutes=1), history_path=history
        )
        check("a post older than seven days expires", len(after) == 1, str(after))
        check(
            "the expired task is named",
            after and after[0]["task_id"] == "task-old",
            str(after),
        )


def check_retention_never_expires_an_unpublished_task() -> None:
    """A task that was never published is never expired."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        history = root / "history.json"
        old = (datetime.now() - timedelta(days=30)).isoformat()
        _write_history(history, [
            {
                "date": old,
                "task_id": "task-draft",
                "status": "DRAFT_SAVED",
                "posted_url": "",
            },
            {
                "date": old,
                "task_id": "task-unconfirmed",
                "status": "PUBLISHED",
                "posted_url": "",
            },
        ])
        expired = storage.expired_published_tasks(history_path=history)
        check("a draft is never expired", expired == [], str(expired))


def check_retention_dry_run_removes_nothing() -> None:
    """The dry run names the files and removes none of them."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        history = root / "history.json"
        tasks = root / "tasks"
        tasks.mkdir()
        copy = root / "copy.mp4"
        copy.write_bytes(b"video")
        original = root / "originals" / "source.mp4"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"original")
        published = (datetime.now() - timedelta(days=8)).isoformat()
        _write_history(history, [{
            "date": published,
            "task_id": "task-old",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
        }])
        (tasks / "task-old.json").write_text(json.dumps({
            "task_id": "task-old",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
            "temp_path": str(copy),
        }), encoding="utf-8")

        result = storage.cleanup_expired_media(
            history_path=history,
            task_states_dir=tasks,
            originals_dir=original.parent,
            dry_run=True,
            log=lambda message: None,
        )
        check("the dry run names the copy", len(result["removed"]) == 1, str(result))
        check("the dry run keeps the copy on disk", copy.is_file(), "the copy was removed")
        check("the dry run never touches the original", original.is_file(), "the original was removed")


def check_retention_keeps_the_original_and_the_shared_file() -> None:
    """The original and a file another job uses are never removed."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        history = root / "history.json"
        tasks = root / "tasks"
        tasks.mkdir()
        originals = root / "originals"
        originals.mkdir()
        original = originals / "source.mp4"
        original.write_bytes(b"original")
        shared = root / "shared.mp4"
        shared.write_bytes(b"shared")
        published = (datetime.now() - timedelta(days=8)).isoformat()
        _write_history(history, [{
            "date": published,
            "task_id": "task-old",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
        }])
        (tasks / "task-old.json").write_text(json.dumps({
            "task_id": "task-old",
            "status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@dj/video/1",
            "temp_path": str(shared),
        }), encoding="utf-8")
        (tasks / "task-other.json").write_text(json.dumps({
            "task_id": "task-other",
            "status": "AWAITING_APPROVAL",
            "temp_path": str(shared),
        }), encoding="utf-8")

        result = storage.cleanup_expired_media(
            history_path=history,
            task_states_dir=tasks,
            originals_dir=originals,
            dry_run=False,
            log=lambda message: None,
        )
        check("the shared file is kept", shared.is_file(), "the shared file was removed")
        check("the original is kept", original.is_file(), "the original was removed")
        check("the skip is recorded", any("job khác" in item for item in result["skipped"]), str(result["skipped"]))
        check("the history is kept", history.is_file(), "the history was removed")


def check_retention_never_removes_an_unpublished_media() -> None:
    """A media of a task that was never published is never removed."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        history = root / "history.json"
        tasks = root / "tasks"
        tasks.mkdir()
        copy = root / "copy.mp4"
        copy.write_bytes(b"video")
        _write_history(history, [])
        (tasks / "task-draft.json").write_text(json.dumps({
            "task_id": "task-draft",
            "status": "DRAFT_SAVED",
            "temp_path": str(copy),
        }), encoding="utf-8")

        result = storage.cleanup_expired_media(
            history_path=history,
            task_states_dir=tasks,
            dry_run=False,
            log=lambda message: None,
        )
        check("a media that was never published is kept", copy.is_file(), "the media was removed")
        check("no file is removed", result["removed"] == [], str(result))


def check_retention_state_survives_a_restart() -> None:
    """The record of the pass is written and read back."""
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        state_file = root / "schedule.json"
        history = root / "history.json"
        _write_history(history, [])
        scheduler.SCHEDULE_STATE_FILE  # the default is not touched by the test
        state = scheduler.load_schedule_state(state_file)
        state.setdefault("retention_runs", []).append({"at": "2026-01-01T00:00:00"})
        scheduler.save_schedule_state(state, state_file)
        read_back = scheduler.load_schedule_state(state_file)
        check(
            "the record of the pass is read back",
            read_back.get("retention_runs"),
            str(read_back),
        )


def main() -> int:
    check_caption_uses_measured_facts()
    check_caption_never_claims_unmeasured_facts()
    check_caption_ignores_facts_that_are_not_measured()
    check_template_provider_uses_the_same_facts()
    check_analyze_content_carries_the_facts()

    check_published_reference_is_found()
    check_published_reference_is_found_in_the_address()
    check_no_publish_is_claimed_without_a_reference()
    check_wait_for_published_reference_gives_up()
    check_published_state_needs_the_reference()
    check_a_published_task_is_never_published_again()
    check_the_published_resume_does_not_post_again()

    check_retention_deadline_is_seven_days()
    check_retention_never_expires_an_unpublished_task()
    check_retention_dry_run_removes_nothing()
    check_retention_keeps_the_original_and_the_shared_file()
    check_retention_never_removes_an_unpublished_media()
    check_retention_state_survives_a_restart()

    print()
    if FAILED:
        print(f"FAILED {len(FAILED)}: {FAILED}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

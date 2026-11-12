"""Project entry point for the content workflow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:  # The review text carries Vietnamese; the Windows console is not UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import yaml

from discover import is_test_data_path

CONFIG_PATH = Path(__file__).with_name("config.yaml")
# P16: production discovery reads only from data/production. Test fixtures
# live in data/test and are refused by a production run.
CANDIDATES_PATH = Path("data") / "production" / "candidates.json"
TEST_CANDIDATES_PATH = Path("data") / "test" / "candidates.json"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load the YAML configuration file."""
    with path.open("r", encoding="utf-8") as config_file:
        return yaml.safe_load(config_file) or {}


def apply_topic(config: dict, topic: str) -> dict:
    """Return a copy of the config with the requested discovery topic applied.

    The topic is the user input that reaches the trending score and the live
    discovery search. It is never inferred from a candidate file.
    """
    updated = dict(config)
    topic = str(topic or "").strip()
    if not topic:
        return updated
    discovery = dict(updated.get("discovery", {}) or {})
    discovery["target_topic"] = topic
    updated["discovery"] = discovery
    return updated


def wait_for_terminal_enter() -> None:
    """Block until the user presses Enter in the terminal."""
    input()


def run_once(
    config: dict,
    task_id: str,
    candidates_path: Path,
    keep_open: bool = True,
    allow_test_data: bool = False,
) -> int:
    """Run the full workflow once and report the outcome.

    With ``keep_open`` the browser is never closed automatically and the run
    waits for the user to press Enter in the terminal after the draft is saved.
    An interrupted run of the same task id resumes at the stage it reached:
    a completed upload is not repeated and an existing draft is not duplicated.
    """
    from workflow import run_workflow, save_run_result

    result = run_workflow(
        config,
        candidates_path,
        task_id,
        keep_browser_open=keep_open,
        wait_for_user=wait_for_terminal_enter if keep_open else None,
        allow_test_data=allow_test_data,
    )
    save_run_result(result, Path("data") / "tasks" / f"{task_id}-workflow.json")
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {"AWAITING_APPROVAL", "PUBLISHED"} else 1


def resume_task(
    config: dict,
    task_id: str,
    candidates_path: Path,
    keep_open: bool = True,
    allow_test_data: bool = False,
) -> int:
    """Resume an interrupted task from its persisted state.

    The Chrome session is reused when it is still usable, a completed upload
    is not repeated, and an existing draft is not duplicated. The browser is
    never closed automatically.
    """
    from workflow import load_resume_state, record_workflow_state, run_workflow

    state = load_resume_state(task_id)
    if not state:
        print(f"RESUME: no persisted state was found for task {task_id}")
        print("Nothing to resume; the task will start from the beginning.")
        return run_once(
            config,
            task_id,
            candidates_path,
            keep_open=keep_open,
            allow_test_data=allow_test_data,
        )

    previous_status = str(state.get("status", "UNKNOWN"))
    print(f"RESUME: task {task_id} was last at {previous_status}")

    if previous_status == "DRAFT_SAVED":
        draft_reference = str(state.get("draft_reference", ""))
        reason = (
            "The draft was already saved and waits for human approval; no upload "
            "and no duplicate draft was created."
        )
        record_workflow_state(task_id, "AWAITING_APPROVAL", reason, state)
        print(f"RESUME: draft already saved at {draft_reference}; waiting for approval.")
        print(json.dumps(state, indent=2, sort_keys=True, default=str))
        return 0

    result = run_workflow(
        config,
        candidates_path,
        task_id,
        keep_browser_open=keep_open,
        wait_for_user=wait_for_terminal_enter if keep_open else None,
        allow_test_data=allow_test_data,
    )
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return 0 if result.status in {"AWAITING_APPROVAL", "PUBLISHED"} else 1


def run_discovery(config: dict, topic: str) -> int:
    """Discover new videos for the topic and write the production candidates file.

    The discovery uses the authorized Chrome session that is already signed in
    and reads the item list the page itself receives. No protection is
    bypassed and no candidate or metric is fabricated. When no valid new
    candidate is found the result is ``NO_CANDIDATES_FOUND``.
    """
    from discovery_live import (
        discover_new_candidates,
        save_production_candidates,
    )

    topic = str(topic or (config.get("discovery", {}) or {}).get("target_topic", "")).strip()
    if not topic:
        print("NO_CANDIDATES_FOUND: no topic was supplied.")
        return 1

    try:
        from poster import read_keyword_search
    except Exception as exc:  # noqa: BLE001
        print(f"NO_CANDIDATES_FOUND: the browser session is unavailable: {exc}")
        return 1

    def _read(keyword: str) -> dict:
        return read_keyword_search(keyword)

    try:
        candidates, blockers = discover_new_candidates(
            config, topic, read_search=_read
        )
    except Exception as exc:  # noqa: BLE001
        print(f"NO_CANDIDATES_FOUND: {exc}")
        return 1

    for blocker in blockers:
        print(f"BLOCKER: {blocker}")

    if not candidates:
        print(
            "NO_CANDIDATES_FOUND: no public video on the TikTok keyword "
            f"search matched the topic {topic!r}."
        )
        save_production_candidates([], topic=topic, blockers=blockers)
        return 1

    path = save_production_candidates(candidates, topic=topic, blockers=blockers)
    print(f"DISCOVERED: {len(candidates)} real candidate(s) written to {path}")
    for candidate in candidates:
        print(
            f"  {candidate.source_url}  views={candidate.views} "
            f"likes={candidate.likes} comments={candidate.comments} "
            f"shares={candidate.shares} duration={candidate.duration_seconds:.1f}s"
        )
        if candidate.missing_metrics:
            print(f"      unknown metrics: {', '.join(candidate.missing_metrics)}")
    return 0


def run_review(config: dict, topic: str, task_id: str) -> int:
    """Discover the real candidates and write the review list for the user.

    Nothing is downloaded and TikTok Studio is not opened. The user reviews
    the candidates with their real metrics and then chooses one with
    ``--select``.
    """
    from discovery_live import discover_new_candidates, save_production_candidates
    from discover import score_all_trending
    from review_stage import format_review, write_review

    topic = str(topic or (config.get("discovery", {}) or {}).get("target_topic", "")).strip()
    if not topic:
        print("NO_CANDIDATES_FOUND: no topic was supplied.")
        return 1

    try:
        from poster import read_keyword_search
    except Exception as exc:  # noqa: BLE001
        print(f"NO_CANDIDATES_FOUND: the browser session is unavailable: {exc}")
        return 1

    def _read(keyword: str) -> dict:
        return read_keyword_search(keyword)

    try:
        candidates, blockers = discover_new_candidates(config, topic, read_search=_read)
    except Exception as exc:  # noqa: BLE001
        print(f"NO_CANDIDATES_FOUND: {exc}")
        return 1

    for blocker in blockers:
        print(f"BLOCKER: {blocker}")

    save_production_candidates(candidates, topic=topic, blockers=blockers)
    scores = score_all_trending(candidates, config) if candidates else []
    path = write_review(task_id, candidates, scores, topic=topic, blockers=blockers)
    print(format_review(load_review_payload(task_id)))
    print(f"\nReview written to {path}")
    print(f"Choose one with: py -3.13 main.py --review-select <number> --task-id {task_id}")
    if not candidates:
        return 1
    return 0


def load_review_payload(task_id: str) -> dict:
    """Load the review record for a task."""
    from review_stage import load_review

    return load_review(task_id)


def select_for_review(task_id: str, index: int) -> int:
    """Record the user's video choice for the review stage."""
    from review_stage import select_candidate

    candidate = select_candidate(task_id, index)
    if candidate is None:
        print(f"REJECTED: no candidate with index {index} was found in the review for {task_id}.")
        return 1
    print(f"SELECTED: {candidate.source_url}")
    print(
        f"  views={candidate.views} likes={candidate.likes} comments={candidate.comments} "
        f"shares={candidate.shares} duration={candidate.duration_seconds:.1f}s"
    )
    print(f"  title={candidate.title[:100]!r}")
    print(f"Process it with: py -3.13 main.py --run --task-id {task_id}")
    return 0


def main() -> None:
    """Load configuration, support a dry run, and run the workflow."""
    parser = argparse.ArgumentParser(description="Content workflow automation")
    parser.add_argument("--dry-run", action="store_true", help="validate startup and exit")
    parser.add_argument("--cleanup", action="store_true", help="clean temporary task files and exit")
    parser.add_argument("--run", action="store_true", help="run the full workflow once")
    parser.add_argument("--task-id", default="p7-run", help="task identifier for this run")
    parser.add_argument(
        "--topic",
        default="",
        help="topic to discover new videos for, for example 'ai music'",
    )
    parser.add_argument(
        "--test-data",
        action="store_true",
        help="allow test fixtures to be used; never combine with a production run",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="run live discovery for the topic and write the production candidates file",
    )
    parser.add_argument(
        "--review",
        action="store_true",
        help="discover the real candidates and show the review list for the user to choose from",
    )
    parser.add_argument(
        "--review-select",
        type=int,
        default=0,
        metavar="N",
        help="choose candidate N from the review list of the task",
    )
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="start the APScheduler job that runs the discovery and review stage daily",
    )
    parser.add_argument(
        "--schedule-now",
        action="store_true",
        help="run one scheduled discovery and review pass now and exit",
    )
    parser.add_argument(
        "--keep-open",
        dest="keep_open",
        action="store_true",
        default=True,
        help="keep the browser open after the draft is saved (default: on)",
    )
    parser.add_argument(
        "--no-keep-open",
        dest="keep_open",
        action="store_false",
        help="allow the browser to be closed when the run ends",
    )
    parser.add_argument(
        "--candidates",
        default=str(CANDIDATES_PATH),
        help="path to the discovered candidates JSON file",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume the given task id from its persisted state without repeating a finished stage",
    )
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="start the dashboard web interface on the loopback interface",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=8777,
        help="port the dashboard listens on",
    )
    parser.add_argument(
        "--dashboard-open",
        action="store_true",
        help="open the dashboard in the default browser when it starts",
    )
    args = parser.parse_args()

    config = load_config()
    config = apply_topic(config, args.topic)

    # The dashboard owns its own server, so it starts before the workflow.
    if args.dashboard:
        from dashboard_server import serve

        server = serve("127.0.0.1", args.dashboard_port, open_browser=args.dashboard_open)
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping the dashboard.")
            server.shutdown()
            server.server_close()
        raise SystemExit(0)

    # The review selection only reads the review record, so it runs before
    # the candidate path check.
    if args.review_select:
        raise SystemExit(select_for_review(args.task_id, args.review_select))

    # P16: a production run may never read test data.
    candidates_path = Path(args.candidates)
    if args.test_data:
        if not is_test_data_path(candidates_path):
            print(
                "TEST MODE: --test-data was requested but the candidate file is not "
                "test data. Use data/test/candidates.json."
            )
            raise SystemExit(2)
        candidates_path = candidates_path
    else:
        if is_test_data_path(candidates_path):
            print(
                f"REJECTED: a production run may not read test data from {candidates_path}. "
                "Use --test-data for a test run."
            )
            raise SystemExit(2)
        production_root = Path("data") / "production"
        resolved = candidates_path.resolve()
        if production_root.resolve() != resolved and production_root.resolve() not in resolved.parents:
            print(
                f"REJECTED: production discovery may only read from {production_root}. "
                "Use --test-data for a test run."
            )
            raise SystemExit(2)

    if args.cleanup:
        from storage import cleanup_task

        cleanup = config.get("cleanup", {})
        result = cleanup_task(
            keep_screenshots=int(cleanup.get("keep_error_screenshots", 0)),
        )
        print(f"cleanup complete: {len(result['temp'])} temp files removed")
        return
    if args.discover:
        raise SystemExit(run_discovery(config, args.topic))
    if args.review:
        raise SystemExit(run_review(config, args.topic, args.task_id))
    if args.schedule_now:
        from scheduler import ScheduleSettings, run_scheduled_task

        settings = ScheduleSettings.from_config(config)
        status = run_scheduled_task(config, settings)
        raise SystemExit(0 if status != "FAILED" else 1)
    if args.schedule:
        from scheduler import start_scheduler

        scheduler = start_scheduler(config)
        if scheduler is None:
            raise SystemExit(0)
        try:
            import time

            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            scheduler.shutdown(wait=False)
        raise SystemExit(0)
    if args.resume:
        raise SystemExit(
            resume_task(
                config,
                args.task_id,
                candidates_path,
                keep_open=args.keep_open,
                allow_test_data=args.test_data,
            )
        )
    if args.run:
        raise SystemExit(
            run_once(
                config,
                args.task_id,
                candidates_path,
                keep_open=args.keep_open,
                allow_test_data=args.test_data,
            )
        )
    if args.dry_run:
        print("ready")
        return

    print("Phase 1 logic ready; live workflow verification remains pending.")


if __name__ == "__main__":
    main()

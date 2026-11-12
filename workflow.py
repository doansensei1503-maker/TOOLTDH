"""P7 full auto flow: discover, download, score, draft, approve, publish, history.

One video is processed per run. Every stage fails closed. The flow never
publishes without explicit human approval, never removes a watermark to hide
the origin of content, and never bypasses a CAPTCHA, re-login, or security
check.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from discover import (
    DiscoveredVideo,
    DiscoveryError,
    SourceNotAllowedError,
    TestDataRejectedError,
    TrendingScore,
    build_caption,
    build_history_metadata,
    creator_credit,
    download_to_temp,
    load_candidates,
    resolve_download_link,
    score_all_trending,
    score_trending,
    select_trending,
    validate_source_permitted,
)
from brain import analyze_content
from history import PublishHistory
from ingest import IngestError, ingest_video
from library import ContentLibrary
from poster import post_to_tiktok_studio
from reviewer import review_with_revisions
from storage import (
    ORIGINALS_DIR,
    cleanup_task,
    ensure_directories,
    sha256_file,
)

PLATFORM = "tiktok"
PASSING_SCORE = 70
DEFAULT_DURATION_SECONDS = 42.0
HTTP_TIMEOUT_SECONDS = 60
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36"
)
VERIFIED_URL_PATTERN = re.compile(r"https://[^\s]+/video/\d+")


class WorkflowError(RuntimeError):
    """Raised when the workflow cannot continue safely."""


def record_workflow_state(
    task_id: str,
    status: str,
    reason: str,
    extra: dict[str, Any] | None = None,
) -> Path:
    """Persist the workflow stage so an interrupted run can be resumed.

    The file is written atomically so a crash never leaves a half written
    state file, and the caption, the video paths, the metadata, and the draft
    reference are kept so nothing is lost between runs.
    """
    tasks_dir = Path("data") / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / f"{task_id}-workflow.json"
    payload: dict[str, Any] = {
        "task_id": task_id,
        "status": status,
        "reason": reason,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if extra:
        payload.update(extra)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    temporary_path.replace(path)
    return path


def load_resume_state(task_id: str) -> dict[str, Any]:
    """Load the persisted state of a previous run for this task.

    The poster state file and the workflow state file are both consulted so
    an interrupted run can be continued at the stage it reached. Nothing is
    deleted and no stage is repeated.
    """
    tasks_dir = Path("data") / "tasks"
    merged: dict[str, Any] = {}
    for name in (f"{task_id}-workflow.json", f"{task_id}.json"):
        path = tasks_dir / name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        for key, value in payload.items():
            if value not in (None, "", [], {}):
                merged.setdefault(key, value)
    return merged


@dataclass
class WorkflowResult:
    """Outcome of one full workflow run."""

    status: str
    reason: str = ""
    task_id: str = ""
    source_url: str = ""
    creator: str = ""
    views: int = 0
    likes: int = 0
    score: int = 0
    caption: str = ""
    hashtags: list[str] = field(default_factory=list)
    sha256: str = ""
    temp_path: str = ""
    original_path: str = ""
    draft_reference: str = ""
    posted_url: str = ""
    requires_user_action: bool = False
    provider: str = ""
    steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the run outcome."""
        return {
            "status": self.status,
            "reason": self.reason,
            "task_id": self.task_id,
            "source_url": self.source_url,
            "creator": self.creator,
            "views": self.views,
            "likes": self.likes,
            "score": self.score,
            "caption": self.caption,
            "hashtags": self.hashtags,
            "sha256": self.sha256,
            "temp_path": self.temp_path,
            "original_path": self.original_path,
            "draft_reference": self.draft_reference,
            "posted_url": self.posted_url,
            "requires_user_action": self.requires_user_action,
            "provider": self.provider,
            "steps": self.steps,
        }


def http_get_text(url: str) -> str:
    """Fetch a page as text for download-link resolution."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def http_get_bytes(url: str) -> bytes:
    """Fetch a resolved media link as bytes."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read()


def discover_candidates(
    config: dict[str, Any],
    candidates_path: Path,
    *,
    log: Callable[[str], None] = print,
    allow_test_data: bool = False,
) -> tuple[list[DiscoveredVideo], DiscoveredVideo | None, str, list[TrendingScore]]:
    """Return allowlisted candidates, one randomly chosen accepted pick, and the scores.

    Candidates outside the allowlist are rejected before any download. Every
    candidate is scored with the trending formula and the state, decision, and
    reason are logged for each one.

    P16: a production run refuses test data. When no valid candidate remains
    the reason is ``NO_CANDIDATES_FOUND`` so an old test video is never reused.
    """
    try:
        candidates = load_candidates(candidates_path, allow_test_data=allow_test_data)
    except TestDataRejectedError as exc:
        log(f"state: test data -> decision: REJECT | reason: {exc}")
        return [], None, "NO_CANDIDATES_FOUND", []
    permitted: list[DiscoveredVideo] = []
    rejected: list[str] = []
    for candidate in candidates:
        try:
            validate_source_permitted(candidate.source_url, config)
        except (DiscoveryError, SourceNotAllowedError) as exc:
            rejected.append(str(exc))
            log(f"state: outside allowlist -> decision: REJECT | reason: {exc}")
            continue
        permitted.append(candidate)
    if not permitted:
        reason = "; ".join(rejected) if rejected else "NO_CANDIDATES_FOUND"
        if not rejected:
            log("state: no candidates -> decision: REJECT | reason: NO_CANDIDATES_FOUND")
        return candidates, None, reason, []

    scored = score_all_trending(permitted, config)
    for item in scored:
        log(f"state: {item.video.creator} -> decision: {item.decision} | reason: {item.reason}")

    accepted = [item.video for item in scored if item.decision == "ACCEPT"]
    if not accepted:
        held = [item for item in scored if item.decision == "HOLD"]
        if held:
            reason = held[0].reason
        else:
            reason = "No allowlisted candidate met the trending thresholds"
        return candidates, None, reason, scored

    # Pick one of the accepted candidates at random so the same video is not
    # always chosen.
    chosen = random.choice(accepted)
    log(
        f"state: {len(accepted)} accepted candidate(s) -> decision: PICK | "
        f"reason: chose {chosen.source_url} at random"
    )
    return candidates, chosen, "", scored


def _selected_from_review(task_id: str) -> DiscoveredVideo | None:
    """Return the candidate the user chose in the review stage.

    The choice is explicit and recorded, so the workflow processes exactly
    the video the user picked.
    """
    from review_stage import load_review, select_candidate

    payload = load_review(task_id)
    if not payload or payload.get("status") != "SELECTED":
        return None
    index = int(payload.get("selected_index", 0) or 0)
    if index <= 0:
        return None
    return select_candidate(task_id, index)


def _local_caption_facts(
    media_path: Path,
    metadata: dict[str, Any],
    selected: DiscoveredVideo | None = None,
) -> dict[str, Any]:
    """Return the facts the local analyzers really measured about the media.

    The sound and the picture are measured on this machine, on the file
    that was already downloaded. Nothing is fetched and no paid service
    is called. When a fact was not measured, it is simply not in the
    result, so a caption never names something the machine did not read.
    """
    facts: dict[str, Any] = {}

    # The sound, when the machine can really decode the track.
    try:
        from local_analyzer import measure_audio

        audio = measure_audio(str(media_path)) if media_path else None
    except Exception:
        audio = None
    if isinstance(audio, dict) and audio.get("decoded"):
        sound: dict[str, Any] = {"measured": True}
        for key in ("tempo_bpm", "tempo_confidence", "mean_volume_db", "duration"):
            if audio.get(key) is not None:
                sound[key] = audio.get(key)
        if sound.get("duration") is not None:
            sound["duration_seconds"] = audio.get("duration")
        if sound.get("mean_volume_db") is not None:
            sound["loudness_db"] = audio.get("mean_volume_db")
        facts["sound"] = sound

    # The picture, when the frames of the discovery are still on the
    # machine. They are read from the cache of the discovery, so the
    # video is never read a second time.
    try:
        from candidate_analysis import _cache_key, _decode_frames, load_cache

        if selected is not None:
            cache = load_cache()
            entry = cache.get(_cache_key(selected)) or {}
            frames = _decode_frames(entry.get("frames") or []) if isinstance(entry, dict) else []
            if frames:
                from local_vision import analyze_vision

                vision = analyze_vision(frames).to_dict()
                if vision.get("reading", {}).get("from_model") or vision.get("production_ui"):
                    facts["vision"] = vision
    except Exception:
        pass

    return facts


def _resolve_candidate_media_link(
    selected: DiscoveredVideo,
    fetch_text: Callable[[str], str],
) -> str:
    """Return the media link for the allowlisted source URL.

    P16: a candidate-supplied ``download_url`` is only honoured when it is
    served by the platform's own media host. A fixture that points at a local
    test file or at an unrelated host is refused, so the media always comes
    from the platform for the source that passed the allowlist and rights
    check.
    """
    from eligibility import check_media_url, is_platform_media_url

    source_host = (urlparse(selected.source_url).hostname or "").lower()
    supplied = str(selected.download_url or "").strip()
    if supplied:
        url_ok, supplied_host, reason = check_media_url(supplied)
        if url_ok:
            return supplied
        if supplied_host and supplied_host != source_host:
            # A different host is refused outright rather than silently
            # replaced, so the reason is visible in the run log.
            raise DiscoveryError(
                "Rejected: the candidate download URL is not usable: "
                f"{reason or 'the media URL failed the platform host check'}. "
                f"Candidate URL: {supplied}"
            )
        raise DiscoveryError(
            "Rejected: the candidate download URL is not usable: "
            f"{reason or 'unknown reason'}. Candidate URL: {supplied}"
        )
    # The platform's own signed media URL is preferred. When the candidate
    # has none the link is resolved from the source page.
    if is_platform_media_url(selected.source_url):
        return selected.source_url
    return resolve_download_link(selected.source_url, fetch_text)


def ensure_original(temp_path: Path, task_id: str) -> Path:
    """Copy the downloaded file into the permanent originals directory."""
    ORIGINALS_DIR.mkdir(parents=True, exist_ok=True)
    destination = ORIGINALS_DIR / f"{task_id}{temp_path.suffix or '.mp4'}"
    if temp_path.resolve() != destination.resolve():
        destination.write_bytes(temp_path.read_bytes())
    return destination


def wait_for_approval(
    task_id: str,
    caption: str,
    history: PublishHistory,
    source_url: str,
    metadata: dict[str, Any],
    *,
    approval: Callable[[], bool],
    published_url: Callable[[], str],
    poll_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    timeout_seconds: float = 3600.0,
) -> str:
    """Wait for explicit human approval before recording a publish.

    No publish is recorded while approval is absent. The draft stays saved and
    the workflow keeps waiting until the user approves and a verified posted
    URL is available.
    """
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if approval():
            posted_url = published_url()
            if not posted_url or not VERIFIED_URL_PATTERN.match(posted_url):
                sleep(poll_seconds)
                continue
            history.record_publish(
                task_id=task_id,
                platform=PLATFORM,
                source_url=source_url,
                posted_url=posted_url,
                caption=caption,
                status="PUBLISHED",
                metadata=metadata,
            )
            return posted_url
        sleep(poll_seconds)
    raise WorkflowError("Approval was not granted within the allowed time")


def run_workflow(
    config: dict[str, Any],
    candidates_path: Path,
    task_id: str,
    *,
    approval: Callable[[], bool] | None = None,
    fetch_text: Callable[[str], str] = http_get_text,
    fetch_bytes: Callable[[str], bytes] = http_get_bytes,
    poster: Callable[..., Any] = post_to_tiktok_studio,
    published_url: Callable[[], str] | None = None,
    log: Callable[[str], None] = print,
    keep_browser_open: bool = True,
    wait_for_user: Callable[[], None] | None = None,
    allow_test_data: bool = False,
) -> WorkflowResult:
    """Run the full flow for exactly one discovered video.

    The browser is never closed automatically. When ``keep_browser_open`` is
    true the run waits for the user in the terminal after the draft is saved.
    """
    ensure_directories()
    steps: list[str] = []
    library = ContentLibrary()
    history = PublishHistory()

    # P15 resume: an interrupted run continues at the stage it reached. The
    # persisted task state is read first so a completed download, upload, or
    # saved draft is never repeated and no duplicate draft is created.
    resume_state = load_resume_state(task_id)
    if resume_state:
        log(
            f"state: RESUMING_TASK -> decision: CONTINUE | reason: "
            f"the previous run reached {resume_state.get('status', 'UNKNOWN')}"
        )
        steps.append("resume")
        resume_status = str(resume_state.get("status", "")).strip().upper()
        if resume_status == "PUBLISHED":
            # The post already went out. The run never publishes a second
            # time, so a retry or a resume cannot double post.
            posted = str(resume_state.get("posted_url", "") or "").strip()
            reason = (
                "The task was already published, so nothing was posted again. "
                f"The post that is live: {posted or 'the address was not recorded'}"
            )
            log(f"state: PUBLISHED -> decision: SKIP publish | reason: {reason}")
            return WorkflowResult(
                status="PUBLISHED",
                reason=reason,
                task_id=task_id,
                source_url=str(resume_state.get("source_url", "")),
                creator=str(resume_state.get("creator", "")),
                caption=str(resume_state.get("caption", "")),
                hashtags=list(resume_state.get("hashtags", []) or []),
                sha256=str(resume_state.get("sha256", "")),
                temp_path=str(resume_state.get("temp_path", "")),
                original_path=str(resume_state.get("original_path", "")),
                draft_reference=str(resume_state.get("draft_reference", "")),
                posted_url=posted,
                provider=str(resume_state.get("provider", "")),
                steps=steps,
            )
        if resume_status == "DRAFT_SAVED":
            draft_reference = str(resume_state.get("draft_reference", ""))
            reason = (
                "The draft was already saved in an earlier run and waits for human "
                "approval; no upload and no duplicate draft was created."
            )
            log(f"state: DRAFT_SAVED -> decision: WAIT for approval | reason: {reason}")
            return WorkflowResult(
                status="AWAITING_APPROVAL",
                reason=reason,
                task_id=task_id,
                source_url=str(resume_state.get("source_url", "")),
                creator=str(resume_state.get("creator", "")),
                caption=str(resume_state.get("caption", "")),
                hashtags=list(resume_state.get("hashtags", []) or []),
                sha256=str(resume_state.get("sha256", "")),
                temp_path=str(resume_state.get("temp_path", "")),
                original_path=str(resume_state.get("original_path", "")),
                draft_reference=draft_reference,
                provider=str(resume_state.get("provider", "")),
                steps=steps,
            )

    # 1. Discover from the allowlist only, score with the trending formula,
    #    and pick one accepted candidate at random.
    candidates, selected, reject_reason, trending_scores = discover_candidates(
        config, candidates_path, log=log, allow_test_data=allow_test_data
    )
    steps.append("discover")

    # The review choice wins over the automatic pick. The user has seen the
    # real candidates and their real metrics and chose this one. A chosen
    # video is used even when the automatic thresholds did not accept it,
    # because the decision was made by the user.
    reviewed = _selected_from_review(task_id)
    if reviewed is not None and reviewed.source_url:
        if selected is None:
            log(
                f"state: review -> decision: USE selected | reason: "
                f"the user chose {reviewed.source_url} from the review list"
            )
        elif reviewed.source_url != selected.source_url:
            log(
                f"state: review -> decision: USE selected | reason: "
                f"the user chose {reviewed.source_url} instead of {selected.source_url}"
            )
        selected = reviewed
        steps.append("review")

    if selected is None:
        log(f"REJECTED: {reject_reason}")
        return WorkflowResult(status="REJECTED", reason=reject_reason, steps=steps)
    log(
        f"discovered: {selected.creator} views={selected.views} "
        f"likes={selected.likes} comments={selected.comments} "
        f"shares={selected.shares} url={selected.source_url}"
    )

    try:
        validate_source_permitted(selected.source_url, config)
    except DiscoveryError as exc:
        log(f"REJECTED: {exc}")
        return WorkflowResult(status="REJECTED", reason=str(exc), steps=steps)

    # 2. Check the download eligibility and download to temp.
    #    The eligibility check is a technical check. The reuse permission
    #    comes only from the rights allowlist and is never inferred from it.
    from eligibility import check_candidate

    reuse_reason = ""
    reuse_permitted = False
    try:
        permitted = validate_source_permitted(selected.source_url, config)
        reuse_permitted = True
        reuse_reason = (
            f"allowlisted source {permitted.get('name', selected.source_name)}; "
            f"rights verified with a permit date of {permitted.get('permit_date', 'unknown')}"
        )
    except DiscoveryError as exc:
        log(f"REJECTED: {exc}")
        return WorkflowResult(status="REJECTED", reason=str(exc), steps=steps)

    try:
        link = _resolve_candidate_media_link(selected, fetch_text)
    except (DiscoveryError, OSError) as exc:
        log(f"FAILED: {exc}")
        return WorkflowResult(
            status="FAILED",
            reason=str(exc),
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            steps=steps,
        )

    eligibility = check_candidate(
        selected,
        media_url=link,
        reuse_permitted=reuse_permitted,
        reuse_reason=reuse_reason,
    )
    if not eligibility.eligible:
        reason = "Rejected: the video is not eligible for download: " + "; ".join(
            eligibility.reasons
        )
        log(f"REJECTED: {reason}")
        return WorkflowResult(
            status="REJECTED",
            reason=reason,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            steps=steps,
        )
    log(
        f"eligible for download: {selected.source_url} host={eligibility.media_host} "
        f"(reuse {reuse_reason})"
    )

    # A video that was already downloaded and processed is not downloaded
    # again, so a repeated run never re-posts the same content.
    existing = library.find_by_source(selected.source_url)
    if existing is not None:
        reason = (
            "The video was already processed in an earlier run "
            f"(task_id: {existing.get('task_id', 'unknown')}, sha256: "
            f"{str(existing.get('sha256', ''))[:16]}); it was not downloaded again."
        )
        log(f"REJECTED: {reason}")
        return WorkflowResult(
            status="REJECTED",
            reason=reason,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            steps=steps,
        )

    try:
        temp_path = download_to_temp(link, task_id, fetch_bytes, referer=selected.source_url)
    except (DiscoveryError, OSError) as exc:
        log(f"FAILED: {exc}")
        return WorkflowResult(
            status="FAILED",
            reason=str(exc),
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            steps=steps,
        )
    steps.append("download")
    # 3. Ingest, hash, and block duplicates.
    try:
        metadata = ingest_video(
            str(temp_path),
            task_id,
            rights_verified=True,
            permission=True,
            rights_evidence=(
                f"Allowlisted discovery source {selected.source_name or selected.source_url}; "
                "creator permission recorded in the discovery allowlist"
            ),
            library=library,
            discovery_config=config,
        )
    except IngestError as exc:
        log(f"REJECTED: {exc}")
        return WorkflowResult(
            status="REJECTED",
            reason=str(exc),
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            steps=steps,
        )
    metadata["title"] = selected.title or metadata.get("title") or task_id
    metadata["topic"] = selected.topic or metadata.get("topic", "")
    # P16: the measured duration is the only duration that is trusted. The
    # declared duration from a candidate record is never used as the value.
    measured_duration = metadata.get("duration_seconds")
    if not isinstance(measured_duration, (int, float)) or measured_duration <= 0:
        reason = "Rejected: the measured media duration is unknown"
        log(f"REJECTED: {reason}")
        return WorkflowResult(
            status="REJECTED",
            reason=reason,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            steps=steps,
        )
    metadata["duration_seconds"] = float(measured_duration)
    metadata["duration_source"] = "measured"
    digest = metadata["sha256"]
    log(
        f"downloaded and hashed: {temp_path} sha256={digest[:16]} "
        f"duration={measured_duration:.2f}s format={metadata.get('format', '')}"
    )

    # 4. Analyse the video content and write a caption that matches it.
    # The facts that the local analyzers really measured are attached to
    # the metadata, so the caption describes the video that was measured
    # and not a generic template. Nothing is fetched to get them, and no
    # paid service is called.
    credit = creator_credit(selected)
    local_facts = _local_caption_facts(Path(temp_path), metadata, selected)
    if local_facts:
        metadata["local_facts"] = local_facts
        measured = ", ".join(
            str(part)
            for part in (
                ", ".join(
                    f"{key} {value}"
                    for key, value in (local_facts.get("sound") or {}).items()
                    if key not in ("measured",)
                ),
                f"hình đọc được bởi mô hình"
                if (local_facts.get("vision") or {}).get("reading", {}).get("from_model")
                else "",
            )
            if part
        )
        log(f"local facts: {measured or 'có đặc trưng đo được'}")
    analysis = analyze_content(metadata, config, creator_credit=credit)
    log(
        f"state: analysed {selected.creator} -> decision: USE content caption | "
        f"reason: topic={analysis.title!r} provider={analysis.provider}"
    )
    result = review_with_revisions(task_id, metadata, config)
    steps.append("score")
    log(f"score: {result.score} status={result.status} provider={result.provider}")
    if result.status == "REJECTED" or result.score < PASSING_SCORE:
        reason = result.score_reason or f"Score {result.score} is below the minimum {PASSING_SCORE}"
        log(f"REJECTED: {reason}")
        return WorkflowResult(
            status="REJECTED",
            reason=reason,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            views=selected.views,
            likes=selected.likes,
            score=result.score,
            provider=result.provider,
            sha256=digest,
            temp_path=str(temp_path),
            steps=steps,
        )

    # 5. Build the caption from the content analysis with creator credit,
    #    keeping the origin visible and no watermark removed.
    caption = build_caption(selected, analysis.caption or result.caption)
    hashtags = list(analysis.hashtags or result.hashtags)
    log(f"caption: {caption}")

    # 6. Save the draft in TikTok Studio. Never publish without approval.
    poster_kwargs: dict[str, Any] = {
        "approved": True,
        "hashtags": hashtags,
        "keep_browser_open": keep_browser_open,
        "log": log,
        "wait_for_user": wait_for_user if keep_browser_open else None,
        "resume": True,
    }
    try:
        poster_outcome = poster(task_id, caption, str(temp_path), config, **poster_kwargs)
    except TypeError as exc:
        # A caller supplied poster that does not accept the P15 resume flag is
        # still called; the resume then happens through the persisted state.
        if "resume" not in str(exc):
            raise
        poster_kwargs.pop("resume")
        poster_outcome = poster(task_id, caption, str(temp_path), config, **poster_kwargs)
    steps.append("draft")
    if poster_outcome.status == "BLOCKED":
        log(f"BLOCKED: {poster_outcome.message}")
        return WorkflowResult(
            status="BLOCKED",
            reason=poster_outcome.message,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            views=selected.views,
            likes=selected.likes,
            score=result.score,
            caption=caption,
            hashtags=hashtags,
            sha256=digest,
            temp_path=str(temp_path),
            requires_user_action=True,
            provider=result.provider,
            steps=steps,
        )
    if poster_outcome.status != "DRAFT_SAVED":
        log(f"FAILED: {poster_outcome.message}")
        return WorkflowResult(
            status="FAILED",
            reason=poster_outcome.message,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            views=selected.views,
            likes=selected.likes,
            score=result.score,
            caption=caption,
            hashtags=hashtags,
            sha256=digest,
            temp_path=str(temp_path),
            provider=result.provider,
            steps=steps,
        )

    draft_reference = str(poster_outcome.state.get("draft_reference", ""))
    log(f"draft saved: {draft_reference}")

    # 7. Wait for explicit human approval before any publish. The publish
    #    path only runs when auto_post is enabled in the config, otherwise the
    #    draft stays saved and the run ends at AWAITING_APPROVAL.
    auto_post = bool(config.get("auto_post", False))
    if approval is None or not auto_post:
        reason = (
            "The draft is saved and waits for human approval before publish."
            if approval is None
            else "auto_post is not enabled, so the draft stays saved for manual review."
        )
        log(f"state: draft saved -> decision: WAIT for approval | reason: {reason}")
        record_workflow_state(
            task_id,
            "AWAITING_APPROVAL",
            reason,
            {
                "source_url": selected.source_url,
                "creator": selected.creator,
                "caption": caption,
                "hashtags": hashtags,
                "sha256": digest,
                "temp_path": str(temp_path),
                "draft_reference": draft_reference,
                "provider": result.provider,
            },
        )
        return WorkflowResult(
            status="AWAITING_APPROVAL",
            reason=reason,
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            views=selected.views,
            likes=selected.likes,
            score=result.score,
            caption=caption,
            hashtags=hashtags,
            sha256=digest,
            temp_path=str(temp_path),
            draft_reference=draft_reference,
            provider=result.provider,
            steps=steps,
        )

    posted_url = ""
    try:
        posted_url = wait_for_approval(
            task_id,
            caption,
            history,
            selected.source_url,
            build_history_metadata(selected, result.score),
            approval=approval,
            published_url=published_url or (lambda: ""),
        )
    except WorkflowError as exc:
        log(f"BLOCKED: {exc}")
        return WorkflowResult(
            status="BLOCKED",
            reason=str(exc),
            task_id=task_id,
            source_url=selected.source_url,
            creator=selected.creator,
            views=selected.views,
            likes=selected.likes,
            score=result.score,
            caption=caption,
            hashtags=hashtags,
            sha256=digest,
            temp_path=str(temp_path),
            draft_reference=draft_reference,
            requires_user_action=True,
            provider=result.provider,
            steps=steps,
        )
    steps.append("publish")

    # 8. After a verified publish, clean temp and keep the original.
    original_path = ensure_original(temp_path, task_id)
    cleanup_result = cleanup_task(temp_path)
    log(f"published and cleaned temp: {len(cleanup_result['temp'])} file(s) removed")

    # The confirmed publish is written to the state of the task, so a
    # later run never posts the same video again and the retention pass
    # can find the task and its post address seven days later.
    record_workflow_state(
        task_id,
        "PUBLISHED",
        f"Published and confirmed: {posted_url}",
        {
            "source_url": selected.source_url,
            "creator": selected.creator,
            "caption": caption,
            "hashtags": hashtags,
            "sha256": digest,
            "temp_path": str(temp_path),
            "original_path": str(original_path),
            "draft_reference": draft_reference,
            "posted_url": posted_url,
            "provider": result.provider,
        },
    )
    return WorkflowResult(
        status="PUBLISHED",
        task_id=task_id,
        source_url=selected.source_url,
        creator=selected.creator,
        views=selected.views,
        likes=selected.likes,
        score=result.score,
        caption=caption,
        hashtags=hashtags,
        sha256=digest,
        temp_path=str(temp_path),
        original_path=str(original_path),
        draft_reference=draft_reference,
        posted_url=posted_url,
        provider=result.provider,
        steps=steps,
    )


def save_run_result(result: WorkflowResult, path: Path) -> Path:
    """Persist the workflow outcome for auditing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.to_dict()
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    temporary_path.replace(path)
    return path


__all__ = [
    "PLATFORM",
    "PASSING_SCORE",
    "WorkflowError",
    "WorkflowResult",
    "discover_candidates",
    "ensure_original",
    "http_get_bytes",
    "http_get_text",
    "load_resume_state",
    "record_workflow_state",
    "run_workflow",
    "save_run_result",
    "wait_for_approval",
]

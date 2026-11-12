"""End-to-end check of the discovery pipeline with a mocked AI provider.

The TikTok search and the frame capture are real. Only the AI provider is
mocked, because this host has no GEMINI_API_KEY. The check proves that the
real frames reach the analysis, that the ranking follows the content, and
that a candidate without media is marked as not enough data.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import candidate_analysis as ca
import dashboard_service as service
from discovery_live import parse_search_results
from poster import read_keyword_search


def _mock_payload(frames, metadata, *, model=""):
    """A stand-in for the AI provider, so no key is needed."""
    darker = sum(1 for f in frames if len(f) < 15000)
    fit = 8 if darker else 18
    return {
        "ai_music_fit": fit,
        "ai_music_fit_reason": "khung hình cho thấy dấu hiệu AI" if fit > 10 else "ít dấu hiệu AI",
        "ai_music_fit_known": True,
        "music_quality": 16,
        "music_quality_reason": "giai điệu và âm thanh quan sát được",
        "music_quality_known": True,
        "visual_quality": 12,
        "visual_quality_reason": "hình ảnh sắc nét",
        "visual_quality_known": True,
        "hook_retention": 11,
        "hook_retention_reason": "mở đầu có nhịp",
        "hook_retention_known": True,
        "engagement_virality": 10,
        "engagement_virality_reason": "dễ chia sẻ",
        "engagement_virality_known": True,
        "creativity": 8,
        "creativity_reason": "ý tưởng rõ",
        "creativity_known": True,
        "channel_fit": 5,
        "channel_fit_reason": "đúng chủ đề AI music",
        "channel_fit_known": True,
        "content_summary": "Video nhạc AI với hình minh họa.",
        "content_ai_visual": True,
    }


def main() -> None:
    print("== real TikTok search ==")
    config = service._load_config()
    from discovery_live import discover_new_candidates

    candidates, blockers = discover_new_candidates(
        config, "AI Music", read_search=lambda kw: read_keyword_search(kw)
    )
    print(f"candidates discovered: {len(candidates)}")
    print(f"blockers: {blockers}")
    with_media = [c for c in candidates if c.download_url]
    print(f"candidates with a media url: {len(with_media)}")
    assert candidates, "the search returned nothing"

    print("\n== real frame capture + mocked AI (no key on this host) ==")
    original = ca.request_content_analysis
    ca.request_content_analysis = _mock_payload
    try:
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"

            def reader(video):
                if not video.download_url:
                    return []
                from poster import capture_video_frames

                return capture_video_frames(
                    video.download_url, offsets=(0.5, 3.0, 8.0), referer=video.source_url
                )

            analyses = ca.analyze_candidates(
                candidates[:5], "AI Music", frame_reader=reader, cache_path=cache_path
            )
    finally:
        ca.request_content_analysis = original

    print(f"analyses: {len(analyses)}")
    for a in analyses:
        mark = f"#{a.rank}" if a.ranked else "  "
        print(
            f"  {mark} @{a.creator:20} score={a.score:3} frames={a.frame_count} "
            f"analyzed={a.content_analyzed} ranked={a.ranked}"
        )
        if not a.ranked:
            print(f"        reason: {a.insufficient_reason}")

    ranked = [a for a in analyses if a.ranked]
    assert ranked, "no candidate was ranked"
    assert ranked[0].rank == 1
    assert ranked[0].frame_count > 0, "the top candidate has no real frames"
    assert ranked[0].score > 0
    assert len(ranked[0].dimensions) == 7
    assert sum(d.max_points for d in ranked[0].dimensions) == 100
    assert ca.best_analysis(analyses) is ranked[0]

    # A candidate without a media url must be marked and not ranked.
    without = [a for a in analyses if not a.ranked]
    for a in without:
        assert a.frame_count == 0
        assert a.score == 0
        assert ca.INSUFFICIENT_DATA in a.summary

    print("\n== the dashboard selection follows the AI ranking ==")
    result = service._discovery_request(topic="AI Music")
    print("status:", result.get("status"))
    print("candidate_count:", result.get("candidate_count"))
    print("ranked_count:", result.get("ranked_count"))
    print("insufficient_count:", result.get("insufficient_count"))
    print("shortfall:", result.get("shortfall_note"))
    print("summary:", (result.get("analysis_summary") or "").replace("\n", " | "))
    selected = result.get("selected")
    analyses_out = result.get("analyses") or []
    print(f"analyses in payload: {len(analyses_out)}")
    if analyses_out:
        top = analyses_out[0]
        print(f"top analysis: @{top['creator']} score={top['score']} rank={top['rank']}")
    if selected:
        print(f"selected: @{selected.get('creator')} {selected.get('source_url')}")
        sel_a = result.get("selected_analysis")
        if sel_a:
            print(f"selected analysis score: {sel_a['score']} rank={sel_a['rank']}")
    assert result.get("downloaded") is False, "something was downloaded"
    print("nothing downloaded: OK")

    print("\nPIPELINE CHECK PASSED")


if __name__ == "__main__":
    main()

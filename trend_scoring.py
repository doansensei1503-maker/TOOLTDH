"""Deterministic, explainable trend scoring for P1 research candidates.

The score answers: which of the collected videos is the strongest research
reference right now?

The contributions are normalized so that no single raw metric can dominate
the result, and every contribution is documented and reported with the
candidate.

Four different facts are kept apart on purpose:

  1. DISCOVERY ELIGIBILITY  - did the candidate survive the user filters?
  2. RELEVANCE              - does it belong to the topic? (relevance.py)
  3. TREND SCORE            - how strong is it as a reference? (this module)
  4. RIGHTS ELIGIBILITY     - may it be reused? (rights_status_of)

A missing metric is UNKNOWN. It is never turned into a zero, and it never
causes a division by zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

# The weights of the trend contributions. They sum to 100.
DEFAULT_WEIGHTS: dict[str, float] = {
    "relevance": 42.0,       # how well it belongs to the topic
    "reach": 16.0,           # how many people saw it
    "engagement": 17.0,      # how strongly the audience reacted
    "velocity": 11.0,        # views per day, only when the age is known
    "recency": 8.0,          # how new it is
    "evidence": 6.0,         # how complete the metadata is
}

# The reach, engagement, velocity, recency and evidence contributions are
# metric driven. Their combined maximum is capped, so no metric can
# outvote the relevance of a candidate. The relevance stays the decisive
# factor: a very popular but off-topic video can never beat a clearly
# on-topic one.
METRIC_CEILING = 58.0

# The engagement tiers: (engagement rate, points). The rate is the total
# real engagement (likes + comments + shares) over the views.
ENGAGEMENT_TIERS: tuple[tuple[float, float], ...] = (
    (0.20, 1.00),
    (0.12, 0.85),
    (0.07, 0.70),
    (0.04, 0.55),
    (0.02, 0.40),
    (0.01, 0.25),
    (0.005, 0.12),
)

# The reach tiers: the views are compared with a logarithmic scale, so a
# video with 10x the views does not get 10x the points.
REACH_TIERS: tuple[tuple[float, float], ...] = (
    (10_000_000, 1.00),
    (3_000_000, 0.92),
    (1_000_000, 0.84),
    (300_000, 0.72),
    (100_000, 0.60),
    (30_000, 0.48),
    (10_000, 0.36),
    (3_000, 0.24),
    (500, 0.12),
)

# The recency tiers: (max age in days, points).
RECENCY_TIERS: tuple[tuple[int, float], ...] = (
    (2, 1.00),
    (7, 0.88),
    (14, 0.76),
    (30, 0.60),
    (60, 0.42),
    (90, 0.28),
    (180, 0.14),
)

# The velocity tiers: (views per day, points).
VELOCITY_TIERS: tuple[tuple[float, float], ...] = (
    (50_000, 1.00),
    (20_000, 0.90),
    (8_000, 0.78),
    (3_000, 0.64),
    (1_000, 0.50),
    (300, 0.36),
    (100, 0.22),
    (30, 0.10),
)

# The evidence tiers: (known metric ratio, points).
EVIDENCE_TIERS: tuple[tuple[float, float], ...] = (
    (1.00, 1.00),
    (0.75, 0.85),
    (0.50, 0.65),
    (0.25, 0.40),
)

# The metrics that count as evidence.
EVIDENCE_METRICS = ("views", "likes", "comments", "shares", "duration", "posted_at")


@dataclass
class TrendScore:
    """The trend verdict of one candidate."""

    score: float
    contributions: dict[str, float] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "contributions": {k: round(v, 2) for k, v in self.contributions.items()},
            "details": self.details,
            "reason": self.reason,
        }


def _known_ratio(candidate: Any) -> float:
    """Return how much of the metadata is really known."""
    missing = set(getattr(candidate, "missing_metrics", None) or [])
    present = [name for name in EVIDENCE_METRICS if name not in missing]
    return len(present) / float(len(EVIDENCE_METRICS))


def _tier(value: float, tiers: tuple[tuple[Any, float], ...]) -> float:
    """Return the points of the first tier the value reaches."""
    for threshold, points in tiers:
        if value >= threshold:
            return points
    return 0.0


def _recency_points(age_days: int | None, tiers: tuple[tuple[int, float], ...]) -> float:
    """Return the recency points, or zero when the age is unknown."""
    if age_days is None or age_days < 0:
        return 0.0
    for threshold, points in tiers:
        if age_days <= threshold:
            return points
    return 0.0


def score_candidate(
    candidate: Any,
    *,
    relevance_score: float = 0.0,
    age_days: int | None = None,
    today: date | None = None,
    weights: dict[str, float] | None = None,
) -> TrendScore:
    """Score one candidate and report every contribution.

    ``relevance_score`` is the 0..100 score of the relevance engine. It is
    the largest single contribution, but it can never exceed its own
    weight, so a very popular but off-topic video cannot win.
    """
    active = dict(DEFAULT_WEIGHTS)
    for key, value in (weights or {}).items():
        try:
            active[key] = float(value)
        except (TypeError, ValueError):
            continue

    missing = set(getattr(candidate, "missing_metrics", None) or [])

    # --- Relevance. -------------------------------------------------------
    relevance = max(0.0, min(100.0, float(relevance_score or 0.0)))
    c_relevance = active["relevance"] * (relevance / 100.0)

    # --- Reach: the views, on a logarithmic scale. ------------------------
    views = int(getattr(candidate, "views", 0) or 0)
    views_known = "views" not in missing and views > 0
    reach_ratio = _tier(float(views), REACH_TIERS) if views_known else 0.0
    c_reach = active["reach"] * reach_ratio

    # --- Engagement: the real engagement rate. ----------------------------
    likes = int(getattr(candidate, "likes", 0) or 0)
    comments = int(getattr(candidate, "comments", 0) or 0)
    shares = int(getattr(candidate, "shares", 0) or 0)
    engagement_known = (
        views_known
        and "likes" not in missing
        and "comments" not in missing
        and "shares" not in missing
    )
    engagement_ratio = 0.0
    if engagement_known and views > 0:
        engagement_ratio = (likes + comments + shares) / float(views)
    elif views_known:
        # A partially known engagement is reported honestly as a lower
        # confidence, so it never beats a fully measured video on its own.
        known_engagement = 0
        known_count = 0
        if "likes" not in missing:
            known_engagement += likes
            known_count += 1
        if "comments" not in missing:
            known_engagement += comments
            known_count += 1
        if "shares" not in missing:
            known_engagement += shares
            known_count += 1
        if known_count and views > 0:
            engagement_ratio = (known_engagement / float(views)) * (known_count / 3.0)
    c_engagement = active["engagement"] * _tier(engagement_ratio, ENGAGEMENT_TIERS)

    # --- Velocity: the estimated views per day. ---------------------------
    # This is an ESTIMATE from one observation, never a growth history.
    velocity_known = False
    views_per_day = None
    if age_days is not None and age_days >= 0 and views_known:
        velocity_known = True
        views_per_day = views / float(max(1, age_days + 1))
    c_velocity = active["velocity"] * (_tier(views_per_day, VELOCITY_TIERS) if velocity_known else 0.0)

    # --- Recency. ---------------------------------------------------------
    c_recency = active["recency"] * _recency_points(age_days, RECENCY_TIERS)

    # --- Evidence completeness. ------------------------------------------
    evidence_ratio = _known_ratio(candidate)
    c_evidence = active["evidence"] * _tier(evidence_ratio, EVIDENCE_TIERS)

    total = c_relevance + c_reach + c_engagement + c_velocity + c_recency + c_evidence
    # The metric driven part is capped, so the relevance keeps the decisive
    # vote. A huge metric can never outvote a clearly on-topic candidate.
    metric_total = c_reach + c_engagement + c_velocity + c_recency + c_evidence
    if metric_total > METRIC_CEILING:
        scale = METRIC_CEILING / metric_total
        c_reach *= scale
        c_engagement *= scale
        c_velocity *= scale
        c_recency *= scale
        c_evidence *= scale
        metric_total = METRIC_CEILING
    total = c_relevance + metric_total
    total = max(0.0, min(100.0, total))

    contributions = {
        "relevance": c_relevance,
        "reach": c_reach,
        "engagement": c_engagement,
        "velocity": c_velocity,
        "recency": c_recency,
        "evidence": c_evidence,
    }
    details = {
        "relevance_score": round(relevance, 2),
        "views": views if views_known else None,
        "views_known": views_known,
        "engagement_rate": round(engagement_ratio, 5) if engagement_known else None,
        "engagement_known": engagement_known,
        "views_per_day": round(views_per_day, 2) if views_per_day is not None else None,
        "views_per_day_estimated": velocity_known,
        "age_days": age_days,
        "evidence_ratio": round(evidence_ratio, 3),
        "missing_metrics": sorted(missing),
    }

    reason = (
        f"relevance {relevance:.0f}/100 (×{active['relevance']:.0f}) + "
        f"reach {reach_ratio:.2f}×{active['reach']:.0f} + "
        f"engagement {engagement_ratio:.4f}×{active['engagement']:.0f} + "
        f"velocity {('%.1f/ngày' % views_per_day) if views_per_day is not None else 'UNKNOWN'}×{active['velocity']:.0f} + "
        f"recency {age_days if age_days is not None else 'UNKNOWN'}d×{active['recency']:.0f} + "
        f"evidence {evidence_ratio:.2f}×{active['evidence']:.0f}"
    )

    return TrendScore(
        score=total,
        contributions=contributions,
        details=details,
        reason=reason,
    )


def rank_candidates(
    candidates: list[Any],
    *,
    relevance_by_url: dict[str, float] | None = None,
    age_by_url: dict[str, int | None] | None = None,
    weights: dict[str, float] | None = None,
) -> list[tuple[Any, TrendScore]]:
    """Score and rank the candidates deterministically.

    The order is stable: the same evidence always produces the same order,
    and a tie is broken by the source URL, never by chance.
    """
    relevance_by_url = relevance_by_url or {}
    age_by_url = age_by_url or {}
    scored: list[tuple[Any, TrendScore]] = []
    for candidate in candidates:
        url = str(getattr(candidate, "source_url", "") or "")
        result = score_candidate(
            candidate,
            relevance_score=float(relevance_by_url.get(url, 0.0) or 0.0),
            age_days=age_by_url.get(url),
            weights=weights,
        )
        scored.append((candidate, result))
    scored.sort(key=lambda item: (-item[1].score, str(getattr(item[0], "source_url", ""))))
    return scored


__all__ = [
    "DEFAULT_WEIGHTS",
    "ENGAGEMENT_TIERS",
    "EVIDENCE_METRICS",
    "REACH_TIERS",
    "RECENCY_TIERS",
    "TrendScore",
    "VELOCITY_TIERS",
    "rank_candidates",
    "score_candidate",
]

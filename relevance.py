"""General, explainable relevance engine for P1 research searches.

The relevance layer answers one question: how well does this candidate
belong to the topic the user is researching?

It uses only evidence that really exists:

  * the original topic
  * the query the candidate was actually found with (its origin)
  * the title / caption
  * the hashtags of the caption
  * the concepts and synonyms of the topic
  * the negative keywords the user excluded

The layer never claims that metadata proves what the video visually shows.
When the evidence is weak the candidate is marked ``NEEDS_REVIEW`` with
the reason, instead of being silently accepted or rejected.

The weights live in ``DEFAULT_WEIGHTS`` and can be overridden from the
configuration, so every score stays explainable and adjustable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from query_planner import CONCEPTS, normalize_text, tokenize

# The weights of the relevance signals. They sum to 100 so the relevance
# score reads as a percentage of how certain the match is.
DEFAULT_WEIGHTS: dict[str, float] = {
    "topic_phrase": 30.0,   # the topic phrase itself is in the caption
    "core_concept": 24.0,   # a core concept of the topic is present
    "query_origin": 18.0,   # the candidate came from a planned query
    "related_intent": 14.0, # the caption carries the wanted intent
    "subtopic": 8.0,        # a subtopic of the topic is present
    "topic_words": 6.0,     # a key word of the topic is present
}

# A negative keyword lowers the score instead of rejecting on its own,
# because a caption can mention a word in passing.
NEGATIVE_PENALTY = 30.0

# How much of the query origin contributes, scaled by the query weight.
QUERY_ORIGIN_MAX = 18.0

# How much of the intent signal contributes, scaled by the intent weight.
INTENT_MAX = 16.0

# A relevance score of 45 with a real concept or phrase match is enough to
# verify. The score is not the only condition: a caption must also carry
# the subject (the topic phrase or a core concept of it). A score reached
# only through the query origin or a single weak word is NOT enough.
RELEVANCE_VERIFIED_MIN = 38.0
# Below this relevance the candidate is not even worth a manual review.
RELEVANCE_MINIMUM = 18.0

# The hashtags of a caption.
_HASHTAG = re.compile(r"#([\wÀ-ỹ]+)")


@dataclass
class RelevanceResult:
    """The relevance verdict of one candidate."""

    status: str                     # VERIFIED / NEEDS_REVIEW / REJECTED
    score: float                    # 0..100
    signals: dict[str, float] = field(default_factory=dict)
    matched_concepts: list[str] = field(default_factory=list)
    matched_intents: list[str] = field(default_factory=list)
    negative_hits: list[str] = field(default_factory=list)
    reason: str = ""
    query_origin: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "score": round(self.score, 2),
            "signals": {k: round(v, 2) for k, v in self.signals.items()},
            "matched_concepts": list(self.matched_concepts),
            "matched_intents": list(self.matched_intents),
            "negative_hits": list(self.negative_hits),
            "reason": self.reason,
            "query_origin": self.query_origin,
        }


def _caption_text(title: str) -> str:
    """Return the folded caption text."""
    return normalize_text(title)


def _hashtags(text: str) -> list[str]:
    """Return the hashtags of a caption."""
    return [tag.lower() for tag in _HASHTAG.findall(str(text or ""))]


def _contains_phrase(haystack: str, phrase: str) -> bool:
    """Return whether the text carries the phrase on a word boundary."""
    folded_phrase = normalize_text(phrase).strip()
    if not folded_phrase:
        return False
    return folded_phrase in haystack


def _carries_any(haystack: str, hashtags: list[str], words: list[str]) -> bool:
    """Return whether the text or its hashtags carry one of the words."""
    for word in words:
        folded = normalize_text(word).strip()
        if not folded:
            continue
        if _contains_phrase(haystack, folded):
            return True
        for tag in hashtags:
            if folded in tag or tag in folded:
                return True
    return False


def concept_words(concept: str) -> list[str]:
    """Return the words that name a concept."""
    spec = CONCEPTS.get(concept, {})
    words: list[str] = []
    canonical = str(spec.get("canonical", concept) or "")
    if canonical:
        words.append(canonical)
    words.extend(str(alias) for alias in spec.get("aliases", []))
    words.extend(str(item) for item in spec.get("english", []))
    return [w for w in words if str(w).strip()]


def topic_concept_words(topic: str) -> list[str]:
    """Return the concept words that belong to a topic.

    The topic itself and its recognised concepts are used. The concept
    dictionary is topic-independent, so no unrelated subject is injected.
    """
    from query_planner import analyze_intent

    intent = analyze_intent(topic)
    words: list[str] = []
    folded = normalize_text(topic)
    # The significant words of the topic itself.
    for token in tokenize(topic):
        if len(token) >= 3:
            words.append(token)
    # The words of every recognised concept.
    for concept in intent.concepts:
        words.extend(concept_words(concept))
    # The english forms of the concepts are looked for too.
    seen: set[str] = set()
    unique: list[str] = []
    for word in words:
        folded_word = normalize_text(word).strip()
        if not folded_word or folded_word in seen:
            continue
        seen.add(folded_word)
        unique.append(word)
    return unique


def intent_words(intents: list[str]) -> list[str]:
    """Return the words that carry an intent."""
    from query_planner import INTENT_PATTERNS

    words: list[str] = []
    for intent in intents or []:
        words.extend(INTENT_PATTERNS.get(intent, []))
    return [w for w in words if str(w).strip()]


def score_relevance(
    title: str,
    topic: str,
    *,
    query_origin: str = "",
    query_weight: float = 1.0,
    concepts: list[str] | None = None,
    intents: list[str] | None = None,
    exclude: list[str] | None = None,
    weights: dict[str, float] | None = None,
) -> RelevanceResult:
    """Score how well one candidate belongs to the topic.

    The result carries the individual signal contributions, so the score
    can always be explained.
    """
    from query_planner import analyze_intent

    active = dict(DEFAULT_WEIGHTS)
    for key, value in (weights or {}).items():
        try:
            active[key] = float(value)
        except (TypeError, ValueError):
            continue

    intent = analyze_intent(topic)
    topic_concepts = list(concepts) if concepts is not None else list(intent.concepts)
    topic_intents = list(intents) if intents is not None else list(intent.intents)

    caption = _caption_text(title)
    hashtags = _hashtags(title)

    signals: dict[str, float] = {}
    matched_concepts: list[str] = []
    matched_intents: list[str] = []
    negative_hits: list[str] = []

    # --- Signal 1: the topic phrase is in the caption. ---------------------
    phrase_hit = _contains_phrase(caption, topic)
    signals["topic_phrase"] = active.get("topic_phrase", 0.0) if phrase_hit else 0.0

    # --- Signal 2: a core concept of the topic is present. -----------------
    # The caption carries a concept of the topic. When several concepts of
    # the topic are present, the caption is closer to the subject, so the
    # signal grows with the number of matched concepts.
    concept_hit = False
    concept_count = 0
    for concept in topic_concepts:
        words = concept_words(concept)
        if _carries_any(caption, hashtags, words):
            concept_hit = True
            concept_count += 1
            matched_concepts.append(concept)
    # The significant words of the topic count as a concept signal too.
    if not concept_hit:
        topic_words = [token for token in tokenize(topic) if len(token) >= 4]
        if topic_words and _carries_any(caption, hashtags, topic_words):
            concept_hit = True
            concept_count = 1
            matched_concepts.append("topic_words")
    # The concept signal is bounded, so it can never exceed its own weight.
    # The first matched concept gives the full weight; every further one
    # adds a share of it, so the signal grows but stays inside the bound.
    if concept_hit:
        concept_base = active.get("core_concept", 0.0)
        signals["core_concept"] = min(
            concept_base,
            concept_base * (1.0 + 0.35 * (concept_count - 1)),
        )
    else:
        signals["core_concept"] = 0.0

    # --- Signal 3: the candidate came from a planned query. ----------------
    origin_hit = bool(query_origin)
    signals["query_origin"] = (
        min(QUERY_ORIGIN_MAX, active.get("query_origin", 0.0) * max(0.0, float(query_weight or 0.0)))
        if origin_hit else 0.0
    )

    # --- Signal 4: the caption carries the wanted intent. ------------------
    # The intent corroborates the subject: a caption that names the concept
    # AND the wanted intent is strong evidence, so the intent signal reaches
    # its full weight in that case.
    intent_hit = False
    intent_count = 0
    for name in topic_intents:
        words = intent_words([name])
        if words and _carries_any(caption, hashtags, words):
            intent_hit = True
            intent_count += 1
            matched_intents.append(name)
    if intent_hit:
        intent_base = active.get("related_intent", 0.0)
        if concept_hit:
            signals["related_intent"] = min(INTENT_MAX, intent_base)
        else:
            signals["related_intent"] = min(INTENT_MAX, intent_base * 0.6)
    else:
        signals["related_intent"] = 0.0

    # --- Signal 5: a subtopic of the topic is present. ---------------------
    subtopic_hit = False
    for concept in topic_concepts:
        spec = CONCEPTS.get(concept, {})
        subtopics = [str(s) for s in spec.get("subtopics", [])]
        if subtopics and _carries_any(caption, hashtags, subtopics):
            subtopic_hit = True
            break
    signals["subtopic"] = active.get("subtopic", 0.0) if subtopic_hit else 0.0

    # --- Signal 6: the topic's own key words are present. ------------------
    # The significant words of the topic are matched on their own, so a
    # Vietnamese topic can match an English caption through the concept
    # vocabulary without needing every original word.
    topic_word_hit = False
    topic_words = [token for token in tokenize(topic) if len(token) >= 4]
    if topic_words and _carries_any(caption, hashtags, topic_words):
        topic_word_hit = True
    signals["topic_words"] = active.get("topic_words", 0.0) if topic_word_hit else 0.0

    score = sum(signals.values())

    # --- Negative keywords. ------------------------------------------------
    for word in exclude or []:
        folded = normalize_text(word).strip()
        if folded and _contains_phrase(caption, folded):
            negative_hits.append(word)
    if negative_hits:
        score -= NEGATIVE_PENALTY * len(negative_hits)

    score = max(0.0, min(100.0, score))

    # --- The verdict. ------------------------------------------------------
    if negative_hits:
        status = "REJECTED"
        reason = "Chứa từ khóa bị loại trừ: " + ", ".join(negative_hits)
    elif score >= RELEVANCE_VERIFIED_MIN and (phrase_hit or concept_hit or topic_word_hit):
        status = "VERIFIED"
        reason = (
            "Khớp chủ đề ("
            + ", ".join(
                part for part, present in (
                    ("cụm chủ đề", phrase_hit),
                    ("khái niệm lõi", concept_hit),
                    ("từ khóa chủ đề", topic_word_hit),
                    ("ý định", intent_hit),
                    ("gốc truy vấn", origin_hit),
                ) if present
            )
            + ")"
        )
    elif score >= RELEVANCE_MINIMUM:
        status = "NEEDS_REVIEW"
        reason = (
            "Bằng chứng metadata còn yếu (điểm "
            + f"{score:.0f}/100"
            + (", khớp: " + ", ".join(matched_concepts + matched_intents) if (matched_concepts or matched_intents) else "")
            + ") — cần người dùng xác nhận nội dung thật."
        )
    else:
        status = "REJECTED"
        reason = f"Không đủ dấu hiệu thuộc chủ đề (điểm {score:.0f}/100)."

    return RelevanceResult(
        status=status,
        score=score,
        signals=signals,
        matched_concepts=matched_concepts,
        matched_intents=matched_intents,
        negative_hits=negative_hits,
        reason=reason,
        query_origin=query_origin,
    )


__all__ = [
    "DEFAULT_WEIGHTS",
    "NEGATIVE_PENALTY",
    "RELEVANCE_MINIMUM",
    "RELEVANCE_VERIFIED_MIN",
    "RelevanceResult",
    "concept_words",
    "intent_words",
    "score_relevance",
    "topic_concept_words",
]

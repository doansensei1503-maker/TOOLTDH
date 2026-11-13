"""General-purpose deterministic query planner for P1 research searches.

A project topic is a research intention, not one literal keyword. This
module turns a topic into several complementary search directions without
any AI model, any network call and any hardcoded special case for a
particular subject.

The pipeline is:

    topic -> intent analysis -> search dimensions -> query plan

Each planned query carries the reason why it belongs to the topic, so the
plan can be shown to the user and edited before the run.

HONESTY NOTE
------------
A deterministic planner cannot read arbitrary language as deeply as a
semantic model. It works from dictionaries of concepts, intents and
synonyms that are visible and editable in this file. It therefore produces
useful, on-topic variations for the topics it understands, and it says so
in the plan (``confidence`` and ``notes``) when it has to fall back to a
narrower plan. It never claims unrestricted semantic understanding.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# The hard ceiling of one controlled run. The default target is lower.
MAX_QUERIES = 8
DEFAULT_QUERY_TARGET = 5
MIN_QUERIES = 1

# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

# Vietnamese tone marks and the letters they combine with, so a topic can be
# compared with an English caption that carries no diacritics at all.
_VN_COMBINING = {
    "a": "a", "à": "a", "á": "a", "ả": "a", "ã": "a", "ạ": "a",
    "ă": "a", "ằ": "a", "ắ": "a", "ẳ": "a", "ẵ": "a", "ặ": "a",
    "â": "a", "ầ": "a", "ấ": "a", "ẩ": "a", "ẫ": "a", "ậ": "a",
    "e": "e", "è": "e", "é": "e", "ẻ": "e", "ẽ": "e", "ẹ": "e",
    "ê": "e", "ề": "e", "ế": "e", "ể": "e", "ễ": "e", "ệ": "e",
    "i": "i", "ì": "i", "í": "i", "ỉ": "i", "ĩ": "i", "ị": "i",
    "o": "o", "ò": "o", "ó": "o", "ỏ": "o", "õ": "o", "ọ": "o",
    "ô": "o", "ồ": "o", "ố": "o", "ổ": "o", "ỗ": "o", "ộ": "o",
    "ơ": "o", "ờ": "o", "ớ": "o", "ở": "o", "ỡ": "o", "ợ": "o",
    "u": "u", "ù": "u", "ú": "u", "ủ": "u", "ũ": "u", "ụ": "u",
    "ư": "u", "ừ": "u", "ứ": "u", "ử": "u", "ữ": "u", "ự": "u",
    "y": "y", "ỳ": "y", "ý": "y", "ỷ": "y", "ỹ": "y", "ỵ": "y",
    "d": "d", "đ": "d",
}

# Words that carry no research meaning. They never become a search concept.
STOP_WORDS = frozenset({
    "a", "an", "and", "the", "for", "of", "to", "in", "on", "with", "my",
    "video", "videos", "tiktok", "fyp", "new", "best", "top", "cach",
    "cách", "ve", "về", "nhu", "như", "mot", "một", "theo", "ban", "bạn",
    "cho", "voi", "với", "tu", "từ", "nang", "nâng", "cao", "dep", "đẹp",
})

# ---------------------------------------------------------------------------
# Concept dictionary
# ---------------------------------------------------------------------------
#
# Every entry is a concept the planner can recognise in a topic, together
# with:
#   canonical : the concept in its neutral form
#   aliases   : words that name the same concept (Vietnamese + English)
#   english   : the English search words that carry the concept
#   intents   : the search intents the concept usually belongs to
#   subtopics : the narrower subjects inside the concept
#
# The dictionary is topic-independent: it describes HOW people search, not
# what one particular project is about.

CONCEPTS: dict[str, dict[str, Any]] = {
    "smartphone_filming": {
        "canonical": "smartphone filming",
        "aliases": [
            "điện thoại", "dien thoai", "smartphone", "phone", "điện thoại quay",
            "quay bằng điện thoại", "quay video bằng điện thoại", "mobile",
            "iphone", "android",
        ],
        "english": ["smartphone videography", "mobile cinematic filming", "phone camera tips"],
        "intents": ["tutorial", "filmmaking"],
        "subtopics": ["camera angle", "gimbal", "lighting", "stabilization", "color grading",
                      "slow motion", "time lapse", "shot composition", "white balance",
                      "khung hình", "ánh sáng", "góc máy"],
    },
    "baking": {
        "canonical": "home baking",
        "aliases": [
            "bánh", "banh", "làm bánh", "lam banh", "công thức làm bánh",
            "cong thuc lam banh", "bake", "baking", "baked", "recipe",
            "pastry", "cake", "cupcake", "bread", "cookie",
        ],
        "english": ["home baking recipe", "easy baking recipe", "baking tutorial"],
        "intents": ["tutorial", "recipe"],
        "subtopics": ["bánh kem", "bánh mì", "bánh quy", "bánh xèo", "bánh chuối",
                      "chocolate", "cheesecake", "cookies", "bread", "cake",
                      "kem", "sponge cake", "cupcake", "brownie"],
    },
    "travel": {
        "canonical": "travel",
        "aliases": [
            "du lịch", "du lich", "travel", "đà lạt", "dalat", "khám phá",
            "tham quan", "trip",
        ],
        "english": ["travel guide", "travel vlog", "things to do"],
        "intents": ["travel", "lifestyle"],
        "subtopics": ["check-in", "food tour", "nature", "landmark", "hotel",
                      "café", "night market", "itinerary", "hiking", "photography spot"],
    },
    "filmmaking": {
        "canonical": "filmmaking",
        "aliases": [
            "quay video", "dựng video", "làm video", "quay phim", "filmmaking",
            "cinematic", "quay phim đẹp", "video production",
        ],
        "english": ["mobile filmmaking", "cinematic videography", "video shooting tips"],
        "intents": ["tutorial", "filmmaking"],
        "subtopics": ["b-roll", "storyboard", "color grading", "camera movement",
                      "drone shot", "sound design", "script", "lens", "aperture"],
    },
    "cooking": {
        "canonical": "cooking",
        "aliases": ["nấu ăn", "nau an", "cooking", "món ăn", "mon an"],
        "english": ["cooking tutorial", "easy recipe", "home cooking"],
        "intents": ["tutorial", "recipe"],
    },
    "beauty": {
        "canonical": "beauty",
        "aliases": ["làm đẹp", "lam dep", "makeup", "beauty", "skincare", "mỹ phẩm"],
        "english": ["makeup tutorial", "beauty tips", "skincare routine"],
        "intents": ["tutorial", "lifestyle"],
    },
    "fitness": {
        "canonical": "fitness",
        "aliases": ["tập gym", "tap gym", "fitness", "workout", "tập luyện", "thể hình"],
        "english": ["home workout", "fitness tips", "beginner workout"],
        "intents": ["tutorial", "lifestyle"],
    },
    "music": {
        "canonical": "music",
        "aliases": ["nhạc", "nhac", "music", "bài hát", "bai hat", "song", "cover", "remix"],
        "english": ["music", "song cover", "remix"],
        "intents": ["music"],
    },
    "anime": {
        "canonical": "anime",
        "aliases": ["anime", "naruto", "one piece", "manga"],
        "english": ["anime edit", "anime music edit", "anime amv"],
        "intents": ["music", "edit"],
    },
    "review": {
        "canonical": "review",
        "aliases": ["review", "đánh giá", "danh giá", "so sánh", "unboxing", "mở hộp"],
        "english": ["review", "honest review", "comparison"],
        "intents": ["review"],
    },
    "tutorial": {
        "canonical": "tutorial",
        "aliases": [
            "hướng dẫn", "huong dan", "tutorial", "cách làm", "cach lam", "học",
            "dạy", "bí quyết", "mẹo", "meo", "tips", "thủ thuật",
        ],
        "english": ["step by step guide", "beginner guide", "quick tips"],
        "intents": ["tutorial"],
    },
    "editing": {
        "canonical": "editing",
        "aliases": ["edit", "editing", "dựng", "chỉnh sửa", "capcut", "premiere"],
        "english": ["video editing", "editing tutorial", "capcut tips"],
        "intents": ["edit", "tutorial"],
    },
    "lifestyle": {
        "canonical": "lifestyle",
        "aliases": ["lifestyle", "đời sống", "doi song", "routine", "vlog", "nhật ký"],
        "english": ["lifestyle", "daily routine", "vlog"],
        "intents": ["lifestyle"],
    },
    "diy": {
        "canonical": "diy",
        "aliases": ["tự làm", "tu lam", "diy", "thủ công", "thu cong", "craft"],
        "english": ["diy", "homemade", "craft tutorial"],
        "intents": ["tutorial", "howto"],
    },
    "makeup": {
        "canonical": "makeup",
        "aliases": ["trang điểm", "trang diem", "makeup", "son", "kem nền"],
        "english": ["makeup tutorial", "makeup look"],
        "intents": ["tutorial", "lifestyle"],
    },
    "tech": {
        "canonical": "tech",
        "aliases": ["công nghệ", "cong nghe", "tech", "technology", "thiết bị", "máy ảnh"],
        "english": ["tech tips", "gear review", "camera tips"],
        "intents": ["review", "tutorial"],
    },
    "food": {
        "canonical": "food",
        "aliases": ["ẩm thực", "am thuc", "food", "món ngon", "mon ngon", "nhà hàng"],
        "english": ["food review", "street food", "food tour"],
        "intents": ["review", "lifestyle", "travel"],
    },
}

# Intent -> the words that make a query read like that intent.
INTENT_PATTERNS: dict[str, list[str]] = {
    "tutorial": ["tutorial", "hướng dẫn", "how to", "cách", "mẹo", "tips", "guide"],
    "review": ["review", "đánh giá", "so sánh", "comparison", "honest"],
    "recipe": ["công thức", "recipe", "cách làm", "nguyên liệu", "ingredients"],
    "filmmaking": ["filmmaking", "cinematic", "quay phim", "shooting", "videography"],
    "music": ["music", "nhạc", "edit", "remix", "cover", "amv"],
    "lifestyle": ["lifestyle", "vlog", "routine", "nhật ký", "đời sống"],
    "travel": ["travel", "du lịch", "guide", "vlog", "thăm quan"],
    "howto": ["cách làm", "diy", "tự làm", "how to make", "homemade"],
    "edit": ["edit", "editing", "dựng", "chỉnh sửa"],
}

# Words that only describe the FORMAT of the result, not the subject.
FORMAT_WORDS = frozenset({
    "video", "videos", "clip", "clips", "short", "shorts", "tiktok", "reels",
    "youtube", "hình", "hinh",
})

# Words that name the AUDIENCE or the QUALITY, not the subject.
QUALITY_WORDS = frozenset({
    "đẹp", "dep", "hay", "tuyệt", "tuyet", "dễ", "de", "nhanh", "quick",
    "simple", "easy", "beautiful", "good", "best", "top",
})

# Words that describe the SHAPE of the content, not its subject.
#
# A query built only from these words ("step by step guide", "quick tips")
# matches almost anything on the source, so it is never sent on its own.
# A phrase that carries no other word must be anchored with a subject word
# of the topic before it is used as a query.
GENERIC_WORDS = frozenset({
    "step", "steps", "by", "guide", "guides", "beginner", "basic", "quick",
    "tips", "tip", "tricks", "trick", "ideas", "idea", "way", "ways",
    "how", "to", "for", "your", "you", "the", "and", "with", "full",
    "hướng dẫn", "huong dan", "mẹo", "meo", "thủ thuật", "thu thuat",
    "bí quyết", "bi quyet", "cách làm", "cach lam",
})

# Words that describe the ACTION, not the thing being acted on.
#
# They are dropped when a query has to be anchored, because an anchored
# query that names only the action ("quay step by step guide") still
# matches too much. The subject noun ("điện thoại") is the better anchor.
ACTION_WORDS = frozenset({
    "quay", "làm", "lam", "nấu", "nau", "trồng", "trong", "chơi", "choi",
    "bơi", "noi", "nói", "diễn", "dien", "may", "may", "cắt", "cat",
    "dựng", "dung", "chỉnh", "chinh", "hướng", "huong", "dạy", "day",
    "học", "hoc", "xem", "nghe", "mua", "ban", "bán", "ban", "review",
    "đánh giá", "danh gia", "so sánh", "so sanh", "tìm", "tim", "chia",
    "sẻ", "se", "check", "top", "mẹo", "meo",
})

# Particles that carry no research meaning. They are not topics, they are
# grammar, so they must never be used to anchor a query.
PARTICLE_WORDS = frozenset({
    "bằng", "bang", "bởi", "boi", "cho", "với", "voi", "cùng", "cung",
    "như", "nhu", "tại", "tai", "về", "ve", "từ", "tu", "ra", "vào",
    "vao", "lên", "len", "xuống", "xuong", "qua", "theo", "trong",
    "trong", "ngoài", "ngoai", "sau", "trước", "truoc", "mà", "ma",
    "thì", "thi", "thế", "the", "rồi", "roi", "để", "de", "vì", "vi",
    "hay", "hoặc", "hoac", "cùng", "cua", "của", "cac", "các", "những",
    "nhung", "một", "mot", "cái", "cai", "con", "các",
})

# Concepts that describe the KIND of content instead of the subject.
# Their English form must never be used as a standalone query.
CONCEPT_CATEGORY_WORDS = frozenset({
    "review", "music", "travel", "lifestyle", "tutorial", "editing",
    "diy", "makeup", "tech", "food", "anime", "beauty", "fitness", "recipe",
    "howto", "filmmaking", "travel", "edit",
})


def _is_generic_phrase(phrase: str) -> bool:
    """Return True when a phrase names no subject at all.

    Such a phrase ("step by step guide") would match almost anything on
    the source, so the planner must not send it on its own.
    """
    words = [w for w in normalize_text(phrase).split() if w]
    if not words:
        return True
    for word in words:
        if word in GENERIC_WORDS:
            continue
        if word in FORMAT_WORDS or word in QUALITY_WORDS:
            continue
        if word in STOP_WORDS:
            continue
        if word in PARTICLE_WORDS:
            continue
        # The word names something concrete -> the phrase is specific.
        return False
    return True


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def normalize_text(value: str) -> str:
    """Return the text with Vietnamese diacritics folded to plain ASCII.

    The fold makes a Vietnamese topic comparable with an English caption
    that carries no diacritics, without losing the original text (the
    original is always kept for the actual query).
    """
    text = unicodedata.normalize("NFC", str(value or ""))
    out: list[str] = []
    for char in text:
        lowered = char.lower()
        if lowered in _VN_COMBINING:
            out.append(_VN_COMBINING[lowered])
        elif char.isascii():
            out.append(lowered)
        else:
            out.append(lowered)
    return "".join(out)


def tokenize(value: str) -> list[str]:
    """Return the meaningful lower-case tokens of a text."""
    folded = normalize_text(value)
    tokens = [
        token.strip(".,!?;:()[]{}\"'")
        for token in re.split(r"[\s/]+", folded)
    ]
    return [token for token in tokens if token and token not in STOP_WORDS]


# ---------------------------------------------------------------------------
# Intent analysis
# ---------------------------------------------------------------------------

@dataclass
class TopicIntent:
    """What the topic is about and what kind of result is wanted."""

    topic: str
    subject: str
    concepts: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    subject_tokens: list[str] = field(default_factory=list)
    subject_phrases: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "subject": self.subject,
            "concepts": list(self.concepts),
            "intents": list(self.intents),
            "subject_tokens": list(self.subject_tokens),
            "subject_phrases": list(self.subject_phrases),
            "notes": list(self.notes),
        }


def analyze_intent(topic: str) -> TopicIntent:
    """Analyse a topic into its subject, concepts and intended result kind.

    The analysis is dictionary driven. It reports what it recognised and
    what it could not recognise, so the plan stays honest.
    """
    original = str(topic or "").strip()
    folded = normalize_text(original)
    notes: list[str] = []

    tokens = tokenize(original)
    token_set = set(tokens)

    concepts: list[str] = []
    for name, spec in CONCEPTS.items():
        for alias in spec.get("aliases", []):
            alias_folded = normalize_text(alias)
            if not alias_folded:
                continue
            # An alias matches when it appears as a whole phrase.
            if alias_folded in folded:
                concepts.append(name)
                break
            # Or when every word of a multi-word alias is present.
            alias_tokens = [t for t in alias_folded.split() if t]
            if len(alias_tokens) > 1 and all(t in token_set for t in alias_tokens):
                concepts.append(name)
                break

    # Keep the order deterministic and remove duplicates.
    concepts = list(dict.fromkeys(concepts))

    intents: list[str] = []
    for name, spec in CONCEPTS.items():
        if name in concepts:
            for intent in spec.get("intents", []):
                if intent not in intents:
                    intents.append(intent)
    # An explicit intent word in the topic wins over an inferred one.
    for intent, patterns in INTENT_PATTERNS.items():
        for pattern in patterns:
            pattern_folded = normalize_text(pattern)
            if pattern_folded and pattern_folded in folded:
                if intent not in intents:
                    intents.append(intent)
                break

    # The subject is the topic without the words that only name the format
    # or the quality. It is the part that has to survive in every query.
    # The ORIGINAL spelling is kept, so a Vietnamese topic stays Vietnamese.
    original_tokens = [
        token.strip(".,!?;:()[]{}\"'")
        for token in re.split(r"[\s/]+", original)
        if token.strip(".,!?;:()[]{}\"'")
    ]
    keep_words = {
        normalize_text(word)
        for word in original_tokens
        if word.lower() not in STOP_WORDS
        and normalize_text(word) not in FORMAT_WORDS
        and normalize_text(word) not in QUALITY_WORDS
    }
    subject_tokens = [word for word in original_tokens if normalize_text(word) in keep_words]
    if not subject_tokens:
        subject_tokens = original_tokens
    if not subject_tokens:
        subject_tokens = list(tokens)

    # The subject PHRASES are the multi-word noun groups of the topic.
    #
    # A Vietnamese compound ("điện thoại", "ống kính", "Du lịch") is one
    # subject even though it is two or three words. Anchoring a query with
    # half of it ("thoại", "ống") produces a query about the wrong thing,
    # so the phrases are detected from the concept aliases and from the
    # compound patterns of the dictionary.
    subject_phrases = _detect_subject_phrases(original, concepts)

    if not concepts:
        notes.append(
            "Không nhận diện được khái niệm nào trong từ điển; kế hoạch dùng các "
            "từ khóa trực tiếp của chủ đề."
        )
    if not intents:
        intents = ["tutorial"]
        notes.append(
            "Không nhận diện được ý định tìm kiếm; mặc định 'hướng dẫn' để tìm "
            "nội dung hữu ích nhất."
        )

    return TopicIntent(
        topic=original,
        subject=" ".join(subject_tokens),
        concepts=concepts,
        intents=intents,
        subject_tokens=subject_tokens,
        subject_phrases=subject_phrases,
        notes=notes,
    )


# Vietnamese and English compound heads: a word that usually belongs to the
# word before it. "điện thoại" is one thing, not two.
#
# The set is folded to ASCII at import time, because it is compared with
# the FOLDED words of the topic. An unfolded entry would never match.
COMPOUND_HEADS = frozenset({
    # Vietnamese compound tails
    "thoại", "anh", "kính", "lịch", "nghiệp", "chơi", "ăn", "uống",
    "nấu", "làm", "quay", "dựng", "chụp", "mua", "bán", "bếp", "nhà",
    "vườn", "rau", "cây", "hoa", "cá", "gà", "thịt", "bánh", "kem",
    "mì", "phở", "bún", "cơm", "nước", "trà", "cà phê", "sữa",
    "ống", "máy", "hình", "phim", "nhạc", "tập", "dàn", "phòng",
    # English compound tails
    "phone", "camera", "lens", "cooking", "baking", "travel", "music",
    "video", "film", "making", "shooting", "recipe", "workout", "routine",
})


# Words that on their own are a subject, so a compound around them is not
# needed to understand what the topic is about.
SUBJECT_WORDS = frozenset({
    "nhạc", "bánh", "mì", "rau", "cây", "trà", "cà phê", "sữa", "bếp",
    "nhà", "vườn", "cá", "gà", "thịt", "kem", "phở", "bún", "cơm",
    "nước", "hình", "phim", "tập", "dàn", "phòng", "chơi", "uống",
    "điện thoại", "ống kính", "máy ảnh", "máy quay",
})

# Every word set above is compared with the FOLDED words of a topic, so it
# has to be folded too. An entry that keeps its diacritics would never
# match the folded word ("máy" would never match "may").
COMPOUND_HEADS = frozenset(normalize_text(w) for w in COMPOUND_HEADS)
SUBJECT_WORDS = frozenset(normalize_text(w) for w in SUBJECT_WORDS)
GENERIC_WORDS = frozenset(normalize_text(w) for w in GENERIC_WORDS)
ACTION_WORDS = frozenset(normalize_text(w) for w in ACTION_WORDS)
PARTICLE_WORDS = frozenset(normalize_text(w) for w in PARTICLE_WORDS)
CONCEPT_CATEGORY_WORDS = frozenset(
    normalize_text(w) for w in CONCEPT_CATEGORY_WORDS
)
FORMAT_WORDS = frozenset(normalize_text(w) for w in FORMAT_WORDS)
QUALITY_WORDS = frozenset(normalize_text(w) for w in QUALITY_WORDS)
STOP_WORDS = frozenset(normalize_text(w) for w in STOP_WORDS)


def _detect_subject_phrases(original: str, concepts: list[str]) -> list[str]:
    """Return the multi-word subject groups of a topic, in original spelling.

    A phrase is either a known concept alias that really occurs in the
    topic, or a run of adjacent words where the later word is a compound
    head. The result keeps the original spelling of the topic.
    """
    original = str(original or "").strip()
    if not original:
        return []

    folded = normalize_text(original)
    phrases: list[str] = []
    seen: set[str] = set()

    # 1) The concept aliases that really occur in the topic.
    for concept in concepts:
        spec = CONCEPTS.get(concept, {})
        for alias in list(spec.get("aliases", [])) + list(spec.get("subtopics", [])):
            alias_folded = normalize_text(alias).strip()
            if not alias_folded or len(alias_folded.split()) < 2:
                continue
            if alias_folded not in folded:
                continue
            # Recover the original spelling from the folded topic.
            phrase = _restore_spelling(original, alias_folded)
            key = normalize_text(phrase)
            if key and key not in seen:
                seen.add(key)
                phrases.append(phrase)

    # 2) The compound groups of the topic itself.
    words = original.split()
    folded_words = [normalize_text(w) for w in words]
    index = 0
    while index < len(words):
        length = 1
        # Extend while the next word is a compound head of the previous.
        while (
            index + length < len(words)
            and folded_words[index + length] in COMPOUND_HEADS
        ):
            length += 1
        if length >= 2:
            phrase = " ".join(words[index:index + length]).strip(".,!?;:")
            key = normalize_text(phrase)
            if key and key not in seen:
                seen.add(key)
                phrases.append(phrase)
            index += length
        else:
            index += 1

    # 3) The compounds that end with a known head ("máy ống kính").
    # The head is found first, then the run is extended backwards over the
    # words that qualify it.
    for head_index, head in enumerate(folded_words):
        if head not in COMPOUND_HEADS:
            continue
        start = head_index
        while start > 0 and folded_words[start - 1] not in PARTICLE_WORDS:
            # The previous word is itself a head: it either belongs to this
            # compound ("ống kính") or it already ends a complete one.
            if folded_words[start - 1] in COMPOUND_HEADS:
                if start - 1 > 0 and folded_words[start - 2] not in PARTICLE_WORDS:
                    start -= 1
                    break
                break
            start -= 1
            if head_index - start >= 2:
                break
        if head_index - start + 1 < 2:
            continue
        phrase = " ".join(words[start:head_index + 1]).strip(".,!?;:")
        key = normalize_text(phrase)
        if key and key not in seen:
            seen.add(key)
            phrases.append(phrase)

    return phrases

def _restore_spelling(original: str, folded_phrase: str) -> str:
    """Return the original spelling of a folded phrase found in the text."""
    folded_original = normalize_text(original)
    position = folded_original.find(folded_phrase)
    if position < 0:
        return folded_phrase
    # The folded text and the original have the same word count, because the
    # fold only replaces characters inside a word.
    prefix_words = folded_original[:position].split()
    target_words = folded_phrase.split()
    original_words = original.split()
    start = len(prefix_words)
    if start + len(target_words) <= len(original_words):
        return " ".join(original_words[start:start + len(target_words)])
    return folded_phrase


# ---------------------------------------------------------------------------
# Query plan
# ---------------------------------------------------------------------------

@dataclass
class PlannedQuery:
    """One search direction of a plan."""

    query: str
    group: str
    reason: str
    intent: str = ""
    concepts: list[str] = field(default_factory=list)
    weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "group": self.group,
            "reason": self.reason,
            "intent": self.intent,
            "concepts": list(self.concepts),
            "weight": round(float(self.weight), 3),
        }


@dataclass
class QueryPlan:
    """The full plan: intent, dimensions and the queries to run."""

    topic: str
    intent: TopicIntent
    queries: list[PlannedQuery] = field(default_factory=list)
    dimensions: list[str] = field(default_factory=list)
    confidence: str = "medium"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "intent": self.intent.to_dict(),
            "queries": [q.to_dict() for q in self.queries],
            "dimensions": list(self.dimensions),
            "confidence": self.confidence,
            "notes": list(self.notes),
            "query_count": len(self.queries),
        }

    def query_texts(self) -> list[str]:
        return [q.query for q in self.queries]


def _english_words(concept: str) -> list[str]:
    spec = CONCEPTS.get(concept, {})
    return list(spec.get("english", []))


def _intent_words(intent: str) -> list[str]:
    return list(INTENT_PATTERNS.get(intent, []))


def _is_category_concept(concept: str) -> bool:
    """Return True when a concept names a CATEGORY, not a subject.

    "review", "music", "travel" and "tutorial" describe the kind of
    content, so searching for them alone would return everything. Their
    English form therefore has to be anchored with a word of the topic.
    A compound concept ("home baking", "smartphone filming") already names
    a subject and can be searched on its own.
    """
    canonical = CONCEPTS.get(concept, {}).get("canonical", concept)
    words = [w for w in normalize_text(canonical).split() if w]
    if len(words) != 1:
        return False
    return words[0] in GENERIC_WORDS or words[0] in CONCEPT_CATEGORY_WORDS


def build_query_plan(
    topic: str,
    *,
    max_queries: int = DEFAULT_QUERY_TARGET,
    hard_ceiling: int = MAX_QUERIES,
) -> QueryPlan:
    """Build the deterministic query plan for one topic.

    The plan never returns fewer than the topic itself (the user's own
    words are the strongest evidence) and never returns more than the hard
    ceiling. Equivalent queries are removed, and the remaining queries are
    ranked by how likely they are to belong to the topic.
    """
    original = str(topic or "").strip()
    intent = analyze_intent(original)
    notes = list(intent.notes)

    ceiling = max(MIN_QUERIES, min(int(max_queries or DEFAULT_QUERY_TARGET), int(hard_ceiling or MAX_QUERIES)))
    ceiling = min(ceiling, MAX_QUERIES)

    candidates: list[PlannedQuery] = []

    # --- Dimension 1: the topic itself, in the user's own words. -----------
    if original:
        candidates.append(PlannedQuery(
            query=original,
            group="topic",
            reason="Chính chủ đề người dùng đặt ra — tín hiệu mạnh nhất.",
            intent=",".join(intent.intents),
            concepts=list(intent.concepts),
            weight=1.0,
        ))

    # --- Dimension 2: subject + intent. ------------------------------------
    # The subject keeps the original spelling of the topic. Only the intent
    # word is appended, and only when it does not repeat a word the subject
    # already carries.
    subject = intent.subject.strip()
    subject_folded = set(normalize_text(subject).split())
    for name in intent.intents:
        for word in _intent_words(name)[:2]:
            if not subject:
                break
            # Do not append a word the subject already contains.
            if normalize_text(word).split()[0] in subject_folded:
                continue
            query = f"{subject} {word}".strip()
            candidates.append(PlannedQuery(
                query=query,
                group=f"intent:{name}",
                reason=f"Từ khóa chủ đề kèm dạng nội dung '{name}'.",
                intent=name,
                concepts=list(intent.concepts),
                weight=0.9,
            ))
            break

    # --- Dimension 3: concept in its English form. ------------------------
    # A Vietnamese topic needs its English equivalent, because most of the
    # source content is captioned in English.
    #
    # HONESTY: an English phrase that names no subject at all ("step by step
    # guide") would match almost anything on the source. Such a phrase is
    # only used when it is anchored with a word of the topic, so every query
    # in the plan still points at the subject the user asked about.
    #
    # The anchor is the subject GROUP first ("điện thoại", "Du lịch"), because
    # half of a compound ("thoại", "Du") names the wrong thing on its own.
    # The SHORTEST usable group wins: the whole topic as an anchor would
    # only repeat the topic and tell the source nothing new.
    anchor_token = ""
    usable_phrases = []
    for phrase in intent.subject_phrases:
        phrase_folded = normalize_text(phrase)
        words = phrase_folded.split()
        if not words:
            continue
        if all(word in GENERIC_WORDS or word in ACTION_WORDS for word in words):
            continue
        if all(word in PARTICLE_WORDS for word in words):
            continue
        usable_phrases.append(phrase)
    if usable_phrases:
        usable_phrases.sort(key=lambda p: (len(p.split()), -len(p)))
        anchor_token = usable_phrases[0]
    if not anchor_token:
        for token in intent.subject_tokens:
            token_folded = normalize_text(token)
            if not token_folded or token_folded in GENERIC_WORDS:
                continue
            if token_folded in ACTION_WORDS or token_folded in PARTICLE_WORDS:
                continue
            anchor_token = token
            break
    if not anchor_token:
        # No concrete noun: fall back to any non-generic subject word.
        for token in intent.subject_tokens:
            token_folded = normalize_text(token)
            if token_folded and token_folded not in GENERIC_WORDS:
                if token_folded in PARTICLE_WORDS:
                    continue
                anchor_token = token
                break
    if not anchor_token:
        anchor_token = intent.subject.strip()

    for concept in intent.concepts:
        canonical = CONCEPTS.get(concept, {}).get("canonical", concept)
        category = _is_category_concept(concept)
        for word in _english_words(concept):
            # A phrase that names no subject, or a concept that is only a
            # category, has to carry a word of the topic. Otherwise the
            # source returns everything and the plan lies about it.
            if _is_generic_phrase(word) or category:
                if not anchor_token:
                    continue
                query = f"{anchor_token} {word}".strip()
                reason = (
                    f"Khái niệm '{canonical}' được diễn đạt bằng tiếng Anh "
                    f"'{word}', gắn với từ khóa '{anchor_token}' của chủ đề để "
                    "không tìm nhầm nội dung chung chung."
                )
            else:
                query = f"{word}"
                reason = (
                    f"Khái niệm '{canonical}' được diễn đạt bằng tiếng Anh "
                    f"'{word}' để tìm cả nguồn tiếng Anh."
                )
            candidates.append(PlannedQuery(
                query=query,
                group=f"concept:{concept}",
                reason=reason,
                intent=",".join(intent.intents),
                concepts=[concept],
                weight=0.85,
            ))
            break

    # --- Dimension 4: concept + intent (the "how to" angle). --------------
    for concept in intent.concepts:
        canonical = CONCEPTS.get(concept, {}).get("canonical", concept)
        category = _is_category_concept(concept)
        for name in intent.intents:
            words = _intent_words(name)
            if not words:
                continue
            # A concept that already names the intent is not repeated.
            if normalize_text(words[0]) in normalize_text(canonical):
                continue
            if category or _is_generic_phrase(canonical):
                # A category concept needs the subject to stay specific.
                if not anchor_token:
                    continue
                query = f"{anchor_token} {canonical} {words[0]}".strip()
            else:
                query = f"{canonical} {words[0]}".strip()
            candidates.append(PlannedQuery(
                query=query,
                group=f"concept_intent:{concept}:{name}",
                reason=(
                    f"Khái niệm '{canonical}' theo góc nhìn '{name}' — "
                    "mở rộng góc tìm kiếm, không đổi chủ đề."
                ),
                intent=name,
                concepts=[concept],
                weight=0.8,
            ))
            break

    # --- Dimension 5: subject token + concept (sub-topic angle). -----------
    for token in intent.subject_tokens:
        for concept in intent.concepts:
            canonical = CONCEPTS.get(concept, {}).get("canonical", concept)
            # The token must add something the canonical name does not say.
            if normalize_text(token) in normalize_text(canonical):
                continue
            query = f"{token} {canonical}".strip()
            candidates.append(PlannedQuery(
                query=query,
                group=f"subtopic:{concept}",
                reason=(
                    f"Từ khóa '{token}' của chủ đề kết hợp khái niệm "
                    f"'{canonical}' — tìm góc phụ cụ thể."
                ),
                intent=",".join(intent.intents),
                concepts=[concept],
                weight=0.7,
            ))
            break

    # --- Dimension 6: the practical angle. --------------------------------
    # The angle that shows the topic being done, not only explained.
    for concept in intent.concepts:
        canonical = CONCEPTS.get(concept, {}).get("canonical", concept)
        if _is_generic_phrase(canonical):
            if not anchor_token:
                continue
            query = f"{anchor_token} {canonical} ideas".strip()
        else:
            query = f"{canonical} ideas".strip()
        candidates.append(PlannedQuery(
            query=query,
            group=f"practical:{concept}",
            reason=(
                f"'{canonical}' theo góc thực hành — tìm ví dụ và cách làm "
                "thực tế thay vì chỉ lý thuyết."
            ),
            intent=",".join(intent.intents),
            concepts=[concept],
            weight=0.6,
        ))
        break

    # --- Dimension 7: the honest fallback. --------------------------------
    # A topic whose subject the dictionary does not know still deserves a
    # real plan. The subject words themselves are combined with the intent
    # words, so the run still searches the user's subject from several
    # angles instead of collapsing to one literal query.
    if len(candidates) < MIN_QUERIES + 2:
        fallback_terms: list[str] = []
        for phrase in intent.subject_phrases:
            if phrase not in fallback_terms:
                fallback_terms.append(phrase)
        for token in intent.subject_tokens:
            token_folded = normalize_text(token)
            if not token_folded or token_folded in GENERIC_WORDS:
                continue
            if token_folded in PARTICLE_WORDS or token_folded in ACTION_WORDS:
                continue
            if token not in fallback_terms:
                fallback_terms.append(token)
        for term in fallback_terms:
            for name in intent.intents:
                words = _intent_words(name)
                if not words:
                    continue
                for word in words[:2]:
                    if normalize_text(word).split()[0] in {normalize_text(t) for t in intent.subject_tokens}:
                        continue
                    candidates.append(PlannedQuery(
                        query=f"{term} {word}".strip(),
                        group=f"fallback:{name}",
                        reason=(
                            f"Từ khóa '{term}' của chủ đề kết hợp dạng nội dung "
                            f"'{name}' — chủ đề chưa có khái niệm riêng trong từ điển."
                        ),
                        intent=name,
                        concepts=[],
                        weight=0.55,
                    ))
                    break
                break

    # --- Deduplicate and rank. --------------------------------------------
    seen: set[str] = set()
    unique: list[PlannedQuery] = []
    for item in candidates:
        key = normalize_text(item.query).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(item)

    unique.sort(key=lambda item: (-item.weight, item.query.lower()))

    # The topic always comes first: it is the user's own wording.
    unique.sort(key=lambda item: 0 if item.group == "topic" else 1)

    plan = QueryPlan(
        topic=original,
        intent=intent,
        queries=unique[:ceiling],
        notes=notes,
    )
    plan.dimensions = _dimensions_of(plan)

    if len(unique) < len(candidates):
        plan.notes.append(
            f"{len(candidates) - len(unique)} truy vấn trùng nhau đã được loại bỏ."
        )
    plan.notes.append(f"Kế hoạch có {len(plan.queries)} truy vấn (tối đa cho phép {ceiling}).")
    if not intent.concepts:
        plan.confidence = "low"
    elif len(intent.concepts) >= 2:
        plan.confidence = "high"
    return plan


def _dimensions_of(plan: QueryPlan) -> list[str]:
    """Return the readable list of search dimensions of a plan."""
    labels: list[str] = []
    for item in plan.queries:
        if item.group == "topic":
            labels.append("Chủ đề gốc")
        elif item.group.startswith("intent:"):
            labels.append(f"Góc ý định: {item.group.split(':', 1)[1]}")
        elif item.group.startswith("concept_intent:"):
            parts = item.group.split(":")
            labels.append(f"{parts[1]} + {parts[2]}")
        elif item.group.startswith("concept:"):
            labels.append(f"Khái niệm: {item.group.split(':', 1)[1]}")
        elif item.group.startswith("subtopic:"):
            labels.append(f"Góc phụ: {item.group.split(':', 1)[1]}")
        elif item.group.startswith("practical:"):
            labels.append(f"Góc thực hành: {item.group.split(':', 1)[1]}")
    # Keep the order but remove duplicates.
    return list(dict.fromkeys(labels))


def plan_to_dict(plan: QueryPlan) -> dict[str, Any]:
    """Serialize a plan for storage in a run snapshot."""
    return plan.to_dict()


def expand_topic_queries(topic: str, max_queries: int = DEFAULT_QUERY_TARGET) -> list[str]:
    """Return the query texts of the plan for one topic.

    This keeps the old call shape working. The plan itself carries the
    reasons, so the caller that needs them uses ``build_query_plan``.
    """
    plan = build_query_plan(topic, max_queries=max_queries)
    return plan.query_texts()


__all__ = [
    "CONCEPTS",
    "DEFAULT_QUERY_TARGET",
    "INTENT_PATTERNS",
    "MAX_QUERIES",
    "PlannedQuery",
    "QueryPlan",
    "TopicIntent",
    "analyze_intent",
    "build_query_plan",
    "expand_topic_queries",
    "normalize_text",
    "plan_to_dict",
    "tokenize",
]

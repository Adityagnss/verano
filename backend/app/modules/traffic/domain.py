"""
Traffic: the pure rules (no I/O), see ADR 0031 and ADR 0032.

Everything here is a plain function over plain values, so it is quick to run and easy to check:
- reading text out of the different shapes a prompt or an answer comes in (a string, a list of chat messages, a
  JSON reply), time stamps, ratings;
- removing personal data (emails, phone numbers, card-like numbers and the owner's own patterns) and cutting every
  field to its size cap with a flag that says it was cut;
- the "topic" of a question, folding near-duplicates, and how a trace's checks combine into one result;
- choosing a sample of live traffic by a stable hash, so the same trace is always in or out;
- the drift test behind alerts: a rolling window, a sequential likelihood-ratio test and the "more than one bad
  day" rule, plus quiet hours.
"""

import hashlib
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

# ----------------------------------------------------------------------------------------------- records


@dataclass
class TraceRecord:
    """One model call or one request to the user's app, as read from any source, before cleaning."""

    external_id: str | None
    started_at: datetime | None
    input_text: str
    output_text: str
    status: str = "ok"
    error_message: str | None = None
    latency_ms: int | None = None
    model: str | None = None
    prompt_version: str | None = None
    rating: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    cost: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Problem:
    """Something wrong with one record of a file, in words a person can act on."""

    record: int
    message: str


@dataclass
class ParseResult:
    records: list[TraceRecord] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)
    found: int = 0
    ignored: int = 0


# ----------------------------------------------------------------------------------------------- reading text

ANSWER_KEYS: Final = ("answer", "output", "text", "response", "result", "reply", "completion", "message", "content")
QUESTION_KEYS: Final = ("question", "query", "input", "prompt", "message", "text", "content", "user_input", "q")


def compact(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        return str(value)


def _content_text(content: Any) -> str:
    """The text of one chat message's content: a string, or a list of parts such as {"type": "text", "text": ...}."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    if isinstance(content, dict):
        text = content.get("text") or content.get("content")
        return text if isinstance(text, str) else compact(content)
    return "" if content is None else str(content)


def message_list(value: Any) -> list[dict[str, Any]] | None:
    """The value as a list of chat messages ({"role", "content"}), or None when it is not one."""
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith("["):
            return None
        try:
            value = json.loads(text)
        except ValueError:
            return None
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        messages = [item for item in value if "role" in item or "content" in item or "parts" in item]
        return messages or None
    return None


def last_message_text(messages: list[dict[str, Any]], roles: Sequence[str]) -> str:
    for message in reversed(messages):
        if str(message.get("role", "")).lower() in roles:
            body = message.get("content")
            if body is None and isinstance(message.get("parts"), list):
                body = message["parts"]
            text = _content_text(body)
            if text.strip():
                return text
    return ""


def input_text_of(value: Any) -> str:
    """What a person asked, from whatever the source stored: text, chat messages or a JSON object."""
    if value is None or value == {} or value == []:
        return ""
    messages = message_list(value)
    if messages is not None:
        text = last_message_text(messages, ("user", "human"))
        if text:
            return text
        return _content_text([m.get("content") for m in messages])
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return value
            return input_text_of(parsed)
        return value
    if isinstance(value, dict):
        for key in ("messages", "input_messages"):
            if key in value:
                text = input_text_of(value[key])
                if text:
                    return text
        for key in QUESTION_KEYS:
            if isinstance(value.get(key), str) and value[key].strip():
                return str(value[key])
        for key in QUESTION_KEYS:
            if key in value and value[key] is not None:
                nested = input_text_of(value[key])
                if nested:
                    return nested
        return compact(value)
    if isinstance(value, list):
        return "\n".join(part for part in (input_text_of(item) for item in value) if part)
    return str(value)


def output_text_of(value: Any) -> str:
    """What the app or model answered, from a string, chat messages, an OpenAI or Anthropic reply or a JSON object."""
    if value is None or value == {} or value == []:
        return ""
    messages = message_list(value)
    if messages is not None:
        text = last_message_text(messages, ("assistant", "ai", "model"))
        if text:
            return text
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
            except ValueError:
                return value
            if isinstance(parsed, dict):
                return output_text_of(parsed)
        return value
    if isinstance(value, dict):
        choices = value.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            first = choices[0]
            message = first.get("message")
            if isinstance(message, dict):
                text = _content_text(message.get("content"))
                if text:
                    return text
            if isinstance(first.get("text"), str):
                return str(first["text"])
        content = value.get("content")
        if isinstance(content, list):
            text = _content_text(content)
            if text:
                return text
        for key in ANSWER_KEYS:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        for key in ANSWER_KEYS:
            item = value.get(key)
            if isinstance(item, dict | list):
                nested = output_text_of(item)
                if nested:
                    return nested
        return compact(value)
    if isinstance(value, list):
        return "\n".join(part for part in (output_text_of(item) for item in value) if part)
    return str(value)


def lookup(data: Any, path: str) -> Any:
    """A value from nested objects by a dotted name; a key that itself contains dots wins over splitting."""
    if not isinstance(data, dict):
        return None
    if path in data:
        return data[path]
    head, _, rest = path.partition(".")
    while rest:
        if head in data:
            return lookup(data[head], rest)
        part, _, rest = rest.partition(".")
        head = f"{head}.{part}"
    return data.get(head)


# ----------------------------------------------------------------------------------------------- time, numbers


def parse_timestamp(value: Any) -> datetime | None:
    """A date and time from an ISO string, or from epoch seconds, milliseconds, microseconds or nanoseconds."""
    if value is None or isinstance(value, bool):
        return None
    number: float | None = None
    if isinstance(value, int | float):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.fullmatch(r"-?\d+(\.\d+)?", text):
            number = float(text)
        else:
            try:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    if number is None or number <= 0:
        return None
    for limit, divisor in ((1e11, 1.0), (1e14, 1e3), (1e17, 1e6)):
        if number < limit:
            number /= divisor
            break
    else:
        number /= 1e9
    try:
        return datetime.fromtimestamp(number, UTC)
    except (OverflowError, OSError, ValueError):
        return None


def milliseconds_between(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None or end < start:
        return None
    return round((end - start).total_seconds() * 1000)


def to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


POSITIVE_WORDS: Final = frozenset({"good", "positive", "up", "thumbs_up", "thumbsup", "like", "yes", "true", "correct"})
NEGATIVE_WORDS: Final = frozenset({"bad", "negative", "down", "thumbs_down", "thumbsdown", "dislike", "no", "false"})


def normalize_rating(value: Any) -> float | None:
    """A person's rating as 0 (bad) to 1 (good). Thumbs, 0 to 1, 1 to 5 stars and -1 to 1 are understood."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, str):
        word = value.strip().lower().replace(" ", "_")
        if word in POSITIVE_WORDS:
            return 1.0
        if word in NEGATIVE_WORDS:
            return 0.0
    number = to_float(value)
    if number is None:
        return None
    if number == -1.0:
        return 0.0
    if 0.0 <= number <= 1.0:
        return number
    if 1.0 < number <= 5.0:
        return (number - 1.0) / 4.0
    return None


FEEDBACK_NAMES: Final = ("feedback", "rating", "thumb", "user_score", "helpful", "satisf")


def is_feedback_name(name: str) -> bool:
    lowered = name.lower()
    return any(word in lowered for word in FEEDBACK_NAMES)


# ----------------------------------------------------------------------------------------------- sizes


def clip(text: str, limit: int) -> tuple[str, bool]:
    """The text cut to `limit` characters, and whether it was cut."""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def bound_meta(meta: dict[str, Any], max_chars: int, depth: int = 0) -> tuple[dict[str, Any], bool]:
    """Small metadata: at most 40 keys, three levels deep, text values cut to 500 characters, and the whole thing
    within `max_chars` when written out. The flag says anything was dropped or cut."""
    cut = False
    out: dict[str, Any] = {}
    for index, (key, value) in enumerate(meta.items()):
        if index >= 40:
            cut = True
            break
        name = str(key)[:100]
        if isinstance(value, str):
            text, was_cut = clip(value, 500)
            out[name] = text
            cut = cut or was_cut
        elif isinstance(value, bool | int | float) or value is None:
            out[name] = value
        elif isinstance(value, dict) and depth < 2:
            inner, inner_cut = bound_meta(value, max_chars, depth + 1)
            out[name] = inner
            cut = cut or inner_cut
        elif isinstance(value, list):
            items = [item if isinstance(item, bool | int | float) else str(item)[:200] for item in value[:20]]
            out[name] = items
            cut = cut or len(value) > 20
        else:
            out[name] = str(value)[:200]
            cut = True
    if depth == 0:
        while len(compact(out)) > max_chars and out:
            out.popitem()
            cut = True
    return out, cut


# ----------------------------------------------------------------------------------------------- personal data

EMAIL: Final = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
CARD_CANDIDATE: Final = re.compile(r"(?<![\w-])\d(?:[ -]?\d){12,18}(?![\w-])")
PHONE_CANDIDATE: Final = re.compile(r"(?<![\w.])\+?\d[\d\s().\-]{7,20}\d(?![\w])")
NESTED_QUANTIFIER: Final = re.compile(r"\([^)]*[+*][^)]*\)\s*[+*{]")
MAX_PATTERNS: Final = 10
MAX_PATTERN_CHARS: Final = 200


@dataclass(frozen=True)
class ScrubConfig:
    enabled: bool = True
    emails: bool = True
    phones: bool = True
    cards: bool = True
    patterns: tuple[str, ...] = ()


def luhn_ok(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        number = int(char)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def pattern_problem(pattern: str) -> str | None:
    """A reason the owner's own pattern is refused, or None. Patterns that could run for very long are refused."""
    if not pattern.strip():
        return "A pattern can't be empty."
    if len(pattern) > MAX_PATTERN_CHARS:
        return f"A pattern can be at most {MAX_PATTERN_CHARS} characters."
    if NESTED_QUANTIFIER.search(pattern):
        return "This pattern repeats a repeated group, which can make scrubbing very slow. Simplify it."
    try:
        re.compile(pattern)
    except re.error as error:
        return f"This pattern is not valid: {error}."
    return None


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[card]" if 13 <= len(digits) <= 19 and luhn_ok(digits) else match.group(0)


def _phone(match: re.Match[str]) -> str:
    text = match.group(0)
    digits = re.sub(r"\D", "", text)
    plausible = 9 <= len(digits) <= 15 and (text.startswith("+") or re.search(r"[\s().\-]", text) is not None)
    only_date = re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) is not None
    return "[phone]" if plausible and not only_date else text


def scrub_text(text: str, config: ScrubConfig) -> tuple[str, int]:
    """The text with personal data replaced by a label such as [email], and how many were replaced."""
    if not config.enabled or not text:
        return text, 0
    total = 0
    steps: list[tuple[re.Pattern[str], Callable[[re.Match[str]], str]]] = []
    if config.cards:
        steps.append((CARD_CANDIDATE, _card))
    if config.emails:
        steps.append((EMAIL, lambda _m: "[email]"))
    if config.phones:
        steps.append((PHONE_CANDIDATE, _phone))
    for pattern in config.patterns:
        if pattern_problem(pattern) is None:
            steps.append((re.compile(pattern), lambda _m: "[hidden]"))
    for regex, replace in steps:
        found = 0

        def counted(match: re.Match[str], replace: Callable[[re.Match[str]], str] = replace) -> str:
            nonlocal found
            new = replace(match)
            if new != match.group(0):
                found += 1
            return new

        text = regex.sub(counted, text)
        total += found
    return text, total


def scrub_value(value: Any, config: ScrubConfig) -> tuple[Any, int]:
    """The same for every text inside a nested value (object keys are kept)."""
    if isinstance(value, str):
        return scrub_text(value, config)
    if isinstance(value, dict):
        total = 0
        out: dict[str, Any] = {}
        for key, item in value.items():
            out[key], count = scrub_value(item, config)
            total += count
        return out, total
    if isinstance(value, list):
        total = 0
        items = []
        for item in value:
            new, count = scrub_value(item, config)
            items.append(new)
            total += count
        return items, total
    return value, 0


# ----------------------------------------------------------------------------------------------- topics, folding

WORD: Final = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
STOP_WORDS: Final = frozenset(
    [
        "that",
        "this",
        "with",
        "from",
        "have",
        "your",
        "what",
        "when",
        "where",
        "which",
        "would",
        "could",
        "should",
        "about",
        "please",
        "there",
        "their",
        "them",
        "they",
        "will",
        "been",
        "were",
        "into",
        "than",
        "then",
        "also",
        "just",
        "like",
        "need",
        "want",
        "help",
        "does",
        "doesn",
        "know",
        "tell",
        "make",
        "some",
        "more",
        "most",
        "very",
        "much",
        "many",
        "here",
        "over",
        "only",
        "other",
        "such",
        "each",
    ]
)


def topic_hash(text: str) -> str:
    """A short label for what a question is about: its three most telling words, in order of the alphabet. Questions
    on the same subject share a label, and a label never seen before marks a new topic."""
    counts: dict[str, int] = {}
    for word in WORD.findall(text.lower()):
        if word not in STOP_WORDS:
            counts[word] = counts.get(word, 0) + 1
    ranked = sorted(counts, key=lambda w: (-counts[w], -len(w), w))[:3]
    if not ranked:
        return hashlib.blake2b(b"", digest_size=6).hexdigest()
    return hashlib.blake2b(" ".join(sorted(ranked)).encode(), digest_size=6).hexdigest()


def fold_duplicates(
    vectors: Sequence[Sequence[float]], known: Sequence[Sequence[float]], threshold: float
) -> list[int]:
    """Which of `vectors` repeat an earlier one or one already in `known`, as the index of the one they fold into
    (-1 when they stand alone). Each is compared with the kept representatives only, so memory stays small
    and the work is at most (items x representatives). Vectors are unit length, so a dot product is the similarity."""
    kept: list[Sequence[float]] = list(known)
    kept_index: list[int] = [-2] * len(known)
    placed: list[int] = []
    for index, vector in enumerate(vectors):
        best, best_at = threshold, None
        for at, other in enumerate(kept):
            similarity = sum(a * b for a, b in zip(vector, other, strict=True))
            if similarity > best:
                best, best_at = similarity, at
        if best_at is None:
            kept.append(vector)
            kept_index.append(index)
            placed.append(-1)
        else:
            placed.append(kept_index[best_at])
    return placed


# ----------------------------------------------------------------------------------------------- sampling, scores

DAY_ONE: Final = date(1970, 1, 1)


def sample_bucket(key: str, salt: str) -> float:
    """A number in [0, 1) that depends only on the key and the salt, the same on every machine and every run."""
    digest = hashlib.blake2b(f"{salt}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(digest) / 2**64


def in_sample(key: str, rate: float, salt: str) -> bool:
    """Whether this trace is in a sample of the given rate. The same trace is always in or always out, and a
    higher rate only adds traces (every trace in a 5% sample is also in a 10% sample)."""
    if rate <= 0:
        return False
    if rate >= 1:
        return True
    return sample_bucket(key, salt) < rate


@dataclass(frozen=True)
class CheckResult:
    name: str
    value: float
    passed: bool
    required: bool
    weight: float
    judged: bool = False


def combine_checks(results: Sequence[CheckResult]) -> tuple[float | None, bool | None]:
    """One quality number (the weighted mean) and one pass/fail for a trace from its checks. A trace passes when
    every required check passed and at least one check scored; nothing scored gives (None, None)."""
    if not results:
        return None, None
    weight = sum(max(r.weight, 0.0) for r in results)
    quality = sum(r.value * max(r.weight, 0.0) for r in results) / weight if weight > 0 else None
    if quality is None:
        quality = sum(r.value for r in results) / len(results)
    required = [r for r in results if r.required]
    passed = all(r.passed for r in required) if required else all(r.passed for r in results)
    return round(quality, 4), passed


def month_start(now: datetime) -> datetime:
    return datetime(now.year, now.month, 1, tzinfo=UTC)


def judge_allowance(limit: int, used: int, wanted: int) -> int:
    """How many more traces may be judged this month."""
    return max(0, min(wanted, limit - used))


# ----------------------------------------------------------------------------------------------- drift and alerts

BOUNDARY_ALPHA: Final = 0.05
BOUNDARY_BETA: Final = 0.05
LLR_BOUNDARY: Final = math.log((1 - BOUNDARY_BETA) / BOUNDARY_ALPHA)
MIN_DAY_SAMPLES: Final = 5


@dataclass(frozen=True)
class DayPoint:
    """One day of live traffic: how many traces counted and how many of them were good."""

    day: date
    good: int
    total: int

    @property
    def rate(self) -> float | None:
        return self.good / self.total if self.total else None


@dataclass(frozen=True)
class Verdict:
    breached: bool
    recovered: bool
    reference: float | None
    window_rate: float | None
    window_total: int
    bad_days: int
    llr: float | None
    reason: str


def log_likelihood_ratio(good: int, total: int, reference: float, margin: float) -> float:
    """Evidence that the true rate is `margin` below `reference` rather than at it (Wald's sequential test): the sum
    over traces of the log of how much likelier each outcome is under the lower rate."""
    p0 = min(max(reference, 0.02), 0.98)
    p1 = min(max(reference - margin, 0.01), p0 - 0.005)
    return good * math.log(p1 / p0) + (total - good) * math.log((1 - p1) / (1 - p0))


def _totals(points: Sequence[DayPoint]) -> tuple[int, int]:
    return sum(p.good for p in points), sum(p.total for p in points)


def drift_verdict(
    points: Sequence[DayPoint],
    *,
    kind: str,
    today: date,
    threshold: float,
    margin: float,
    window_days: int,
    baseline_days: int,
    min_samples: int,
    min_bad_days: int,
) -> Verdict:
    """Is the live rate clearly below where it should be?

    The "line" is the owner's threshold (kind `threshold`) or the rate of the baseline days before the window
    (kind `drop`). The rolling window is the last `window_days` days up to `today`. The window counts as a breach only
    when all three hold: it has at least `min_samples` traces, the sequential test has seen enough evidence that the
    rate is `margin` below the line, and at least `min_bad_days` separate days sit below the line by half the margin.
    The last condition is what keeps one bad day from alerting, however loud that day was."""
    window_start = today - timedelta(days=window_days - 1)
    window = [p for p in points if window_start <= p.day <= today]
    good, total = _totals(window)
    window_rate = good / total if total else None
    if kind == "drop":
        base = [p for p in points if window_start - timedelta(days=baseline_days) <= p.day < window_start]
        base_good, base_total = _totals(base)
        if base_total < min_samples:
            return Verdict(
                False, False, None, window_rate, total, 0, None, "Not enough earlier traffic to compare with yet."
            )
        reference = base_good / base_total
    else:
        reference = threshold
    if total < min_samples or window_rate is None:
        return Verdict(False, False, reference, window_rate, total, 0, None, "Not enough traffic in the window yet.")
    llr = log_likelihood_ratio(good, total, reference, margin)
    day_line = reference - margin / 2
    bad_days = sum(1 for p in window if p.total >= MIN_DAY_SAMPLES and p.rate is not None and p.rate < day_line)
    breached = llr >= LLR_BOUNDARY and bad_days >= min_bad_days
    recovered = not breached and window_rate >= reference - margin / 2
    if breached:
        reason = (
            f"The last {window_days} days scored {window_rate:.0%} over {total} traces, below the line of "
            f"{reference:.0%}, and {bad_days} days were below it."
        )
    elif llr >= LLR_BOUNDARY:
        reason = "A drop, but on fewer than the required number of days, so it is not an alert yet."
    else:
        reason = "Within the expected range."
    return Verdict(breached, recovered, reference, window_rate, total, bad_days, llr, reason)


def in_quiet_hours(now: datetime, start_hour: int | None, end_hour: int | None, utc_offset_min: int) -> bool:
    """Whether `now` falls in the owner's quiet hours (local hours start to end, wrapping past midnight)."""
    if start_hour is None or end_hour is None or start_hour == end_hour:
        return False
    local = now.astimezone(UTC) + timedelta(minutes=utc_offset_min)
    hour = local.hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour

"""
More rule evaluators (same contract as rules.py): deterministic, free checks on one output.

- Text checks: `contains_all`, `contains_any`, `not_contains`, `regex_match`, `regex_absent`, `starts_with`,
  `ends_with`, `char_length`, `word_count`, `numeric_close`, `no_pii`, `valid_url`, `valid_xml`, `valid_yaml`.
- Closeness to the expected answer (a 0..1 value judged against the threshold): `token_overlap_f1`,
  `edit_similarity`, `bleu`, `rouge_l`. Each is written here from its published definition.
- Tool-call checks over what the user's app reported: `tool_called`, `tool_not_called`, `tool_order`,
  `max_tool_calls`.
- `RULE_INFO` describes every rule (these and the ones in rules.py) so the UI can offer a rule picker.
Rules register themselves with the `rule` decorator of rules.py, which must never import this file: whoever wires
the rules imports this module once. A rule returns None when it does not apply (missing config, no expected answer).
Decisions: `valid_xml` refuses DTDs and entity declarations (so entity-expansion attacks cannot run); `no_pii` names
the kind of personal data found and never prints the matched text; text longer than `MAX_SIMILARITY_CHARS` is cut
before the quadratic edit-distance work.
"""

import math
import re
import xml.parsers.expat as expat
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

import yaml

from app.modules.evaluation.domain import EvalCase, Score, score
from app.modules.evaluation.plugins.rules import rule

MAX_SIMILARITY_CHARS = 2000
MAX_BLEU_ORDER = 4
URL_SCHEMES = {"http", "https"}
MIN_PHONE_DIGITS = 8
CARD_DIGITS = range(13, 20)
REGEX_FLAGS = {"i": re.IGNORECASE, "s": re.DOTALL, "m": re.MULTILINE}
WORD = re.compile(r"\w+")
NUMBER = re.compile(r"[-+]?(?:\d[\d,]*(?:\.\d+)?|\.\d+)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d(?:[\s().-]?\d){7,}")
CARD = re.compile(r"\d(?:[ -]?\d){12,18}")


def _strings(config: dict[str, Any], key: str) -> list[str] | None:
    values = config.get(key)
    if not isinstance(values, list) or not values:
        return None
    return [str(value) for value in values]


def _text(case: EvalCase, config: dict[str, Any]) -> tuple[str, bool]:
    sensitive = bool(config.get("case_sensitive", False))
    return (case.output if sensitive else case.output.casefold()), sensitive


def _fold(value: str, sensitive: bool) -> str:
    return value if sensitive else value.casefold()


def _pass_fail(ok: bool, threshold: float, good: str, bad: str) -> Score:
    return score(1.0 if ok else 0.0, threshold, good if ok else bad)


def _words(text: str) -> list[str]:
    return WORD.findall(text.casefold())


def _within(count: int, config: dict[str, Any]) -> tuple[bool, str]:
    low, high = config.get("min"), config.get("max")
    if low is not None and count < low:
        return False, f"{count} is below the minimum of {low}; make the answer longer."
    if high is not None and count > high:
        return False, f"{count} is above the maximum of {high}; make the answer shorter."
    return True, f"{count} is within the limits."


@rule("contains_all")
def contains_all(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    values = _strings(config, "values")
    if values is None:
        return None
    text, sensitive = _text(case, config)
    missing = [value for value in values if _fold(value, sensitive) not in text]
    return score(
        (len(values) - len(missing)) / len(values),
        threshold,
        f"Missing: {', '.join(missing)}. Make the answer include them." if missing else "Includes every required text.",
    )


@rule("contains_any")
def contains_any(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    values = _strings(config, "values")
    if values is None:
        return None
    text, sensitive = _text(case, config)
    ok = any(_fold(value, sensitive) in text for value in values)
    return _pass_fail(
        ok, threshold, "Includes one of the required texts.", f"None of these appear: {', '.join(values)}."
    )


@rule("not_contains")
def not_contains(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    values = _strings(config, "values")
    if values is None:
        return None
    text, sensitive = _text(case, config)
    found = [value for value in values if _fold(value, sensitive) in text]
    return _pass_fail(
        not found,
        threshold,
        "Has none of the banned texts.",
        f"Contains banned text: {', '.join(found)}. Tell the model not to say it.",
    )


def _compiled(config: dict[str, Any]) -> re.Pattern[str] | None:
    pattern = config.get("pattern")
    if not isinstance(pattern, str) or not pattern:
        return None
    flags = 0
    for letter in str(config.get("flags", "")).lower():
        flags |= REGEX_FLAGS.get(letter, 0)
    try:
        return re.compile(pattern, flags)
    except re.error:
        return None


@rule("regex_match")
def regex_match(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    pattern = _compiled(config)
    if pattern is None:
        return None
    return _pass_fail(
        pattern.search(case.output) is not None,
        threshold,
        "Matches the pattern.",
        f"Does not match the pattern {pattern.pattern}. Ask for that format.",
    )


@rule("regex_absent")
def regex_absent(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    pattern = _compiled(config)
    if pattern is None:
        return None
    return _pass_fail(
        pattern.search(case.output) is None,
        threshold,
        "Does not match the banned pattern.",
        f"Matches the banned pattern {pattern.pattern}. Tell the model to avoid it.",
    )


@rule("starts_with")
def starts_with(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    value = config.get("value")
    if not isinstance(value, str) or not value:
        return None
    return _pass_fail(
        case.output.lstrip().startswith(value),
        threshold,
        "Starts as required.",
        f"Does not start with '{value}'. Tell the model how to begin.",
    )


@rule("ends_with")
def ends_with(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    value = config.get("value")
    if not isinstance(value, str) or not value:
        return None
    return _pass_fail(
        case.output.rstrip().endswith(value),
        threshold,
        "Ends as required.",
        f"Does not end with '{value}'. Tell the model how to finish.",
    )


@rule("char_length")
def char_length(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if config.get("min") is None and config.get("max") is None:
        return None
    ok, reason = _within(len(case.output.strip()), config)
    return _pass_fail(ok, threshold, f"Characters: {reason}", f"Characters: {reason}")


@rule("word_count")
def word_count(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if config.get("min") is None and config.get("max") is None:
        return None
    ok, reason = _within(len(case.output.split()), config)
    return _pass_fail(ok, threshold, f"Words: {reason}", f"Words: {reason}")


def _f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


@rule("token_overlap_f1")
def token_overlap_f1(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if case.expected is None:
        return None
    output, expected = Counter(_words(case.output)), Counter(_words(case.expected))
    shared = sum((output & expected).values())
    if not shared:
        return score(0.0, threshold, "No words in common with the expected answer.")
    value = _f1(shared / sum(output.values()), shared / sum(expected.values()))
    return score(value, threshold, f"Word overlap with the expected answer is {value:.0%}.")


def _levenshtein(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


@rule("edit_similarity")
def edit_similarity(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if case.expected is None:
        return None
    output, expected = case.output.strip()[:MAX_SIMILARITY_CHARS], case.expected.strip()[:MAX_SIMILARITY_CHARS]
    longest = max(len(output), len(expected))
    value = 1.0 - _levenshtein(output, expected) / longest if longest else 1.0
    return score(value, threshold, f"Text is {value:.0%} similar to the expected answer by character edits.")


def _ngrams(tokens: list[str], order: int) -> Counter[tuple[str, ...]]:
    return Counter(tuple(tokens[i : i + order]) for i in range(len(tokens) - order + 1))


def _bleu(candidate: list[str], reference: list[str]) -> float:
    if not candidate or not reference:
        return 0.0
    log_sum = 0.0
    for order in range(1, MAX_BLEU_ORDER + 1):
        mine, theirs = _ngrams(candidate, order), _ngrams(reference, order)
        clipped = sum((mine & theirs).values())
        log_sum += math.log((clipped + 1) / (sum(mine.values()) + 1))
    penalty = 1.0 if len(candidate) > len(reference) else math.exp(1 - len(reference) / len(candidate))
    return penalty * math.exp(log_sum / MAX_BLEU_ORDER)


@rule("bleu")
def bleu(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if case.expected is None:
        return None
    value = _bleu(_words(case.output), _words(case.expected))
    return score(value, threshold, f"BLEU against the expected answer is {value:.2f}.")


def _lcs_length(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for a in left:
        current = [0]
        for j, b in enumerate(right, start=1):
            current.append(previous[j - 1] + 1 if a == b else max(previous[j], current[j - 1]))
        previous = current
    return previous[-1]


@rule("rouge_l")
def rouge_l(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if case.expected is None:
        return None
    output, expected = _words(case.output), _words(case.expected)
    common = _lcs_length(output, expected) if output and expected else 0
    value = _f1(common / len(output), common / len(expected)) if common else 0.0
    return score(value, threshold, f"ROUGE-L against the expected answer is {value:.2f}.")


def _first_number(text: str) -> float | None:
    found = NUMBER.search(text)
    if found is None:
        return None
    try:
        return float(found.group().replace(",", ""))
    except ValueError:
        return None


@rule("numeric_close")
def numeric_close(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    if case.expected is None:
        return None
    wanted = _first_number(case.expected)
    if wanted is None:
        return None
    got = _first_number(case.output)
    if got is None:
        return score(0.0, threshold, "No number found in the answer. Ask the model to state the number.")
    tolerance = float(config.get("tolerance", 0.0))
    gap = abs(got - wanted)
    allowed = tolerance * abs(wanted) if config.get("relative", False) else tolerance
    return _pass_fail(
        gap <= allowed,
        threshold,
        f"{got:g} is close enough to {wanted:g}.",
        f"{got:g} is not within tolerance of {wanted:g}. Ask for a more careful calculation.",
    )


def _luhn(digits: str) -> bool:
    total = 0
    for position, char in enumerate(reversed(digits)):
        digit = int(char)
        if position % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def _digits(text: str) -> str:
    return "".join(char for char in text if char.isdigit())


def _pii_kinds(text: str) -> list[str]:
    kinds = []
    if EMAIL.search(text):
        kinds.append("an email address")
    cards = [_digits(m.group()) for m in CARD.finditer(text)]
    if any(len(digits) in CARD_DIGITS and _luhn(digits) for digits in cards):
        kinds.append("a payment card number")
    if any(len(_digits(m.group())) >= MIN_PHONE_DIGITS for m in PHONE.finditer(text)):
        kinds.append("a phone number")
    return kinds


@rule("no_pii")
def no_pii(case: EvalCase, config: dict[str, Any], threshold: float) -> Score:
    kinds = _pii_kinds(case.output)
    return _pass_fail(
        not kinds,
        threshold,
        "No email address, phone number or card number found.",
        f"The answer contains {' and '.join(kinds)}. Tell the model never to repeat personal data.",
    )


@rule("valid_url")
def valid_url(case: EvalCase, config: dict[str, Any], threshold: float) -> Score:
    text = case.output.strip()
    try:
        parts = urlsplit(text)
        ok = parts.scheme.lower() in URL_SCHEMES and bool(parts.hostname) and not any(c.isspace() for c in text)
    except ValueError:
        ok = False
    return _pass_fail(
        ok, threshold, "A valid web address.", "Not a single http or https address with a host. Ask for only the URL."
    )


class _ForbiddenXml(ValueError):
    pass


def _forbid(*_: Any) -> None:
    raise _ForbiddenXml("DTDs and entity declarations are not allowed")


def _xml_problem(text: str) -> str | None:
    parser = expat.ParserCreate()
    parser.StartDoctypeDeclHandler = _forbid
    parser.EntityDeclHandler = _forbid
    try:
        parser.Parse(text, True)
    except _ForbiddenXml as exc:
        return str(exc)
    except expat.ExpatError as exc:
        return expat.ErrorString(exc.code)
    return None


@rule("valid_xml")
def valid_xml(case: EvalCase, config: dict[str, Any], threshold: float) -> Score:
    problem = _xml_problem(case.output.strip())
    return _pass_fail(problem is None, threshold, "Well-formed XML.", f"Not valid XML: {problem}. Ask for valid XML.")


@rule("valid_yaml")
def valid_yaml(case: EvalCase, config: dict[str, Any], threshold: float) -> Score:
    try:
        ok = yaml.safe_load(case.output) is not None
    except yaml.YAMLError:
        ok = False
    return _pass_fail(ok, threshold, "Valid YAML.", "Not valid YAML (or empty). Ask for YAML only.")


def _same(left: Any, right: Any) -> bool:
    return bool(left == right or str(left) == str(right))


def _arguments_match(call: dict[str, Any], wanted: dict[str, Any]) -> bool:
    given = call.get("arguments")
    given = given if isinstance(given, dict) else {}
    return all(key in given and _same(given[key], value) for key, value in wanted.items())


def _called_names(case: EvalCase) -> list[str]:
    return [str(call.get("name")) for call in case.tool_calls]


@rule("tool_called")
def tool_called(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    name = config.get("name")
    if not isinstance(name, str) or not name:
        return None
    wanted = config.get("arguments") or {}
    needed = int(config.get("min_times", 1))
    matches = sum(1 for call in case.tool_calls if call.get("name") == name and _arguments_match(call, wanted))
    return _pass_fail(
        matches >= needed,
        threshold,
        f"Called {name} {matches} time(s).",
        f"Called {name} {matches} time(s) with the required arguments, needed {needed}. "
        "Tell the model when to use this tool.",
    )


@rule("tool_not_called")
def tool_not_called(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    names = _strings(config, "names")
    if names is None:
        return None
    used = sorted(set(names) & set(_called_names(case)))
    return _pass_fail(
        not used,
        threshold,
        "None of the forbidden tools were called.",
        f"Called forbidden tool(s): {', '.join(used)}. Tell the model not to use them here.",
    )


@rule("tool_order")
def tool_order(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    names = _strings(config, "names")
    if names is None:
        return None
    remaining = iter(_called_names(case))
    ok = all(name in remaining for name in names)
    return _pass_fail(
        ok,
        threshold,
        "Tools were called in the required order.",
        f"Tools were not called in the order {', '.join(names)}. Spell out the order in the prompt.",
    )


@rule("max_tool_calls")
def max_tool_calls(case: EvalCase, config: dict[str, Any], threshold: float) -> Score | None:
    limit = config.get("limit")
    if limit is None:
        return None
    count = len(case.tool_calls)
    return _pass_fail(
        count <= int(limit),
        threshold,
        f"{count} tool call(s), within the limit of {limit}.",
        f"{count} tool calls, above the limit of {limit}. Tell the model to call fewer tools.",
    )


def _info(title: str, description: str, config: str) -> dict[str, str]:
    return {"title": title, "description": description, "config": config}


RULE_INFO: dict[str, dict[str, str]] = {
    "exact_match": _info(
        "Exact match", "The answer equals the expected answer, ignoring case and punctuation.", "none"
    ),
    "allowed_values": _info(
        "Allowed values", "The answer is one of the allowed labels.", "allowed_outputs (list of labels, optional)"
    ),
    "json_valid": _info("Valid JSON", "The answer is JSON (code fences allowed).", "none"),
    "json_schema": _info(
        "JSON schema", "The answer is JSON that fits a schema.", "output_schema (JSON schema, optional)"
    ),
    "field_match": _info("Field match", "Share of the expected JSON's top-level fields the answer gets right.", "none"),
    "length": _info("Shorter than input", "The answer is shorter than the input it summarizes.", "none"),
    "constraints": _info(
        "Task rules", "The written rules that can be checked mechanically.", "constraints (list of rules, optional)"
    ),
    "contains_all": _info(
        "Contains all",
        "Share of the required texts the answer includes.",
        "values (list), case_sensitive (default false)",
    ),
    "contains_any": _info(
        "Contains any",
        "The answer includes at least one of the texts.",
        "values (list), case_sensitive (default false)",
    ),
    "not_contains": _info(
        "Does not contain",
        "The answer includes none of the banned texts.",
        "values (list), case_sensitive (default false)",
    ),
    "regex_match": _info(
        "Matches pattern", "A regular expression is found in the answer.", "pattern, flags (letters i, s, m)"
    ),
    "regex_absent": _info(
        "Avoids pattern", "A regular expression is not found in the answer.", "pattern, flags (letters i, s, m)"
    ),
    "starts_with": _info("Starts with", "The answer begins with the given text.", "value"),
    "ends_with": _info("Ends with", "The answer ends with the given text.", "value"),
    "char_length": _info(
        "Character length", "The answer's length in characters is within limits.", "min, max (both optional)"
    ),
    "word_count": _info("Word count", "The answer's number of words is within limits.", "min, max (both optional)"),
    "token_overlap_f1": _info("Word overlap", "F1 of words shared with the expected answer.", "none"),
    "edit_similarity": _info(
        "Edit similarity", "One minus the normalized character edit distance to the expected answer.", "none"
    ),
    "bleu": _info("BLEU", "Sentence BLEU (up to 4-grams) against the expected answer.", "none"),
    "rouge_l": _info("ROUGE-L", "Longest common word sequence F-measure against the expected answer.", "none"),
    "numeric_close": _info(
        "Number close",
        "The first number in the answer is close to the expected one.",
        "tolerance (default 0), relative (default false)",
    ),
    "no_pii": _info("No personal data", "No email address, phone number or card number in the answer.", "none"),
    "valid_url": _info("Valid URL", "The answer is a single http or https address.", "none"),
    "valid_xml": _info("Valid XML", "The answer is well-formed XML (no DTDs or entities).", "none"),
    "valid_yaml": _info("Valid YAML", "The answer parses as YAML and is not empty.", "none"),
    "tool_called": _info(
        "Tool called",
        "The app called the tool, optionally with given arguments.",
        "name, arguments (optional), min_times (default 1)",
    ),
    "tool_not_called": _info("Tool not called", "The app called none of the listed tools.", "names (list)"),
    "tool_order": _info("Tool order", "The listed tools were called in this order.", "names (list)"),
    "max_tool_calls": _info("Tool call limit", "The app made no more than this many tool calls.", "limit"),
}

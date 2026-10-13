"""
Which of a Task Spec's plain-English rules can be checked by a program, and how.

A rule is checkable only when it says something a program can count: a word or character limit, a single
word, lowercase, a cap on exclamation marks. A rule that depends on the situation ("under 80 words unless the
customer asks for detailed steps") or on meaning ("never promise anything the policy does not state") is not
checkable here; it is left to the judges, never guessed. Kept free of other modules so both the generator (which
chooses the checks) and the rule evaluator (which runs them) can use it.
"""

import re
from collections.abc import Callable

Check = Callable[[str], bool]

LIMIT_WORDS = r"(?:at most|no more than|max(?:imum)?|under|fewer than)"
WORD_LIMIT = re.compile(rf"{LIMIT_WORDS}\s+(\d+)\s+words?", re.I)
CHAR_LIMIT = re.compile(rf"{LIMIT_WORDS}\s+(\d+)\s+(?:characters|chars)", re.I)
EXCLAMATION_LIMIT = re.compile(
    r"(?:at most|no more than|max(?:imum)?|never (?:use )?more than|not (?:use )?more than)"
    r"\s+(one|two|three|four|five|\d+)\s+exclamation",
    re.I,
)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
# A rule that only applies in some situations cannot be checked on every answer.
CONDITIONAL = re.compile(r"\b(unless|except|only if|only when|if|when|whenever|otherwise)\b", re.I)


def check_for(constraint: str) -> Check | None:
    """A function that says whether an output obeys the rule, or None when a program cannot tell."""
    text = constraint.lower()
    if CONDITIONAL.search(constraint):
        return None
    if "one word" in text or "single word" in text:
        return lambda output: len(output.split()) == 1
    if "lowercase" in text or "lower case" in text:
        return lambda output: output == output.lower()
    if match := WORD_LIMIT.search(constraint):
        words = int(match.group(1))
        return lambda output: len(output.split()) <= words
    if match := CHAR_LIMIT.search(constraint):
        chars = int(match.group(1))
        return lambda output: len(output) <= chars
    if match := EXCLAMATION_LIMIT.search(constraint):
        count = match.group(1).lower()
        limit = NUMBER_WORDS[count] if count in NUMBER_WORDS else int(count)
        return lambda output: output.count("!") <= limit
    return None


def split_rules(constraints: list[str]) -> tuple[list[str], list[str]]:
    """The rules a program can check, and the rest (which the judges are asked to read)."""
    checkable = [c for c in constraints if check_for(c) is not None]
    return checkable, [c for c in constraints if check_for(c) is None]

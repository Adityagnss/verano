"""
Token estimation without a tokenizer.

A deliberately simple characters-per-token estimate (the ratio is a setting). It is used
where an upper-bound guess is enough and speed matters: sizing a request for the rate
limiter's token bucket and checking that a rendered prompt fits a model's context window.
Billing never uses it; costs come from the provider's reported token counts.
"""

from collections.abc import Iterable


def estimate_tokens(texts: Iterable[str], max_output: int | None, chars_per_token: int) -> int:
    return sum(len(text) for text in texts) // chars_per_token + 1 + (max_output or 0)

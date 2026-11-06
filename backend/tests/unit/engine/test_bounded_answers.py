"""A stored answer has a size limit and says when it was cut."""

from decimal import Decimal
from types import SimpleNamespace

from app.core.config import Settings
from app.core.text import bound
from app.modules.apps.caller import AppCaller
from app.modules.apps.mapping import AppReply
from app.modules.apps.runner import AppCallResult


def test_a_short_text_is_kept_and_a_long_one_is_cut_and_flagged() -> None:
    assert bound("hello", 10) == ("hello", False)
    assert bound("x" * 11, 10) == ("x" * 10, True)


def test_an_app_answer_over_the_limit_is_stored_cut_with_the_flag_and_the_reported_cost() -> None:
    caller = object.__new__(AppCaller)
    caller._settings = Settings(_env_file=None, stored_answer_max_chars=50)
    reply = AppReply(answer="y" * 80, chunks=["a chunk"], tool_calls=[], cost=0.002)
    values = caller._single_values(AppCallResult(request_body="{}", status_code=200, latency_ms=12, reply=reply))
    assert values["raw_output"] == "y" * 50
    assert values["output_truncated"] is True
    assert values["retrieved_chunks"] == ["a chunk"]
    assert values["tool_calls"] is None
    assert values["cost"] == Decimal("0.002")


def test_a_failed_app_call_is_a_failed_answer_with_the_reason_never_a_pass() -> None:
    caller = object.__new__(AppCaller)
    caller._settings = SimpleNamespace(stored_answer_max_chars=50)  # type: ignore[assignment]
    values = caller._single_values(
        AppCallResult(request_body="{}", status_code=500, error="The app answered with status 500.")
    )
    assert values["status"].value == "failed"
    assert values["error_message"] == "The app answered with status 500."
    assert "raw_output" not in values

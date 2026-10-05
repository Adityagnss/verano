"""
Mock LLM provider, installed into LiteLLM's custom-provider hook as `mock/<model>`.

Because it sits behind LiteLLM, the gateway treats it exactly like a real provider: same
parameter filtering, rate limiting, retries, cost and recording. Model behavior comes from
`mock_models.yaml`; each behavior is a registered plugin:

- `echo`       returns the last user message
- `scripted`   returns the first fixture response whose regex matches the prompt
- `answer_key` returns the known correct answer with probability `accuracy`, else a wrong one
- `flaky`      fails with seeded 429s, 500s, timeouts or broken JSON, else defers to `inner`;
                `fail_first` scripts exact failures for the first occurrences of a request

Randomness is seeded from the configured seed, the model, the request and how many times
that exact request has been seen, so a test run is identical every time while a retry of
the same request can still get a different outcome.
"""

import asyncio
import hashlib
import json
import random
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import litellm
from litellm import exceptions as llm_errors
from litellm.llms.custom_llm import CustomLLM
from litellm.types.utils import ModelResponse

from app.core.config import Settings
from app.core.datafiles import load_yaml
from app.core.registry import Registry
from app.modules.gateway.schemas import MockAnswerKey, MockModelsConfig, MockModelSpec, MockScript, MockScriptFile

PROVIDER = "mock"
CHARS_PER_TOKEN = 4
MOCK_REQUEST = httpx.Request("POST", "http://mock.invalid/v1/chat/completions")


class MockRequest:
    def __init__(
        self, model: str, messages: list[dict[str, Any]], spec: MockModelSpec, rng: random.Random, occurrence: int
    ) -> None:
        self.model = model
        self.messages = messages
        self.spec = spec
        self.rng = rng
        self.occurrence = occurrence

    @property
    def last_user(self) -> str:
        return next((str(m["content"]) for m in reversed(self.messages) if m["role"] == "user"), "")

    @property
    def prompt_text(self) -> str:
        return "\n".join(str(m["content"]) for m in self.messages)


Behavior = Callable[["MockLLM", MockRequest], str]
BEHAVIORS: Registry[Behavior] = Registry("mock behavior")


@BEHAVIORS.register("echo")
def echo(_: "MockLLM", request: MockRequest) -> str:
    return request.last_user


@BEHAVIORS.register("scripted")
def scripted(llm: "MockLLM", request: MockRequest) -> str:
    for script in llm.scripts():
        if re.search(script.match, request.prompt_text, re.DOTALL):
            return script.response
    raise llm_errors.BadRequestError(
        message=f"mock/scripted has no fixture matching this prompt: {request.last_user[:120]!r}",
        model=request.model,
        llm_provider=PROVIDER,
    )


@BEHAVIORS.register("answer_key")
def answer_key(llm: "MockLLM", request: MockRequest) -> str:
    answers = llm.answers()
    key = request.last_user.strip()
    if key not in answers:
        raise llm_errors.BadRequestError(
            message=f"mock/{request.model} has no answer-key entry for: {key[:120]!r}",
            model=request.model,
            llm_provider=PROVIDER,
        )
    correct = answers[key]
    if request.rng.random() < (request.spec.accuracy or 0.0):
        return correct
    wrong = sorted({answer for answer in answers.values() if answer != correct}) or [f"not {correct}"]
    return request.rng.choice(wrong)


def _rate_limit(request: MockRequest) -> str:
    headers = {"retry-after": str(request.spec.retry_after_s)}
    raise llm_errors.RateLimitError(
        message="mock rate limit",
        llm_provider=PROVIDER,
        model=request.model,
        response=httpx.Response(429, headers=headers, request=MOCK_REQUEST),
    )


def _server_error(request: MockRequest) -> str:
    raise llm_errors.InternalServerError(message="mock server error", llm_provider=PROVIDER, model=request.model)


def _timeout(request: MockRequest) -> str:
    raise llm_errors.Timeout(message="mock timeout", model=request.model, llm_provider=PROVIDER)


def _broken_json(request: MockRequest) -> str:
    return 'Sure! Here is the JSON you asked for: {"answer": '


def _auth_error(request: MockRequest) -> str:
    raise llm_errors.AuthenticationError(message="mock invalid api key", llm_provider=PROVIDER, model=request.model)


def _bad_request(request: MockRequest) -> str:
    raise llm_errors.BadRequestError(message="mock bad request", llm_provider=PROVIDER, model=request.model)


def _content_policy(request: MockRequest) -> str:
    raise llm_errors.ContentPolicyViolationError(
        message="mock content policy", llm_provider=PROVIDER, model=request.model
    )


FAILURES: dict[str, Callable[[MockRequest], str]] = {
    "rate_limit": _rate_limit,
    "server_error": _server_error,
    "timeout": _timeout,
    "broken_json": _broken_json,
    "auth_error": _auth_error,
    "bad_request": _bad_request,
    "content_policy": _content_policy,
}


@BEHAVIORS.register("flaky")
def flaky(llm: "MockLLM", request: MockRequest) -> str:
    if request.occurrence <= len(request.spec.fail_first):
        return FAILURES[request.spec.fail_first[request.occurrence - 1]](request)
    if request.rng.random() < request.spec.failure_rate:
        kinds = sorted(request.spec.failure_mix)
        kind = request.rng.choices(kinds, weights=[request.spec.failure_mix[k] for k in kinds])[0]
        return FAILURES[kind](request)
    return BEHAVIORS[request.spec.inner or "echo"](llm, request)


class MockLLM(CustomLLM):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self._config = load_yaml(settings.mock_models_path, MockModelsConfig)
        self._scripted_dir = settings.mock_scripted_dir
        self._answer_key_path = settings.mock_answer_key_path
        self._seen: Counter[str] = Counter()

    def scripts(self) -> list[MockScript]:
        files = sorted(Path(self._scripted_dir).glob("*.yaml"))
        return [script for path in files for script in load_yaml(path, MockScriptFile).responses]

    def answers(self) -> dict[str, str]:
        return load_yaml(self._answer_key_path, MockAnswerKey).answers

    def _occurrence(self, model: str, messages: list[dict[str, Any]]) -> tuple[str, int]:
        digest = hashlib.sha256(json.dumps([model, messages], sort_keys=True).encode()).hexdigest()
        self._seen[digest] += 1
        return digest, self._seen[digest]

    async def acompletion(self, model: str, messages: list[dict[str, Any]], *args: Any, **kwargs: Any) -> ModelResponse:
        spec = self._config.models.get(model)
        if spec is None:
            raise llm_errors.NotFoundError(
                message=f"mock model '{model}' is not defined", model=model, llm_provider=PROVIDER
            )
        digest, occurrence = self._occurrence(model, messages)
        rng = random.Random(f"{self._config.seed}:{digest}:{occurrence}")
        request = MockRequest(model, messages, spec, rng, occurrence)
        if spec.latency_ms:
            await asyncio.sleep(spec.latency_ms / 1000)
        text = BEHAVIORS[spec.behavior](self, request)
        prompt_tokens = len(request.prompt_text) // CHARS_PER_TOKEN + 1
        completion_tokens = len(text) // CHARS_PER_TOKEN + 1
        reported = spec.response_models[(occurrence - 1) % len(spec.response_models)] if spec.response_models else model
        response = ModelResponse(
            model=f"{PROVIDER}/{reported}",
            choices=[{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        )
        response._hidden_params["additional_headers"] = dict(spec.response_headers)
        return response


def install_mock_provider(settings: Settings) -> None:
    others = [entry for entry in litellm.custom_provider_map if entry.get("provider") != PROVIDER]
    litellm.custom_provider_map = [*others, {"provider": PROVIDER, "custom_handler": MockLLM(settings)}]

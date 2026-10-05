"""
The sampling settings of one model in an experiment (DEVELOPMENT.md H2 step 1): what the
API accepts, how equal settings are written the same way, and the seed of each repeated run.

Unknown names, booleans or strings posing as numbers, NaN and bad stop sequences are refused
when the experiment is created, not silently dropped later. Whether a model supports a
setting, and its range, is checked against the model's profile in the service.
"""

from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field

MAX_RUNS = 5
# Run k uses seed + k - 1, and some providers take a 32-bit seed.
MAX_SEED = 2**31 - 1 - (MAX_RUNS - 1)
MAX_STOP_SEQUENCES = 4
MAX_STOP_CHARS = 100
NOT_A_NUMBER = "must be a number"


def _number(value: Any) -> Any:
    if isinstance(value, bool | str):
        raise ValueError(NOT_A_NUMBER)
    return value


def _stop(sequences: list[str]) -> list[str]:
    """Empty entries removed and repeats dropped; sorted, so the same set is the same setting."""
    unique = sorted({sequence for sequence in sequences if sequence})
    if len(unique) > MAX_STOP_SEQUENCES:
        raise ValueError(f"at most {MAX_STOP_SEQUENCES} stop sequences")
    if any(len(sequence) > MAX_STOP_CHARS for sequence in unique):
        raise ValueError(f"each stop sequence is at most {MAX_STOP_CHARS} characters")
    return unique


Real = Annotated[float, BeforeValidator(_number), Field(allow_inf_nan=False)]
Whole = Annotated[int, BeforeValidator(_number)]


class SamplingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    temperature: Annotated[Real, Field(ge=0, le=2)] | None = None
    top_p: Annotated[Real, Field(ge=0, le=1)] | None = None
    top_k: Annotated[Whole, Field(ge=1)] | None = None
    max_tokens: Annotated[Whole, Field(ge=1)] | None = None
    seed: Annotated[Whole, Field(ge=0, le=MAX_SEED)] | None = None
    presence_penalty: Annotated[Real, Field(ge=-2, le=2)] | None = None
    frequency_penalty: Annotated[Real, Field(ge=-2, le=2)] | None = None
    stop: Annotated[list[str], AfterValidator(_stop)] | None = None

    def normalized(self) -> dict[str, Any]:
        """Only the settings that were given; an empty stop list means none."""
        values = self.model_dump(exclude_none=True)
        if not values.get("stop"):
            values.pop("stop", None)
        return values


def normalize_params(params: dict[str, Any]) -> dict[str, Any]:
    return SamplingParams.model_validate(params).normalized()


def run_params(params: dict[str, Any], run_number: int) -> dict[str, Any]:
    """The settings of one repeated run: the seed moves up by one per run, so the runs differ
    from each other but running the same configuration again reproduces each of them."""
    if params.get("seed") is None:
        return params
    return {**params, "seed": params["seed"] + run_number - 1}

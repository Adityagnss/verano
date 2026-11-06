"""
The tools `verano mcp` offers an AI agent, each with a complete input and output schema.

A tool is a name, a description, two pydantic models (their JSON schemas are what the agent sees, and
what the server checks arguments and results against) and a handler that calls Verano's public API
through `ApiClient`. Tools are listed in one registry; adding one never touches the protocol code.
A tool marked `writes` creates, spends or moves something. It refuses, naming `--allow-write`, unless
the person who started the server allowed it. Reading results is always allowed.
"""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from verano.client import ApiClient
from verano.errors import CliError
from verano.runner import link, with_defaults

WRITE_FLAG = "--allow-write"
SMALL_SET = 30
WORST_ANSWERS_MAX = 20
REFUSAL = (
    "Refused: {tool} changes things in Verano, and this server is read-only. "
    "Ask the person who started it to restart `verano mcp` with {flag} if they want you to do this. "
    "Reading projects, prompts, labels and results is always allowed."
)


class Refused(Exception):
    """A write was asked for while the server is read-only."""


@dataclass(frozen=True)
class Context:
    api: ApiClient
    base_url: str
    allow_write: bool = False
    max_cost: Decimal | None = None


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[Context, Any], BaseModel]
    writes: bool = False

    def run(self, context: Context, arguments: BaseModel) -> BaseModel:
        if self.writes and not context.allow_write:
            raise Refused(REFUSAL.format(tool=self.name, flag=WRITE_FLAG))
        return self.handler(context, arguments)


# -- shapes ----------------------------------------------------------------------------------------


class NoArguments(Strict):
    pass


class ProjectRef(Strict):
    project_id: str = Field(description="The project's id, from list_projects.")


class ProjectItem(BaseModel):
    id: str
    name: str
    description: str | None = None


class ProjectList(BaseModel):
    projects: list[ProjectItem]


class CreateProjectIn(Strict):
    name: str = Field(min_length=1, max_length=200, description="What to call the project.")
    description: str | None = Field(default=None, max_length=2000)


class PromptItem(BaseModel):
    id: str
    name: str
    latest_version: int
    latest_version_id: str


class PromptList(BaseModel):
    prompts: list[PromptItem]


class PromptRef(ProjectRef):
    prompt_id: str = Field(description="The prompt's id, from list_prompts.")


class LabelItem(BaseModel):
    name: str
    version: int
    version_id: str


class LabelList(BaseModel):
    labels: list[LabelItem]
    accept_moves_label: str | None = Field(description="The label that accepting an improvement moves; null if none.")


class MoveLabelIn(PromptRef):
    label: str = Field(min_length=1, max_length=48, description="Such as production or staging.")
    version_id: str = Field(description="The saved version the label should point at.")


class RunEvaluationIn(ProjectRef):
    prompt_id: str | None = Field(default=None, description="The prompt to test; left out, the project's newest.")
    max_cost: float | None = Field(
        default=None,
        gt=0,
        description="Dollars. Nothing starts if the estimate is higher. Needed unless the person "
        "set a limit when starting the server.",
    )


class RunStarted(BaseModel):
    experiment_id: str
    calls: int
    estimated_cost: str | None = Field(description="Dollars, or null when a model's price is unknown.")
    link: str


class ResultRef(ProjectRef):
    experiment_id: str
    worst_answers: int = Field(
        default=5, ge=0, le=WORST_ANSWERS_MAX, description="How many weakest answers to include."
    )


class ModelResult(BaseModel):
    model: str
    cases: int
    judged_cases: int
    quality: float | None
    pass_rate: float | None
    latency_ms: float | None
    cost_per_call: str | None
    failed_calls: int
    versus_best: str | None


class Evidence(BaseModel):
    model: str
    case_number: int
    passed: bool | None
    quality: float | None
    failed_checks: list[str]
    input: str
    expected: str | None
    answer: str | None
    error: str | None


class ResultOut(BaseModel):
    experiment_id: str
    status: str
    scored: bool
    models: list[ModelResult]
    evidence: list[Evidence]
    limits: list[str] = Field(description="What the numbers can and cannot tell you. Repeat these when you report.")
    link: str


class ExperimentRef(ProjectRef):
    experiment_id: str = Field(description="The finished, scored run to improve on.")


class ImprovementStarted(BaseModel):
    session_id: str
    status: str
    stage: str
    link: str


class SessionRef(ProjectRef):
    session_id: str


class CandidateItem(BaseModel):
    id: str
    strategy: str
    outcome: str


class ImprovementState(BaseModel):
    session_id: str
    status: str
    stage: str
    message: str | None
    candidates: list[CandidateItem]


class AcceptIn(SessionRef):
    candidate_id: str


class Accepted(BaseModel):
    session_id: str
    moved_label: str | None


# -- pure helpers ------------------------------------------------------------------------------------


def limits_of(status: str, scored: bool, models: list[dict[str, Any]]) -> list[str]:
    """What the numbers can and cannot say, in plain words."""
    limits = []
    if status not in {"completed", "cancelled", "failed"}:
        limits.append("The run has not finished, so these numbers will change.")
    elif status != "completed":
        limits.append(f"The run ended early ({status}), so some test cases were never answered.")
    if not scored:
        limits.append("The answers have not been scored yet, so there is no quality number.")
    for m in models:
        if m["unscored_cases"]:
            limits.append(f"{m['model']}: {m['unscored_cases']} answers could not be judged and are left out.")
        if m["failed_calls"]:
            limits.append(f"{m['model']}: {m['failed_calls']} calls failed and have no answer.")
        if m["cases"] < SMALL_SET:
            limits.append(f"{m['model']}: only {m['cases']} test cases, so small differences may be noise.")
        if m.get("vs_best"):
            limits.append(f"{m['model']} compared with the best model: {m['vs_best']['label']}.")
    limits.append("Quality comes from a model acting as judge; check its agreement with people on the judge screen.")
    return list(dict.fromkeys(limits))


def _text(value: Any) -> str | None:
    return None if value is None else str(value)


# -- handlers ----------------------------------------------------------------------------------------


def list_projects(ctx: Context, _: NoArguments) -> ProjectList:
    return ProjectList(
        projects=[
            ProjectItem(id=str(p["id"]), name=p["name"], description=p.get("description"))
            for p in ctx.api.pages("/projects")
        ]
    )


def create_project(ctx: Context, args: CreateProjectIn) -> ProjectItem:
    created = ctx.api.post("/projects", {"name": args.name, "description": args.description})
    return ProjectItem(id=str(created["id"]), name=created["name"], description=created.get("description"))


def list_prompts(ctx: Context, args: ProjectRef) -> PromptList:
    return PromptList(
        prompts=[
            PromptItem(
                id=str(p["id"]),
                name=p["name"],
                latest_version=p["latest_version"]["version"],
                latest_version_id=str(p["latest_version"]["id"]),
            )
            for p in ctx.api.pages(f"/projects/{args.project_id}/prompts")
        ]
    )


def list_labels(ctx: Context, args: PromptRef) -> LabelList:
    found = ctx.api.get(f"/projects/{args.project_id}/prompts/{args.prompt_id}/labels")
    return LabelList(
        labels=[
            LabelItem(name=x["name"], version=x["version"], version_id=str(x["version_id"])) for x in found["labels"]
        ],
        accept_moves_label=found["accept_moves_label"],
    )


def move_label(ctx: Context, args: MoveLabelIn) -> LabelList:
    ctx.api.put(
        f"/projects/{args.project_id}/prompts/{args.prompt_id}/labels/{args.label}", {"version_id": args.version_id}
    )
    return list_labels(ctx, PromptRef(project_id=args.project_id, prompt_id=args.prompt_id))


def run_evaluation(ctx: Context, args: RunEvaluationIn) -> RunStarted:
    limit = Decimal(str(args.max_cost)) if args.max_cost is not None else ctx.max_cost
    if limit is None:
        raise CliError("Give max_cost, the most the run may cost in dollars, so nothing starts without a limit.")
    pid = args.project_id
    version = ctx.api.get(f"/projects/{pid}/dataset-versions/current")
    if version["status"] != "approved":
        raise CliError("The test cases are not approved yet.", "Approve them in the web app first.")
    profiles = [p for p in ctx.api.pages(f"/projects/{pid}/models") if p["is_selected"]]
    if not profiles:
        raise CliError("No models are selected in this project.", "Select the models to test in the web app first.")
    body: dict[str, Any] = {
        "dataset_version_id": version["id"],
        "split_scope": "all",
        "models": [{"model_profile_id": p["id"], "runs": 1, "params": with_defaults({}, p)} for p in profiles],
        "budget_cap": str(limit),
    }
    if args.prompt_id:
        body["prompt_id"] = args.prompt_id
    estimate = ctx.api.post(f"/projects/{pid}/experiments/estimate", body)
    cost = estimate["total_cost"]
    if cost is None:
        raise CliError("The price of some selected models is unknown, so the limit can't be checked. Nothing started.")
    if Decimal(str(cost)) > limit:
        raise CliError(f"The estimate ${cost} is over the limit ${limit}. Nothing was started.")
    experiment = ctx.api.post(f"/projects/{pid}/experiments", body)
    return RunStarted(
        experiment_id=str(experiment["id"]),
        calls=estimate["calls"],
        estimated_cost=_text(cost),
        link=link(ctx.base_url, pid, str(experiment["id"])),
    )


def get_result(ctx: Context, args: ResultRef) -> ResultOut:
    pid, eid = args.project_id, args.experiment_id
    experiment = ctx.api.get(f"/projects/{pid}/experiments/{eid}")
    results = ctx.api.get(f"/projects/{pid}/experiments/{eid}/results")
    scored = results["evaluation_run"] is not None
    evidence: list[Evidence] = []
    if scored and args.worst_answers:
        rows = ctx.api.get(
            f"/projects/{pid}/logbook/answers",
            experiment_ids=[eid],
            sort="quality",
            order="asc",
            limit=args.worst_answers,
        )["items"]
        evidence = [
            Evidence(
                model=r["model"],
                case_number=r["case_number"],
                passed=r["passed"],
                quality=r["quality"],
                failed_checks=r["failed_checks"],
                input=r["input_preview"],
                expected=r["golden_answer"],
                answer=r["output_preview"],
                error=r["error"],
            )
            for r in rows
        ]
    models = [
        ModelResult(
            model=m["model"],
            cases=m["cases"],
            judged_cases=m["judged_cases"],
            quality=m["quality"],
            pass_rate=m["pass_rate"],
            latency_ms=m["latency_ms"],
            cost_per_call=_text(m["cost_per_call"]),
            failed_calls=m["failed_calls"],
            versus_best=m["vs_best"]["label"] if m.get("vs_best") else None,
        )
        for m in results["models"]
    ]
    return ResultOut(
        experiment_id=eid,
        status=experiment["status"],
        scored=scored,
        models=models,
        evidence=evidence,
        limits=limits_of(experiment["status"], scored, results["models"]),
        link=link(ctx.base_url, pid, eid),
    )


def propose_improvement(ctx: Context, args: ExperimentRef) -> ImprovementStarted:
    started = ctx.api.post(f"/projects/{args.project_id}/improvements", {"experiment_id": args.experiment_id})
    return ImprovementStarted(
        session_id=str(started["id"]),
        status=started["status"],
        stage=started["stage"],
        link=link(ctx.base_url, args.project_id, args.experiment_id),
    )


def get_improvement(ctx: Context, args: SessionRef) -> ImprovementState:
    found = ctx.api.get(f"/projects/{args.project_id}/improvements/{args.session_id}")
    return ImprovementState(
        session_id=str(found["id"]),
        status=found["status"],
        stage=found["stage"],
        message=found["message"],
        candidates=[
            CandidateItem(id=str(c["id"]), strategy=c["strategy"], outcome=c["outcome"]) for c in found["candidates"]
        ],
    )


def accept_improvement(ctx: Context, args: AcceptIn) -> Accepted:
    done = ctx.api.post(
        f"/projects/{args.project_id}/improvements/{args.session_id}/candidates/{args.candidate_id}/accept"
    )
    return Accepted(session_id=str(done["id"]), moved_label=done.get("moved_label"))


def registry() -> list[Tool]:
    return [
        Tool("list_projects", "List projects", "The projects you can see.", NoArguments, ProjectList, list_projects),
        Tool(
            "create_project",
            "Create a project",
            "Make an empty project.",
            CreateProjectIn,
            ProjectItem,
            create_project,
            writes=True,
        ),
        Tool(
            "list_prompts",
            "List prompts",
            "A project's prompts and their latest versions.",
            ProjectRef,
            PromptList,
            list_prompts,
        ),
        Tool(
            "list_labels",
            "List prompt labels",
            "Which version each label (production, staging) points at.",
            PromptRef,
            LabelList,
            list_labels,
        ),
        Tool(
            "run_evaluation",
            "Run an evaluation",
            "Test a prompt on the project's approved test cases with its selected models. Costs money, "
            "so a cost limit is required. Returns at once; read the outcome with get_result.",
            RunEvaluationIn,
            RunStarted,
            run_evaluation,
            writes=True,
        ),
        Tool(
            "get_result",
            "Read a result",
            "The scores of a run with the weakest answers as evidence and the limits of the numbers.",
            ResultRef,
            ResultOut,
            get_result,
        ),
        Tool(
            "propose_improvement",
            "Propose an improvement",
            "Start an Improve round on a finished run: Verano writes and tests better versions of the prompt. "
            "It never accepts one.",
            ExperimentRef,
            ImprovementStarted,
            propose_improvement,
            writes=True,
        ),
        Tool(
            "get_improvement",
            "Read an improvement",
            "How an Improve round is going and which candidates beat the prompt.",
            SessionRef,
            ImprovementState,
            get_improvement,
        ),
        Tool(
            "accept_improvement",
            "Accept an improvement",
            "Save a proven candidate as the prompt's new version (and move the label if the prompt is set to).",
            AcceptIn,
            Accepted,
            accept_improvement,
            writes=True,
        ),
        Tool(
            "move_label",
            "Move a label",
            "Point a label such as production at a saved version, which changes what apps receive.",
            MoveLabelIn,
            LabelList,
            move_label,
            writes=True,
        ),
    ]

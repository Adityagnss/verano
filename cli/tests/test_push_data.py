"""`verano push`, test cases: upload, pair, approve, and leave things alone when nothing changed."""

from pathlib import Path

import pytest

from tests.conftest import Run
from tests.platform import FakePlatform
from verano import data

SECRET = "sk-test-SECRET-9876"
TICKETS = (
    "ticket,expected\nCard charged twice,billing\nWhere is my parcel,shipping\nApp crashes,technical\n,missing input\n"
)

HEADER = """\
version: 1
project: shop
keys:
  openai: env:OPENAI_API_KEY
prompts:
  - name: tag
    system: Tag the ticket.
    task: {type: classification, goal: Tag tickets by team, allowed_outputs: [billing, shipping, technical]}
    models: [gpt-4o-mini]
"""
CASES = "    data:\n      cases: {file: tickets.csv, input: ticket, expected: expected}\n"


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(data, "POLL_S", 0)
    monkeypatch.setattr(data, "WAIT_S", 0.05)
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)


def setup(tmp_path: Path, extra: str = CASES, tickets: str = TICKETS, header: str = HEADER) -> Path:
    (tmp_path / "tickets.csv").write_text(tickets)
    path = tmp_path / "verano.yaml"
    path.write_text(header + extra)
    return path


def uploads(platform: FakePlatform) -> int:
    return sum(1 for call in platform.calls if call == ("POST", f"/projects/{platform.projects[0]['id']}/input-files"))


def test_the_first_push_uploads_the_cases_pairs_the_answers_and_approves_them(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    setup(tmp_path)
    result = run("push")
    assert result.code == 0, result.err
    assert "1 rows skipped (row 4: the input is empty)" not in result.err  # that is for validate, not push
    assert "3 test cases uploaded, 3 paired with an answer" in result.err
    assert "test cases approved: 3 cases (0 held back to check improvements)" in result.err
    pid = platform.projects[0]["id"]
    names = sorted(f["filename"] for f in platform.files[pid])
    assert names == ["case-0001.txt", "case-0002.txt", "case-0003.txt", "golden.csv"]
    texts = {f["filename"]: platform.contents[f["id"]].decode() for f in platform.files[pid]}
    assert texts["case-0002.txt"] == "Where is my parcel"
    assert "case-0003.txt,technical" in texts["golden.csv"]
    (version,) = platform.versions[pid]
    assert version["status"] == "approved"
    (spec,) = platform.specs.values()
    assert spec["spec"] == {
        "task_type": "classification",
        "goal": "Tag tickets by team",
        "output_format": "single_label",
        "allowed_outputs": ["billing", "shipping", "technical"],
        "output_schema": None,
        "constraints": [],
        "risk_areas": [],
    }
    assert version["task_spec_id"] == spec["id"]
    golden = next(f for f in platform.files[pid] if f["kind"] == "golden_set")
    assert golden["column_mapping"]["input_file"] == "input_file"


def test_pushing_again_uploads_nothing_and_a_prompt_wording_change_does_not_rebuild_the_cases(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = setup(tmp_path)
    run("push")
    platform.calls.clear()
    again = run("push")
    assert "test cases unchanged (3 cases, approved)" in again.err
    assert uploads(platform) == 0
    path.write_text(path.read_text().replace("Tag the ticket.", "Tag the ticket with a team name."))
    platform.calls.clear()
    reworded = run("push")
    assert "saved version 2" in reworded.err
    assert "test cases unchanged" in reworded.err
    assert uploads(platform) == 0
    assert len(platform.versions[platform.projects[0]["id"]]) == 1


def test_changing_a_row_or_the_task_makes_a_new_dataset_version_and_keeps_the_old_one(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    path = setup(tmp_path)
    run("push")
    (tmp_path / "tickets.csv").write_text(TICKETS.replace("App crashes", "App crashes at start"))
    changed = run("push")
    assert "test cases approved: 3 cases" in changed.err
    pid = platform.projects[0]["id"]
    assert [v["status"] for v in platform.versions[pid]] == ["approved", "approved"]
    assert uploads(platform) == 8
    path.write_text(path.read_text().replace("Tag tickets by team", "Tag tickets by owning team"))
    platform.calls.clear()
    assert "test cases approved" in run("push").err
    assert len(platform.versions[pid]) == 3


def test_a_dry_run_says_what_would_be_uploaded_and_changes_nothing(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    setup(tmp_path)
    fresh = run("push", "--dry-run")
    assert fresh.code == 0
    assert "would: save the Task Spec and upload 3 test cases" in fresh.err
    run("push")
    platform.calls.clear()
    kept = run("push", "--dry-run")
    assert "would: keep the approved test cases (the files are unchanged)" in kept.err
    (tmp_path / "tickets.csv").write_text(TICKETS + "New one,other\n")
    changed = run("push", "--dry-run")
    assert "would: upload 4 test cases and approve them as a new dataset version" in changed.err
    assert platform.writes == []


def test_no_data_leaves_the_test_cases_alone(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    setup(tmp_path)
    result = run("push", "--no-data")
    assert result.code == 0
    assert platform.files == {}
    assert platform.specs == {}


def test_a_prompt_that_wants_other_inputs_than_a_file_can_provide_is_refused_with_the_fix(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    header = HEADER.replace("    system: Tag the ticket.\n", "    user: 'Ticket: {{ ticket }}'\n")
    setup(tmp_path, header=header)
    result = run("push")
    assert result.code == 1
    assert "The prompt needs {{ ticket }}" in result.err
    assert "Write {{ attachment }}" in result.err
    assert platform.files == {}


def test_a_judge_is_passed_with_the_task_and_missing_one_is_flagged_when_scoring_needs_it(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    platform.evaluator_kinds = ["exact_match", "deepeval"]
    path = setup(tmp_path)
    assert "scored partly by a judge model" in run("push").err
    (tmp_path / "tickets.csv").write_text(TICKETS + "Another,other\n")
    path.write_text(
        path.read_text().replace(
            "    models: [gpt-4o-mini]\n", "    models: [gpt-4o-mini, gpt-4o]\n    judge: gpt-4o\n"
        )
    )
    judged = run("push")
    assert "scored partly by a judge model" not in judged.err
    last = list(platform.specs.values())[-1]
    assert last["generator_model"] == "gpt-4o"
    assert last["generator_credential_id"] == platform.credentials[platform.projects[0]["id"]][0]["id"]


def test_files_and_a_golden_table_can_be_given_as_they_are(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    for number in (1, 2):
        (tmp_path / "docs" / f"t{number}.txt").write_text(f"ticket {number}")
    (tmp_path / "answers.csv").write_text("file,answer\nt1.txt,billing\nt2.txt,shipping\nt3.txt,other\n")
    extra = (
        "    data:\n      inputs: [docs/*.txt]\n      golden: answers.csv\n"
        "      columns: {input_file: file, expected_output: answer}\n"
    )
    path = setup(tmp_path, extra)
    result = run("push")
    assert result.code == 0, result.err
    assert "golden file: Some rows match no input file. (1 rows)" in result.err
    assert "2 test cases uploaded, 3 paired with an answer" in result.err
    golden = next(f for f in platform.files[platform.projects[0]["id"]] if f["kind"] == "golden_set")
    assert golden["column_mapping"] == {"input_file": "file", "expected_output": "answer"}
    path.write_text(path.read_text().replace("      columns: {input_file: file, expected_output: answer}\n", ""))
    (tmp_path / "answers.csv").write_text("file,answer\nt1.txt,billing\n")
    assert run("push").code == 0
    suggested = [f for f in platform.files[platform.projects[0]["id"]] if f["kind"] == "golden_set"][-1]
    assert suggested["column_mapping"] == {"expected_output": "expected"}


def test_two_input_files_with_one_name_are_refused(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        (tmp_path / folder / "same.txt").write_text(folder)
    setup(tmp_path, "    data:\n      inputs: ['*/same.txt']\n")
    result = run("push")
    assert result.code == 1
    assert "Two input files are both called same.txt" in result.err


def test_unapproved_cases_from_elsewhere_are_not_touched_unless_asked(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    setup(tmp_path)
    run("push", "--no-data")
    pid = platform.projects[0]["id"]
    draft = platform.draft(pid)
    foreign = {
        "id": "f-ui", "kind": "raw_inputs", "status": "imported", "filename": "from-the-web-app.txt",
        "size_bytes": 3, "sha256": "ab" * 32, "dataset_version_id": draft["id"], "validation_report": None,
    }  # fmt: skip
    platform.files.setdefault(pid, []).append(foreign)
    draft["item_count"] += 1
    refused = run("push")
    assert refused.code == 1
    assert "unapproved test cases that are not in verano.yaml (from-the-web-app.txt)" in refused.err
    assert "--replace-draft" in refused.err
    assert all(f["filename"] != "case-0001.txt" for f in platform.files[pid])
    replaced = run("push", "--replace-draft")
    assert replaced.code == 0, replaced.err
    assert "from-the-web-app.txt" not in {f["filename"] for f in platform.files[pid]}
    assert "test cases approved: 3 cases" in replaced.err


def test_an_unfinished_earlier_push_is_cleaned_up_and_redone(platform: FakePlatform, run: Run, tmp_path: Path) -> None:
    setup(tmp_path)
    run("push", "--no-data")
    pid = platform.projects[0]["id"]
    platform.draft(pid)["item_count"] = 0
    platform.files[pid] = []
    platform.stuck = True
    stuck = run("push")
    assert stuck.code == 1
    platform.stuck = False
    again = run("push")
    assert again.code == 0, again.err
    assert sorted(f["filename"] for f in platform.files[pid]).count("golden.csv") == 1
    assert platform.versions[pid][-1]["status"] == "approved"


def test_a_worker_that_never_finishes_is_named_after_the_wait(
    platform: FakePlatform, run: Run, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup(tmp_path)
    platform.stuck = True
    result = run("push")
    assert result.code == 1
    assert "didn't finish processing test cases within 0 seconds" in result.err
    assert "docker compose logs worker" in result.err


@pytest.mark.parametrize(
    ("extra", "tickets", "needle"),
    [
        (
            "    data:\n      cases: {file: tickets.csv, input: text, expected: expected}\n",
            TICKETS,
            "the column 'text' (for input) is not in the file",
        ),
        (
            "    data:\n      cases: {file: tickets.xlsx, input: ticket, expected: expected}\n",
            TICKETS,
            "Save it as CSV first",
        ),
        (
            "    data:\n      cases: {file: tickets.csv, input: ticket}\n",
            TICKETS,
            "name the column with the correct answer",
        ),
        (
            "    data:\n      cases: {file: tickets.csv, input: ticket, expected: expected}\n"
            "      golden: tickets.csv\n",
            TICKETS,
            "not both",
        ),
        (CASES, "ticket,expected\n,\n", "no row has both an input and a correct answer"),
    ],
)
def test_mistakes_in_the_cases_are_caught_before_anything_is_sent(
    platform: FakePlatform, run: Run, tmp_path: Path, extra: str, tickets: str, needle: str
) -> None:
    setup(tmp_path, extra, tickets)
    (tmp_path / "tickets.xlsx").write_bytes(b"PK")
    result = run("push")
    assert result.code == 1
    assert needle in result.err
    assert platform.calls == []


def test_validate_previews_the_cases_and_the_rows_it_would_skip(
    platform: FakePlatform, run: Run, tmp_path: Path
) -> None:
    setup(tmp_path)
    result = run("validate")
    assert result.code == 0
    assert "data:    3 test cases from tickets.csv (1 rows skipped)" in result.out
    assert "1 rows skipped (row 4: the input is empty)" in result.err
    assert platform.calls == []

"""
The whole-loop driver `scripts/flow_check.py` runs end to end against the mock provider: sign up, add a key, write and
approve test cases, run, Improve, save the best candidate and run it again. The mock models do not get better with
a better prompt, so this proves the plumbing and the printed scores, not the lift; the real lift is measured with
a real key (see the script).
"""

import importlib.util
from pathlib import Path

import httpx
import pytest

pytestmark = [pytest.mark.integration]

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "flow_check.py"


async def test_the_flow_driver_runs_the_whole_loop_on_the_mock_provider(client: httpx.AsyncClient) -> None:
    spec = importlib.util.spec_from_file_location("flow_check", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    flow_check = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(flow_check)
    lines: list[str] = []
    flow = await flow_check.run_flow(
        client,
        provider="mock",
        api_key=None,
        model="bad",
        writer_model="scripted",
        cases=12,
        rounds=1,
        force_save=True,
        say=lines.append,
        wait=60,
        every=0.05,
    )
    assert [r.label.split(" (")[0] for r in flow.rounds] == ["Round 0", "Round 1"]
    assert all(r.pass_rate is not None for r in flow.rounds)
    assert any(line.startswith("Improve wrote 3 candidates") for line in lines)

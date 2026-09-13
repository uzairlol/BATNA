"""Unit tests for the Phase 6 full-loop DoD evaluator (hermetic, CI-gating)."""

from __future__ import annotations

from batna.agents.eval import run_full_loop_dod_eval


async def test_full_loop_dod_passes_with_zero_crashes() -> None:
    result = await run_full_loop_dod_eval(runs_per_config=6, max_rounds=6)

    assert result.total_runs == 24  # 4 configs x 6 runs
    assert result.crashes == 0
    assert result.passes() is True  # >= 20 runs and zero crashes

    # Every no-ZOPA run must be detected as no_zopa (correct deadlock detection).
    assert result.per_config["no_zopa"]["no_zopa"] == 6
    assert result.per_config["no_zopa"]["crashes"] == 0
    assert result.per_config["no_zopa"]["agreements"] == 0

    # With a 6-round budget, the wide and asymmetric ZOPAs agree; no-ZOPA never does.
    assert result.per_config["wide"]["agreements"] >= 1
    assert result.per_config["asymmetric"]["agreements"] >= 1
    assert result.per_config["wide"]["round_exhaustions"] == 0


async def test_full_loop_dod_reports_tool_usage() -> None:
    result = await run_full_loop_dod_eval(runs_per_config=2, max_rounds=6)

    # Both sides used at least one tool in at least the wide/asymmetric runs.
    assert result.tool_using_buyer_runs >= 1
    assert result.tool_using_seller_runs >= 1


async def test_full_loop_dod_requires_20_runs() -> None:
    result = await run_full_loop_dod_eval(runs_per_config=1, max_rounds=6)
    # 4 runs total < 20 -> DoD not met.
    assert result.passes() is False

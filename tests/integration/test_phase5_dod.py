"""Integration tests: the Phase 5 Definition of Done against the real precedent MCP server.

Phase 5 DoD: across 20+ runs the buyer agent calls at least one real MCP tool before
its opening offer in the large majority of cases, and diffing its claims against the
call log never finds a reference to a result it did not really fetch. These tests run
against the real ``precedent`` MCP server (real cached USAspending awards), so no
external network or LLM is required.
"""

from __future__ import annotations

import os
import sys

import pytest

from batna.agents.eval import default_server_env, run_dod_eval

_RUNS = int(os.environ.get("PHASE5_DOD_RUNS", "20"))


@pytest.mark.integration
async def test_phase5_dod_against_real_precedent_server() -> None:
    result = await run_dod_eval(
        runs=_RUNS,
        command=sys.executable,
        args=["-m", "batna.mcp_servers.precedent_server"],
        env=default_server_env(),
    )

    # With the deterministic scripted client every run consults the registry tool first.
    assert result.tool_before_offer_runs == result.total_runs
    # Majority of runs called a real MCP tool (search_precedent) before the opening offer.
    assert result.tool_before_offer_runs / result.total_runs >= 0.8
    # No run ever cited a value it did not actually fetch.
    assert result.ungrounded_runs == 0
    assert result.grounded_runs == result.total_runs
    assert result.passes()

"""BATNA negotiating and adversarial agents.

Phase 5 introduces the single, tool-using buyer agent that discovers MCP tools
dynamically each session, autonomously decides which to call before its opening offer,
and records every invocation so its claims can be audited against the real call log.
"""

from batna.agents.buyer_agent import BuyerAgent, NegotiationResult, OpeningOffer
from batna.agents.eval import DoDResult, run_dod_eval
from batna.agents.llm import Action, LLMClient, OllamaLLMClient, ScriptedLLMClient, ToolCall
from batna.agents.scripted_counterparty import CounterOffer, ScriptedSeller
from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.agents.tool_provider import ToolProvider
from batna.agents.verification import (
    VerificationOptions,
    VerificationReport,
    verify_claims_grounded,
)

__all__ = [
    "Action",
    "BuyerAgent",
    "CounterOffer",
    "DoDResult",
    "LLMClient",
    "NegotiationResult",
    "OllamaLLMClient",
    "OpeningOffer",
    "ScriptedLLMClient",
    "ScriptedSeller",
    "ToolCall",
    "ToolCallEntry",
    "ToolCallLog",
    "ToolProvider",
    "VerificationOptions",
    "VerificationReport",
    "run_dod_eval",
    "verify_claims_grounded",
]

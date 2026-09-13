"""BATNA negotiating and adversarial agents.

Phase 5 introduces the single, tool-using buyer agent that discovers MCP tools
dynamically each session, autonomously decides which to call before its opening offer,
and records every invocation so its claims can be audited against the real call log.

Phase 6 turns this into a full two-agent loop: a shared ``NegotiatorAgent`` base
(Buyer and Seller), structured multi-term ``ContractTerms`` offers, a merged native +
MCP dynamic tool catalog, and a LangGraph flow. Scripted negotiator stand-ins keep CI
hermetic.
"""

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.eval import DoDResult, FullLoopResult, run_dod_eval, run_full_loop_dod_eval
from batna.agents.llm import (
    Action,
    LLMClient,
    OllamaLLMClient,
    ScriptedLLMClient,
    ScriptedNegotiatorLLM,
    ToolCall,
)
from batna.agents.native_tools import NativeTool, check_contract_risk_schema, native_tools_catalog
from batna.agents.negotiator import NegotiationError, NegotiatorAgent
from batna.agents.offers import OfferParseError, ParsedOffer, format_offer, parse_offer
from batna.agents.scripted_counterparty import CounterOffer, ScriptedSeller
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_call_log import ToolCallEntry, ToolCallLog
from batna.agents.tool_provider import ToolProvider
from batna.agents.verification import (
    VerificationOptions,
    VerificationReport,
    verify_claims_grounded,
    verify_offer_grounded,
)

__all__ = [
    "Action",
    "BuyerAgent",
    "CounterOffer",
    "DoDResult",
    "FullLoopResult",
    "LLMClient",
    "NativeTool",
    "NegotiationError",
    "NegotiatorAgent",
    "OfferParseError",
    "OllamaLLMClient",
    "ParsedOffer",
    "ScriptedLLMClient",
    "ScriptedNegotiatorLLM",
    "ScriptedSeller",
    "SellerAgent",
    "ToolCall",
    "ToolCallEntry",
    "ToolCallLog",
    "ToolProvider",
    "VerificationOptions",
    "VerificationReport",
    "check_contract_risk_schema",
    "format_offer",
    "native_tools_catalog",
    "parse_offer",
    "run_dod_eval",
    "run_full_loop_dod_eval",
    "verify_claims_grounded",
    "verify_offer_grounded",
]

"""Smoke: prove a REAL Ollama model negotiates through the agent loop (live mode)."""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from batna.agents.buyer_agent import BuyerAgent
from batna.agents.eval import _DEFAULT_SCENARIO, _HermeticRegistry, _scenario_principals
from batna.agents.graph import run_negotiation
from batna.agents.llm import OllamaLLMClient
from batna.agents.seller_agent import SellerAgent
from batna.agents.tool_provider import ToolProvider
from batna.stream.events import EventType
from batna.stream.sink import InMemoryStreamSink


async def main() -> None:
    model = "qwen2.5:7b"
    durable = InMemoryStreamSink(session_id="live-smoke")
    shared = _HermeticRegistry()

    llm = OllamaLLMClient(model=model)
    buyer = BuyerAgent(
        llm=llm,
        provider=ToolProvider(shared, sink=durable, role="buyer"),
        sink=durable,
        role="buyer",
    )
    seller = SellerAgent(
        llm=OllamaLLMClient(model=model),
        provider=ToolProvider(shared, sink=durable, role="seller"),
        sink=durable,
        role="seller",
    )

    buyer_p, seller_p = _scenario_principals("wide")
    result = await run_negotiation(
        buyer,
        seller,
        buyer_p,
        seller_p,
        _DEFAULT_SCENARIO,
        max_rounds=3,
        sink=durable,
        thread_id="live-smoke",
        run_mode="live",
        run_model=model,
    )

    print(f"\nOUTCOME: {result.get('outcome')}")
    print(f"ROUNDS:  {result.get('rounds_elapsed')}")
    print(f"RUN_MODE: {result.get('run_mode')} / {result.get('run_model')}")
    print(f"ACCEPTED: {result.get('accepted_offer')}")
    print("\n---- streamed reasoning (REAL model text) ----")
    for ev in durable.emitted:
        if ev.type is EventType.REASONING:
            print(f"[{ev.side}] {ev.payload.get('text', '')[:400]}")
    print("\n---- offers ----")
    for ev in durable.emitted:
        if ev.type is EventType.OFFER:
            print(f"[{ev.side}] { {k: v for k, v in ev.payload.items() if k == 'price'} }")
    print(f"\nTOTAL EVENTS: {len(durable.emitted)}")


if __name__ == "__main__":
    asyncio.run(main())

# BATNA — Bilateral Agent Trust & Negotiation Architecture

**Status:** Pre-build / Specification (v3 — Real Agentic Architecture, No Placeholders)
**Owner:** Uzair Arif
**Type:** Production-grade agentic AI system (portfolio project, AI Engineer track)
**Prior work this extends:** ELICIT (Theory-of-Mind auditing, reputation, gossip, institutional voting), SEAM (structured memory curation, contamination/poisoning detection)

**What changed from v2, and why:** v2 still leaned on synthetic placeholder data behind the tools (a hand-written JSON file standing in for "market benchmarks") and treated tools as in-process Python functions rather than genuine externally-served capabilities. That is a real gap between "looks agentic" and "is agentic" — the mechanics were right, the substance behind them was not. v3 closes that gap on every component: tools are backed by real public data sources or a real served MCP tool, tool selection is dynamic rather than a fixed hardcoded list, and a human-approval gate exists for consequential actions, which is how real deployed agentic systems handle high-stakes autonomy today — they don't let an agent finalize a six-figure commitment with zero oversight, and neither should this system pretend to.

---

## 0. One-Line Pitch

An autonomous multi-agent contract negotiation system in which two tool-using LLM agents represent principals with genuinely conflicting interests, dynamically select and call real data-backed tools — served over MCP, grounded in real public economic and procurement data — mid-negotiation, are audited for reasoning-tool-action consistency by a Theory-of-Mind auditor, are protected from manipulation by a poisoning-aware structured memory system, escalate consequential decisions to a human approval gate, and stream the entire negotiation live to a public, one-command-deployable dashboard.

---

## 1. Why This Project Exists (Portfolio Thesis)

Unchanged in substance from v2 — keep this framing everywhere:

- **ELICIT** found a Reasoning-Action Gap: agents articulate correct strategy but act inconsistently, detectable via Theory-of-Mind auditing.
- **SEAM** found memory collapse (Echo Trap) under naive updates and contamination vulnerability under shared memory, both mitigated by structured Generate→Reflect→Curate curation.
- **BATNA** productizes both findings inside a real tool-using, real-data-grounded agentic system doing consequential autonomous work, with the same rigor about "what is actually being claimed" that you demanded of your own ELICIT/SEAM writeups: no synthetic stand-ins presented as if they were real, no capability claimed that hasn't been verified against an adversarial test.

---

## 2. What "Agentic" Means Here — And What Disqualifies a Component From Counting

State this explicitly in the README. A component only counts as "agentic" in this system if it meets all of the following. This bar exists specifically to prevent the toy-tool problem from creeping back in during implementation.

1. **The agent, not the code, decides whether and which tool to call**, based on reasoning over the current state — no fixed call sequence.
2. **The tool is backed by real, externally verifiable data or computation** — not a hand-authored JSON file dressed up as a data source. If you cannot point to where the underlying number came from outside your own repo, it does not ship.
3. **At least one tool is served as a genuine external capability** (an MCP server the agent calls over a protocol boundary), not merely an in-process Python function — this is the actual current industry pattern (Anthropic's own MCP, used the same way your own tool list uses `search_mcp_registry` / `suggest_connectors`), and it is the concrete, checkable difference between "I wrote a function and called it a tool" and "I built an agent that consumes real external tools."
4. **Consequential actions pass through an explicit approval gate**, not unconditional autonomy — this is how real agentic deployments (payments, procurement, legal commitments) are actually shipped in 2026: bounded autonomy with human-in-the-loop checkpoints above a defined stakes threshold, not full autonomy dressed up as a feature.
5. **Failure is handled, not assumed away** — every tool call has a timeout, a retry policy, and a defined agent behavior when a tool errors or returns malformed data. An agent that has never seen its own tool fail has not been tested as an agent.

Any component that fails one of these five checks gets rebuilt or cut before Phase Review — do not let a "we'll make it real later" placeholder survive into a later phase. That is exactly the failure mode you called out.

---

## 3. Domain Scope

**Domain: B2B vendor/procurement contract negotiation.** Unchanged reasoning: quantifiable terms, real commercial precedent (Ironclad, Robin AI class), and — new in v3 — genuine public data availability, which is exactly why this domain was chosen and not, say, a fictional negotiation scenario: procurement and vendor pricing data has real, freely accessible public sources (below), which is what makes "no toy data" achievable at all in the time you have.

**Out of scope for v1:** 3+ party negotiations, real-time voice, parsing real uploaded legal documents, fine-tuning, live human negotiation replacement. Log these in `FUTURE_WORK.md`, do not build them now.

---

## 4. Tech Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Consistent with your stack |
| Agent orchestration | LangGraph | Native tool-calling nodes, conditional edges driven by the agent's own tool-call decision, state persistence |
| **Tool protocol** | **MCP (Model Context Protocol)** for at least the precedent-retrieval and market-data tools, run as real local MCP servers your agents connect to over stdio/HTTP | This is the actual current standard for how production agent systems expose tools externally — not a nice-to-have, a requirement per Section 2 |
| LLM — negotiating agents (local dev) | **Qwen3:4B minimum** via Ollama with native tool calling | Independent benchmark data shows sub-4B open models fail specifically at tool-call *judgment* — resisting irrelevant triggers, recognizing when a tool is unnecessary, respecting negation — which is exactly the skill your negotiating agents need most. Do not go smaller than this for anything you'd show in a demo or count in an eval run. |
| LLM — negotiating agents (hosted/prod) | Anthropic API (Claude Sonnet) | Real cost/latency tracking, stronger multi-step tool-use reliability for the hosted demo that a hiring manager will actually click on |
| LLM — ToM auditor & judge | Anthropic API (Claude Haiku) or Qwen3:4B locally | Cheaper model, deliberately different from the negotiating agents to avoid shared blind spots |
| Structured output / tool schemas | Pydantic v2 | Every tool call, tool result, offer, and audit result validated, matching your existing no-hardcoded-constants discipline |
| Backend API | FastAPI | Session endpoints, WebSocket streaming |
| Real-time transport | WebSockets + Redis pub/sub | Every reasoning step, tool call, tool result, offer, audit result, and approval-gate event published the instant it happens |
| Persistence | PostgreSQL | Full transcripts, tool call logs (including MCP call/response pairs), contract state, audit logs, eval results, approval-gate decisions |
| Cache/pubsub | Redis | Live session state, dashboard pub/sub backbone |
| Observability | OpenTelemetry, trace store in Postgres | Per-turn and per-tool-call latency and cost, full causal chain including MCP round-trips |
| Eval harness | Custom pytest-based + LLM-as-judge for qualitative surface | Golden scenarios built from real reference data (Section 5.2), not synthetic ones |
| CI/CD | GitHub Actions | Lint (ruff strict), type-check (mypy strict), unit + integration tests, eval regression gate, MCP server health check |
| Containerization | Docker + docker-compose | One-command full stack including MCP server containers |
| Hosting | Fly.io (API, Postgres, Redis, MCP servers), Vercel (dashboard) | Zero-friction deploy from Dockerfile/Vite build, WebSockets supported natively |
| Dashboard | React + Vite, native WebSocket client | Live per-agent reasoning, tool calls with real inputs/outputs visible, offers, ToM scores, memory health, guardrail flags, approval-gate prompts |
| Testing | pytest, ruff (UP/B/ANN/RUF), mypy strict | Matches your existing bar |

---

## 5. Core Components — Deep Dive

### 5.1 Negotiation Engine (deterministic core, no LLM)
Unchanged: contract schema (`price`, `payment_terms_days`, `delivery_sla_days`, `liability_cap_pct`, `contract_duration_months`, `termination_notice_days`), principal schema (`reservation_value`, `target_value`, `authorized_mandate`, `round_budget`), ZOPA calculation, Nash Bargaining Solution reference score. Build and fully unit-test before any LLM exists.

### 5.2 Tools — Real Data, Real Serving, No Placeholders

| Tool | Real backing source | Serving | Why it's real, not toy |
|---|---|---|---|
| `get_market_benchmark(term, industry, region)` | **FRED (Federal Reserve Economic Data) API** and/or **BLS Producer Price Index (PPI) API** — both free, public, no synthetic authoring required — pulled live for relevant industry cost indices, plus historical PPI trend to justify a price range for the negotiated good/service category | MCP server (`fred-mcp` or a thin custom MCP wrapper around the FRED/BLS REST APIs) | The number the agent reasons over is a real published economic statistic at the moment it's queried, not a number you invented. This is the single highest-leverage fix from v2. |
| `check_contract_risk(proposed_terms)` | A codified rule engine built from real, citable procurement risk-assessment frameworks (e.g., published NIST/ISO supplier-risk criteria, or a public standard contract clause library such as the Uniform Commercial Code's default remedy provisions as the reference for liability-cap reasonableness) — the rules must trace to a real external standard you can cite, not an ad hoc if/else you made up for convenience | In-process (deterministic logic does not need MCP — MCP is for genuine external capability, not for dressing up local code) | The distinction that matters: it's fine for this to be local code, as long as the *rules themselves* trace to a real external standard, not an invented threshold. Cite the source in a code comment and in the README. |
| `simulate_counteroffer(current_terms, proposed_concession)` | Pure game-theoretic computation (expected surplus vs. reservation value) | In-process | This is real by construction — it's math, not a data-sourcing problem. No change needed here, this was never the toy part. |
| `retrieve_precedent(term, industry)` | **USAspending.gov API** (U.S. federal contract award data — public domain, free, no auth required, includes real award amounts, terms, and vendor/agency pairs) indexed into your existing FAISS/BM25/RRF hybrid retrieval pipeline, reused directly from the IBA RAG chatbot build | **MCP server**, run as its own container, exposing a `search_precedent` tool over a real indexed corpus of real government procurement awards | This is your strongest "not toy" artifact: real government contract data, a real hybrid retrieval pipeline you've already built once, served over the real protocol standard. This is the component to spend the most care on. |

**Dynamic tool selection, not a fixed list:** agents receive a tool *catalog* (queried from the MCP registry each session, mirroring the `search_mcp_registry` → `suggest_connectors` pattern used elsewhere in modern agent platforms) rather than a hardcoded static tool list baked into the prompt. This matters because a fixed tool list is itself a small tell of a toy build — a genuinely agentic system discovers and selects from available capabilities rather than having them enumerated once and never revisited.

### 5.3 Buyer Agent / Seller Agent
Per turn: agent receives state → queries available tools from the MCP registry → decides whether/which to call → receives real tool results → reasons over them, explicitly citing what it retrieved → produces a structured offer. Reasoning, tool calls (including raw MCP request/response pairs), and the offer are logged as separate, independently auditable artifacts.

### 5.4 Theory-of-Mind (ToM) Consistency Auditor — extended from ELICIT
Runs after every turn on a separate model. Checks:
1. Reasoning-offer consistency (as in ELICIT).
2. Reasoning-tool consistency: did the offer contradict the agent's own real tool output (e.g., ignored a PPI-derived benchmark or a risk flag).
3. **Tool-provenance consistency (new):** did the agent's reasoning cite a tool result it never actually retrieved via a logged MCP call — this is the direct check against an agent fabricating grounding it doesn't have, which is a real and current failure mode of tool-using LLMs, not a hypothetical one.

### 5.5 Structured Memory Module — ported from SEAM
Generate→Reflect→Curate cycle, Self-BLEU/embedding drift health metrics, ground-truth-transcript cross-check for anchoring/poisoning claims, extended to also cross-check fabricated tool-result claims against the real MCP call log (not just conversational claims).

### 5.6 Human Approval Gate (new — this is the missing "real prod" pattern)
Any offer that would finalize a contract term beyond a configured stakes threshold (e.g., price beyond X% of the principal's target value, or any liability-cap change flagged high-risk by the risk-checker) is held in a `pending_approval` state and streamed to the dashboard as an explicit approval request, rather than auto-finalized. A human (you, in the demo; a designated approver, in a real deployment) approves, rejects, or requests revision before the contract state advances. This is not an afterthought feature — it is the component that makes the system honestly describable as "agentic with bounded autonomy," which is the actual production pattern for consequential agentic systems in 2026, not full unsupervised autonomy.

### 5.7 Guardrail Layer (hard constraints, unchanged principle)
No offer outside `authorized_mandate` can ever be finalized, enforced in plain validation code independent of LLM compliance — this operates beneath and independently of the approval gate; the guardrail is absolute, the approval gate is for judgment calls within the mandate that still warrant a second look.

### 5.8 Adversarial Bad-Faith Agent
Persona set: false urgency, false authority, false anchoring, stalling, **and fabricated tool-provenance claims** (asserting a market rate or precedent it never actually queried via MCP). Used in a dedicated red-team eval suite to verify the ToM auditor and memory module actually catch real tool-fabrication, not just conversational lying.

### 5.9 Eval Harness
Golden scenarios built using real historical procurement data pulled from the USAspending.gov corpus (real past deals as reference points for "was this a reasonable outcome"), not synthetic principal configurations invented from nothing. Metrics: deal closure rate by ZOPA width, mean distance from Nash Bargaining Solution, mandate violation rate (must be 0%), adversarial catch rate (target ≥90%, broken out separately for tool-fabrication attempts specifically), tool-call appropriateness rate, tool-provenance-fabrication rate (target 0%, and every instance must be caught).

### 5.10 Real-Time Observability & Dashboard
Every event — reasoning trace, MCP tool call fired with real request payload, MCP tool result received, offer issued, ToM score, memory health delta, guardrail check, approval-gate request/decision — published to Redis the instant it happens, forwarded over WebSocket to any connected dashboard client. Two-column live view (Buyer/Seller) plus a shared strip for contract state, audit scores, and pending approvals requiring your input in real time.

---

## 6. Repository Structure

```
batna/
├── engine/
│   ├── contract.py
│   ├── principal.py
│   └── scoring.py                 # ZOPA, Nash Bargaining Solution
├── mcp_servers/
│   ├── market_data_server/        # wraps FRED/BLS PPI APIs
│   ├── precedent_server/          # FAISS/BM25/RRF over USAspending.gov corpus
│   └── registry_client.py         # dynamic tool discovery
├── tools/
│   ├── risk_checker.py            # in-process, rules cited to real standards
│   └── surplus_simulator.py       # in-process, pure game theory
├── agents/
│   ├── buyer.py
│   ├── seller.py
│   ├── adversary.py
│   └── graph.py                   # LangGraph orchestration, dynamic tool-call edges
├── audit/
│   ├── tom_auditor.py             # extended from ELICIT, tool-provenance checks
│   └── schemas.py
├── memory/
│   ├── curator.py                 # ported from SEAM
│   ├── health_metrics.py
│   └── poison_detection.py        # includes MCP-call-log cross-check
├── guardrails/
│   ├── mandate_enforcement.py
│   └── approval_gate.py           # human-in-the-loop escalation
├── api/
│   ├── main.py
│   ├── routes/
│   └── websocket.py
├── observability/
│   ├── tracing.py
│   └── cost_tracking.py
├── eval/
│   ├── scenarios/                 # built from real USAspending.gov reference deals
│   ├── judge.py
│   ├── score.py
│   └── run_eval.py
├── dashboard/
│   ├── src/
│   └── vite.config.ts
├── tests/
│   ├── unit/
│   ├── integration/
│   └── eval_regression/
├── docker-compose.yml             # includes MCP server containers
├── Dockerfile
├── fly.toml
├── pyproject.toml
├── .github/workflows/ci.yml
└── README.md
```

---

## 7. Phased Build Plan with Exit Conditions

**Phase 0 — Scaffold & Config**
Build: repo skeleton, Pydantic config, ruff/mypy strict, Docker Compose (Postgres + Redis), CI on lint/type-check.
DoD: `docker-compose up` works; CI passes on empty commit.

**Phase 1 — Deterministic Negotiation Engine**
Build: contract/principal schema, ZOPA, Nash Bargaining Solution, unit tests against hand-computed values.
DoD: 100% unit coverage; ZOPA/NBS verified correct.

**Phase 2 — Real Data Pipelines (do this before any agent code)**
Build: FRED/BLS API client with real credential handling and rate-limit respect; USAspending.gov API client and bulk pull of a real procurement award corpus; FAISS/BM25/RRF index built over that real corpus.
DoD: you can query the FRED/BLS client and get a real, current PPI value for a real industry code; you can query the precedent index and get back real award records with real dollar amounts and real agency/vendor names, verified by spot-checking 5 results against the live USAspending.gov website.

**Phase 3 — MCP Servers**
Build: `market_data_server` and `precedent_server` as real, independently runnable MCP servers (stdio or HTTP transport), each exposing a properly schema'd tool.
DoD: you can connect to each MCP server with a generic MCP client (not your own agent code) and successfully call the tool end-to-end — this proves it's a genuine external capability, not code masquerading as one.

**Phase 4 — In-Process Tools**
Build: `risk_checker` with rules traced to a cited real standard (document the citation in the code), `surplus_simulator`.
DoD: risk checker's rule source is documented and defensible if asked "where did this threshold come from" in an interview.

**Phase 5 — Single Tool-Using Agent, Dynamic Tool Selection**
Build: Buyer Agent wired to query the MCP registry for available tools each session (not a hardcoded list), decide autonomously whether/which to call, against a scripted counterparty.
DoD: across 20+ runs, agent calls at least one real MCP tool before its opening offer in the large majority of cases; verify by diffing agent claims against the actual MCP call log that it never references a result it didn't really fetch.

**Phase 6 — Two Tool-Using Agents, Full Loop**
Build: Seller Agent as full tool-using LLM agent; LangGraph turn-based loop to agreement/deadlock/round-exhaustion.
DoD: 20+ full sessions across varied ZOPA configurations, no crashes, correct deadlock detection.

**Phase 7 — Real-Time Streaming**
Build: Redis pub/sub for every event type, FastAPI WebSocket endpoint, minimal dashboard rendering the live feed including raw MCP request/response payloads.
DoD: watch a Phase 6 negotiation stream live in a browser, including visible real tool call payloads, with no polling.

**Phase 8 — ToM Auditor with Tool-Provenance Checking**
Build: extend ELICIT's audit schema with tool-provenance verification against the real MCP call log.
DoD: construct 3 reasoning-offer contradictions, 3 reasoning-tool contradictions, and 3 fabricated-tool-provenance cases (agent claims a result it never fetched); auditor correctly flags all 9.

**Phase 9 — Memory + Poisoning Detection**
Build: SEAM port extended to cross-check fabricated tool claims against the real MCP call log.
DoD: counterparty falsely claims a market rate it never queried; memory module flags and rejects it before belief-state update.

**Phase 10 — Guardrails + Human Approval Gate**
Build: hard mandate enforcement; approval-gate logic with configurable stakes threshold; dashboard UI for approving/rejecting/requesting revision on a pending offer.
DoD: (a) 20+ prompt-injection attempts to exceed mandate are blocked 100% of the time; (b) a deliberately high-stakes offer correctly halts at `pending_approval` and does not finalize until you explicitly approve it via the dashboard.

**Phase 11 — Adversarial Agent + Red-Team Suite**
Build: manipulative persona set including fabricated tool-provenance claims.
DoD: ≥90% adversarial catch rate across the red-team suite, tool-fabrication attempts broken out and reported separately.

**Phase 12 — Eval Harness + CI Gating**
Build: golden scenarios built from real USAspending.gov reference deals, full scoring pipeline, CI regression gate.
DoD: intentionally break the risk-checker or approval gate and confirm CI catches the regression.

**Phase 13 — Full Observability**
Build: OpenTelemetry tracing including MCP round-trip latency, cost tracking.
DoD: reconstruct full causal chain and cost for any completed session from stored data alone.

**Phase 14 — Dashboard Polish**
Build: full live view, historical browser, approval-gate interaction, red flags for guardrail/adversarial catches.
DoD: a stranger can watch and understand a negotiation, including approving a pending offer, without narration.

**Phase 15 — Deployment**
Build: `fly.toml` covering the API and MCP server containers, Postgres/Redis on Fly, dashboard on Vercel.
DoD: a hiring manager gets a URL, starts a session, watches it live, and can even approve/reject a pending offer themselves — no local setup, no you present.

**Phase 16 — Writeup & Demo**
Build: README connecting to ELICIT/SEAM, 2–3 minute demo showing the adversarial agent's fabricated tool-provenance claim caught live, headline metrics stated plainly with real numbers.
DoD: a technical stranger understands what it does, why it's hard, and which number proves it works, in under 5 minutes plus the video.

---

## 8. Success Metrics

- Deal closure rate, by ZOPA width.
- Mean distance from Nash Bargaining Solution for closed deals.
- Mandate violation rate: 0%, hard fail otherwise.
- Adversarial manipulation catch rate: ≥90%, tool-fabrication attempts reported separately.
- Tool-call appropriateness rate.
- Tool-provenance fabrication rate: target 0%, every instance must be caught by the auditor.
- Approval-gate correctness: percentage of genuinely high-stakes offers correctly routed to approval (target 100% — a missed escalation is a serious failure).
- Memory health: Self-BLEU trend below your defined collapse threshold.
- Cost per completed negotiation, p50/p95 latency per turn and per MCP tool call.
- End-to-end dashboard event latency (target sub-second).

---

## 9. Risks & Honest Mitigations

- **Real external APIs (FRED, BLS, USAspending.gov) have rate limits and occasional downtime.** Build caching and graceful degradation from Phase 2 — an agent whose market-data tool times out must have a defined fallback behavior (retry, then reason with an explicit "data unavailable" caveat), not silently fail or fabricate a number. This is itself a real production concern, not an edge case to wave away.
- **MCP server operational complexity is new to you.** Budget real time in Phase 3 — running your own MCP servers (not just consuming someone else's) has a learning curve. Do it early, not under deployment pressure.
- **Sub-4B local models may still underperform on judgment even at Qwen3:4B.** Validate this yourself in Phase 5 with real logged runs before trusting it for anything you'll present — if judgment quality is inadequate, escalate to the Anthropic API path earlier than planned rather than shipping a demo built on an unreliable local model.
- **Non-determinism makes eval noisy.** Run each golden scenario across multiple seeds, matching your SEAM discipline (5 seeds, 162 runs).
- **Domain narrowness criticism.** Preempt in the README: tools, auditor, and memory layer are domain-agnostic; the negotiation engine and the two data sources (FRED/BLS, USAspending.gov) are the domain-specific wrapper — true only if you keep that separation in code.

---

## 10. Open Design Decisions to Resolve Before Phase 1

1. Exact contract term list (recommend the 6 in Section 5.1, no more, for v1).
2. Fixed vs. adaptive round budget.
3. Model split confirmed: Qwen3:4B minimum for local negotiating agents, Anthropic Sonnet for hosted negotiating agents, Anthropic Haiku or Qwen3:4B for the auditor/judge — decide the hosted-vs-local split for the actual public demo now, since it affects the Fly.io cost budget.
4. Approval-gate stakes threshold: what percentage deviation from target value, or which risk-checker flags, trigger mandatory human approval — define this explicitly, do not leave it implicit in code.
5. USAspending.gov corpus scope: which industry/NAICS codes to pull for the precedent index, given API pull volume and your available compute for indexing — recommend picking 2–3 NAICS codes relevant to a plausible procurement scenario (e.g., IT services, logistics) rather than the full corpus.

---

## 11. Glossary

- **BATNA** — Best Alternative to a Negotiated Agreement.
- **Reservation Value** — the worst deal a party will still accept.
- **ZOPA** — Zone of Possible Agreement.
- **Nash Bargaining Solution** — game-theoretic reference point for a fair surplus split.
- **MCP (Model Context Protocol)** — the open protocol standard for exposing tools/capabilities to an LLM agent as external, independently callable services, rather than in-process functions.
- **Tool-provenance fabrication** — an agent claiming a tool result it never actually retrieved, the specific failure mode the auditor and memory module are built to catch.

---

## 12. Timeline (Realistic)

6–8 weeks at above-average effort. The real-data and MCP-serving work (Phases 2–4) adds real time versus a synthetic-data build, but it is the difference between a project that survives technical scrutiny and one that doesn't — do not compress it. Phases 0–4 (~1.5–2 weeks), Phases 5–7 (~1.5 weeks), Phases 8–11 (~2 weeks, the intellectual core), Phases 12–14 (~1 week), Phases 15–16 (~1 week buffer). If Phase 3 (MCP servers) or Phase 10 (approval gate + guardrails) run long, that is expected and correct — those are the two phases that make the difference between "looks agentic" and "is agentic."

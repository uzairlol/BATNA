"""Application configuration using Pydantic Settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for BATNA."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    environment: str = "development"
    log_level: str = "INFO"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Persistence & Cache
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/batna"
    redis_url: str = "redis://localhost:6379/0"

    # Phase 2 data cache
    precedent_corpus_path: str = "data/precedent_corpus.json"

    # Phase 4 in-process risk-checker thresholds. These are documented policy
    # defaults; the source each threshold traces to is recorded in
    # batna.tools.risk_checker. Override via env or .env.
    risk_price_deviation_pct: float = 0.25
    risk_min_liability_cap_pct: float = 0.20
    risk_termination_notice_min_days: int = 1

    # External APIs
    fred_api_key: str = ""
    bls_api_key: str = ""

    # LLMs
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    default_local_model: str = "qwen2.5:7b"
    default_hosted_model: str = "claude-3-5-sonnet-20241022"
    auditor_model: str = "claude-3-5-haiku-20241022"

    # Phase 5 agent behaviour. The buyer agent discovers MCP tools at session start
    # and autonomously decides which to call before its opening offer; these bounds
    # keep the agentic loop finite and auditable. Override via env or .env.
    agent_model: str = "qwen2.5:7b"
    agent_max_tool_calls: int = 6
    # Phase 6 negotiation clock: agents concede in small (10%) steps, so a deal
    # closes after ~7-8 exchanges rather than on the first offer. This higher
    # default gives the graph room to run a genuine multi-round negotiation.
    agent_max_rounds: int = 12
    agent_tool_call_log_dir: str = ""  # optional directory for durable JSONL call logs

    # Phase 6 full-loop negotiation. Structured multi-term offers are parsed from
    # the agent's OFFER_JSON=<json> text; max_offer_retries bounds re-prompting when
    # the model emits text without a valid payload (spec §2.5: failure handled, not
    # assumed away). The seller has its own model setting so the two sides can be
    # given different models in production (avoiding shared blind spots).
    agent_max_offer_retries: int = 3
    seller_model: str = "qwen2.5:7b"

    # Phase 7 demo driver: "live" drives a **real** Ollama model over the
    # LangGraph tool-calling loop so the dashboard streams genuine model reasoning
    # and tool decisions.  If the Ollama server is unreachable the runner falls
    # back to "scripted" (hermetic deterministic stand-in) and labels the session
    # accordingly.  Set BATNA_LLM_MODE=scripted to force the deterministic path.
    llm_mode: str = "live"

    # Phase 7 real-time streaming. Redis pub/sub channels are per-session under a
    # shared prefix; the bounded list is the replay buffer a late-joining WebSocket
    # client reads on connect so it sees the whole session, not just what streams
    # after it attaches.
    redis_pubsub_channel_prefix: str = "session"
    stream_event_buffer_max: int = 500
    stream_replay_limit: int = 100


settings = Settings()

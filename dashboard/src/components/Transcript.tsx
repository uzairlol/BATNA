import { useState } from "react";
import type { StreamEvent } from "../feed";

interface TranscriptProps {
  events: StreamEvent[];
  mode: string | null;
  model: string | null;
}

const TOOL_LABEL: Record<string, string> = {
  get_market_benchmark: "consulted live market data",
  search_precedents: "searched precedent awards",
  check_contract_risk: "ran a contract-risk check",
};

function sideLabel(side?: string | null): string {
  return side === "seller" ? "Seller" : "Buyer";
}

function formatPrice(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n)
    ? `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`
    : String(v ?? "?");
}

function offerLine(p: Record<string, unknown>): string {
  const parts = [
    `${formatPrice(p.price)}/yr`,
    `net ${p.payment_terms_days ?? "?"}d`,
    `SLA ${p.delivery_sla_days ?? "?"}d`,
    `liab cap ${p.liability_cap_pct ?? "?"}%`,
    `${p.contract_duration_months ?? "?"}mo`,
    `${p.termination_notice_days ?? "?"}d notice`,
  ];
  return parts.join(" · ");
}

function toolPrev(p: Record<string, unknown>): string {
  const args = p.arguments as Record<string, unknown> | undefined;
  const industry = args?.industry;
  return typeof industry === "string" ? `(${industry})` : "";
}

function outcomeSentence(outcome: unknown): string {
  const o = String(outcome ?? "?");
  if (o === "agreement") return "Agreement reached — the deal is done.";
  if (o === "no_zopa") return "No overlap in mandates — deadlock, correctly detected.";
  if (o === "round_exhaustion") return "Rounds exhausted without agreement.";
  return o;
}

export default function Transcript({ events, mode, model }: TranscriptProps) {
  if (events.length === 0) {
    return (
      <div className="transcript">
        <div className="empty">
          <p>No negotiation yet.</p>
          <p>Press “Start negotiation” to watch the buyer and seller talk it out live.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="transcript">
      {events.map((ev) => (
        <Row key={`${ev.session_id}-${ev.seq}`} ev={ev} mode={mode} model={model} />
      ))}
    </div>
  );
}

function Row({
  ev,
  mode,
  model,
}: {
  ev: StreamEvent;
  mode: string | null;
  model: string | null;
}) {
  const p = ev.payload ?? {};
  switch (ev.type) {
    case "session_start":
      return (
        <div className="meta meta-head">
          <div className="meta-title">Negotiation session</div>
          <div className="meta-line">
            mode: <b>{mode ?? "…"}</b>
            {model ? ` · model: ${model}` : ""} · max rounds:{" "}
            {String(p.max_rounds ?? "?")}
          </div>
        </div>
      );

    case "discovery": {
      const buyerN = Array.isArray(p.buyer_tools) ? p.buyer_tools.length : 0;
      const sellerN = Array.isArray(p.seller_tools) ? p.seller_tools.length : 0;
      return (
        <div className="meta">
          Agents discovered live tools — buyer {buyerN}, seller {sellerN}
        </div>
      );
    }

    case "reasoning":
      return (
        <div className={`turn turn-${ev.side === "seller" ? "seller" : "buyer"}`}>
          <div className="bubble">
            <div className="bubble-label">{sideLabel(ev.side)}</div>
            <div className="bubble-text">{String(p.text ?? "")}</div>
          </div>
        </div>
      );

    case "offer":
      return (
        <div className={`turn turn-${ev.side === "seller" ? "seller" : "buyer"}`}>
          <div className="bubble bubble-offer">
            <div className="bubble-label">{sideLabel(ev.side)} proposes</div>
            <div className="offer-terms">{offerLine(p)}</div>
          </div>
        </div>
      );

    case "tool_call_start":
    case "tool_call_result":
    case "tool_call_error":
      return (
        <div className={`turn turn-${ev.side === "seller" ? "seller" : "buyer"}`}>
          <ToolChip ev={ev} />
        </div>
      );

    case "acceptance_check": {
      const acceptable = Boolean(p.acceptable);
      const failures = Array.isArray(p.failures) ? (p.failures as string[]) : [];
      return (
        <div className={`meta ${acceptable ? "meta-ok" : ""}`}>
          {sideLabel(ev.side)} acceptance check —{" "}
          {acceptable ? "accepted" : "not yet"}
          {failures.length > 0 ? `: ${failures.join(", ")}` : ""}
        </div>
      );
    }

    case "finalize": {
      const accepted = p.accepted_offer as
        | Record<string, unknown>
        | null
        | undefined;
      return (
        <div className="meta meta-final">
          <div className="meta-title">{outcomeSentence(p.outcome)}</div>
          <div className="meta-line">
            rounds: {String(p.rounds_elapsed ?? "?")}
            {accepted ? ` · agreed at ${formatPrice(accepted.price)}` : ""}
          </div>
        </div>
      );
    }

    case "session_end":
      return (
        <div className="meta">
          Session ended{p.outcome ? ` — ${outcomeSentence(p.outcome)}` : ""}
        </div>
      );

    case "error":
      return <div className="meta meta-error">error: {String(p.message ?? "")}</div>;

    default:
      return <div className="meta">{ev.type}</div>;
  }
}

function ToolChip({ ev }: { ev: StreamEvent }) {
  const [open, setOpen] = useState(false);
  const p = ev.payload ?? {};
  const name = String(p.name ?? "?");
  const verb =
    ev.type === "tool_call_start"
      ? (TOOL_LABEL[name] ?? `called ${name}`)
      : ev.type === "tool_call_error"
        ? `called ${name} — errored`
        : `got ${name} result`;

  return (
    <div className={`toolchip ${ev.type === "tool_call_error" ? "toolchip-err" : ""}`}>
      <button
        className="toolchip-btn"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="status-dot" aria-hidden />
        <span className="toolchip-text">
          {sideLabel(ev.side)} {verb} {toolPrev(p)}
        </span>
        <span className="toolchip-caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <pre className="toolchip-json">{JSON.stringify(ev.payload, null, 2)}</pre>
      )}
    </div>
  );
}
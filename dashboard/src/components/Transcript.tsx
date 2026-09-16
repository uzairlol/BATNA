import { useState } from "react";
import type { StreamEvent } from "../feed";

interface TranscriptProps {
  events: StreamEvent[];
  mode: string | null;
  model: string | null;
  untilAgreement?: boolean;
}

const TOOL_LABEL: Record<string, string> = {
  get_market_benchmark: "Live market data",
  search_precedents: "Precedent awards",
  check_contract_risk: "Contract risk",
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
    `net ${p.payment_terms_days ?? "?"}d`,
    `SLA ${p.delivery_sla_days ?? "?"}d`,
    `liab cap ${p.liability_cap_pct ?? "?"}%`,
    `${p.contract_duration_months ?? "?"}mo`,
    `${p.termination_notice_days ?? "?"}d notice`,
  ];
  return parts.join("  ·  ");
}

function toolPrev(p: Record<string, unknown>): string {
  const args = p.arguments as Record<string, unknown> | undefined;
  const industry = args?.industry;
  return typeof industry === "string" ? `(${industry})` : "";
}

function toolTitle(name: string): string {
  return TOOL_LABEL[name] ?? name;
}

function outcomeSentence(outcome: unknown): string {
  const o = String(outcome ?? "?");
  if (o === "agreement") return "Agreement reached — the deal is done. 🎉";
  if (o === "no_zopa") return "No overlap in mandates — deadlock, correctly detected.";
  if (o === "round_exhaustion") return "Rounds exhausted without agreement.";
  return o;
}

function fmtTime(ts: string): string {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

interface Row {
  kind: "action" | "msg";
  side?: "buyer" | "seller";
  sub?: "text" | "offer" | "tool";
  text?: string;
  event?: StreamEvent;
  p?: Record<string, unknown>;
  cls?: string;
  ts?: string;
  grouped?: boolean;
}

/** Flatten stream events into lightweight chat rows; group consecutive same-side messages. */
function buildRows(
  events: StreamEvent[],
  mode: string | null,
  model: string | null,
  untilAgreement: boolean,
): Row[] {
  const rows: Row[] = [];
  for (const ev of events) {
    const p = ev.payload ?? {};
    const side = ev.side === "seller" ? "seller" : "buyer";
    switch (ev.type) {
      case "session_start":
        rows.push({
          kind: "action",
          text: `Negotiation started · ${mode ?? "…"}${
            model ? ` · ${model}` : ""
          } · stop: ${untilAgreement ? "until agreement" : `round ${String(p.max_rounds ?? "?")}`}`,
          ts: ev.ts,
        });
        break;
      case "discovery": {
        const buyerN = Array.isArray(p.buyer_tools) ? p.buyer_tools.length : 0;
        const sellerN = Array.isArray(p.seller_tools) ? p.seller_tools.length : 0;
        rows.push({
          kind: "action",
          text: `Agents discovered live tools — buyer ${buyerN}, seller ${sellerN}`,
          ts: ev.ts,
        });
        break;
      }
      case "reasoning":
        rows.push({ kind: "msg", side, sub: "text", text: String(p.text ?? ""), ts: ev.ts });
        break;
      case "offer":
        rows.push({ kind: "msg", side, sub: "offer", p, ts: ev.ts });
        break;
      case "tool_call_start":
      case "tool_call_result":
      case "tool_call_error":
        rows.push({ kind: "msg", side, sub: "tool", event: ev, p, ts: ev.ts });
        break;
      case "acceptance_check": {
        const acceptable = Boolean(p.acceptable);
        const failures = Array.isArray(p.failures) ? (p.failures as string[]) : [];
        rows.push({
          kind: "action",
          cls: acceptable ? "ok" : "",
          text: `${sideLabel(ev.side)} — accept${
            acceptable ? "ed" : "ed? not yet"
          }${failures.length > 0 ? ` · ${failures.join(", ")}` : ""}`,
          ts: ev.ts,
        });
        break;
      }
      case "audit": {
        // Theory-of-Mind audit of the latest reasoning/tool action.
        const verdict = String(p.verdict ?? p.result ?? "");
        const consistent = p.consistent === true || verdict === "consistent";
        const tom = typeof p.tom_score === "number" ? p.tom_score : null;
        const actionText = [
          `Auditor reviewed ${sideLabel(ev.side)} — ${consistent ? "consistent ✓" : "inconsistent"}`,
          tom !== null && Number.isFinite(tom) ? `· ToM ${(tom * 100).toFixed(0)}%` : "",
          verdict ? `· ${verdict}` : "",
        ]
          .filter(Boolean)
          .join(" ");
        rows.push({ kind: "action", cls: consistent ? "audit" : "audit-warn", text: actionText, ts: ev.ts });
        break;
      }
      case "approval_gate": {
        // Human-in-the-loop escalation held at a pending_approval state.
        const approved = p.approved;
        const decision =
          approved === true
            ? "Approval granted — autonomous finalization may proceed"
            : approved === false
              ? "Approval denied — action held for revision"
              : "⚠ High-stakes action escalated — awaiting human approval";
        rows.push({ kind: "action", cls: "gate", text: decision, ts: ev.ts });
        break;
      }
      case "finalize":
        rows.push({ kind: "action", cls: "final", text: outcomeSentence(p.outcome), ts: ev.ts });
        break;
      case "session_end":
        rows.push({
          kind: "action",
          cls: "end",
          text: `Session ended — ${outcomeSentence(p.outcome)}`,
          ts: ev.ts,
        });
        break;
      case "error":
        rows.push({
          kind: "action",
          cls: "err",
          text: `error: ${String(p.message ?? "")}`,
          ts: ev.ts,
        });
        break;
      default:
        rows.push({ kind: "action", text: ev.type, ts: ev.ts });
    }
  }
  return rows.map((r, i) => {
    const prev = rows[i - 1];
    const grouped = r.kind === "msg" && prev?.kind === "msg" && prev.side === r.side;
    return { ...r, grouped };
  });
}

export default function Transcript({
  events,
  mode,
  model,
  untilAgreement = false,
}: TranscriptProps) {
  if (events.length === 0) {
    return (
      <div className="thread">
        <div className="empty">
          <div className="empty-emoji">💬</div>
          <p>No conversation yet.</p>
          <p>Press “Start negotiation” and the two agents will start chatting.</p>
        </div>
      </div>
    );
  }

  const rows = buildRows(events, mode, model, untilAgreement);
  return (
    <div className="thread">
      <div className="thread-date">Today</div>
      {rows.map((r, i) =>
        r.kind === "action" ? (
          <ActionLine key={i} row={r} />
        ) : (
          <MessageRow key={i} row={r} prevIsSame={rows[i - 1]?.side === r.side} />
        ),
      )}
    </div>
  );
}
function ActionLine({ row }: { row: Row }) {
  return (
    <div className={`action action-${row.cls ?? "plain"}`}>
      {row.text}
      {row.ts && <span className="action-ts">{fmtTime(row.ts)}</span>}
    </div>
  );
}

function MessageRow({ row, prevIsSame }: { row: Row; prevIsSame: boolean }) {
  const sent = row.side === "buyer";
  const grouped = Boolean(prevIsSame);
  return (
    <div className={`msg ${sent ? "msg-sent" : "msg-recv"} ${grouped ? "grouped" : "first"}`}>
      {!sent && (
        <span className={`avatar avatar-${row.side === "seller" ? "seller" : "buyer"}`}>
          {row.side === "seller" ? "S" : "B"}
        </span>
      )}
      <div className="bubble">
        {!grouped && <span className="bubble-time">{fmtTime(row.ts ?? "")}</span>}
        {row.sub === "offer" ? <OfferCard p={row.p ?? {}} side={row.side} /> : null}
        {row.sub === "text" ? <span className="bubble-text">{row.text}</span> : null}
        {row.sub === "tool" && row.event ? <ToolChip ev={row.event} side={row.side} /> : null}
        {sent && !grouped && (
          <span className="read-tick" title="Negotiator delivered">
            ✓✓
          </span>
        )}
      </div>
    </div>
  );
}

function OfferCard({ p, side }: { p: Record<string, unknown>; side?: string }) {
  return (
    <div className="offer-card">
      <div className="offer-head">
        <span className="offer-tag">{sideLabel(side)} proposes</span>
        <span className="offer-price">
          {formatPrice(p.price)}
          <span className="offer-unit">/yr</span>
        </span>
      </div>
      <div className="offer-terms">{offerLine(p)}</div>
    </div>
  );
}

function ToolChip({ ev, side }: { ev: StreamEvent; side?: string }) {
  const [open, setOpen] = useState(false);
  const p = ev.payload ?? {};
  const name = String(p.name ?? "?");
  const verb =
    ev.type === "tool_call_start"
      ? `using ${toolTitle(name)}`
      : ev.type === "tool_call_error"
        ? `${toolTitle(name)} errored`
        : `${toolTitle(name)} ready`;

  return (
    <div className={`toolchip ${ev.type === "tool_call_error" ? "toolchip-err" : ""}`}>
      <button className="toolchip-btn" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="status-dot" aria-hidden />
        <span className="toolchip-text">
          {sideLabel(side)} {verb} {toolPrev(p)}
        </span>
        <span className="toolchip-caret">{open ? "▾" : "▸"}</span>
      </button>
      {open && <pre className="toolchip-json">{JSON.stringify(ev.payload, null, 2)}</pre>}
    </div>
  );
}
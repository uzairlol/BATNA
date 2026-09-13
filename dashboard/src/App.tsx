import { useCallback, useEffect, useRef, useState } from "react";
import EventFeed from "./components/EventFeed";
import Metrics from "./components/Metrics";
import Transcript from "./components/Transcript";
import ContactCard from "./components/ContactCard";
import {
  LiveFeed,
  createSession,
  startNegotiation,
  summaryFromEvent,
  type ConnectionState,
  type EventHandler,
  type SessionSummary,
  type StreamEvent,
} from "./feed";

const KINDS = ["wide", "narrow", "asymmetric", "no_zopa"] as const;
type View = "transcript" | "log";

export default function App() {
  const [kind, setKind] = useState<(typeof KINDS)[number]>("wide");
  const [untilAgreement, setUntilAgreement] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const [conn, setConn] = useState<ConnectionState>("closed");
  const [view, setView] = useState<View>("transcript");
  const feedRef = useRef<LiveFeed | null>(null);
  const seenSeq = useRef<Set<number>>(new Set());

  const onEvent: EventHandler = useCallback((event) => {
    // Dedup replay + live frames by the backend's monotonic per-session seq so a
    // reconnect (or a buffered replay racing a live publish) can never render a
    // duplicate event or double-count the feed.
    if (seenSeq.current.has(event.seq)) return;
    seenSeq.current.add(event.seq);
    setEvents((prev) => [...prev, event]);
    // The server authors the metrics blob on session_end; auto-show the modal.
    if (event.type === "session_end") {
      const s = summaryFromEvent(event);
      if (s) setSummary(s);
    }
  }, []);

  const start = useCallback(async () => {
    setError(null);
    setSummary(null);
    setEvents([]);
    seenSeq.current = new Set();
    feedRef.current?.stop();
    try {
      const { session_id } = await createSession(kind, untilAgreement);
      setSessionId(session_id);
      await startNegotiation(session_id);
      const feed = new LiveFeed(session_id, onEvent, setConn);
      feedRef.current = feed;
      feed.start();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [kind, untilAgreement, onEvent]);

  // Keep the active pane pinned to the newest event as it streams in.
  useEffect(() => {
    const el = document.querySelector<HTMLElement>(
      view === "transcript" ? ".thread" : ".feed",
    );
    if (el) el.scrollTop = el.scrollHeight;
  }, [events, view]);

  // Dismiss the summary modal with Escape.
  useEffect(() => {
    if (!summary) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSummary(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [summary]);

  const startEvent = events.find((e) => e.type === "session_start");
  const mode = (startEvent?.payload?.run_mode as string) || null;
  const model = (startEvent?.payload?.run_model as string) || null;
  const offers = events.filter((e) => e.type === "offer").length;
  const toolCalls = events.filter((e) => e.type === "tool_call_start").length;
  const currentRound =
    events
      .filter((e) => e.type === "offer")
      .reduce<number>((max, e) => {
        const r = (e.payload.round as number | undefined) ?? 0;
        return Number.isFinite(r) && r > max ? r : max;
      }, 0) +
    (offers > 0 ? 1 : 0);

  return (
    <div className="app">
      <div className="chrome">
        <header className="topbar">
          <div className="brand">
            <span className="brand-dot" />
            BATNA <span className="brand-ph">· live negotiation</span>
          </div>
          <div className="controls">
            <label>
              Scenario
              <select
                value={kind}
                onChange={(e) => setKind(e.target.value as (typeof KINDS)[number])}
                disabled={conn === "open"}
              >
                {KINDS.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
            <label
              className="checkbox-label"
              title="Ignore the round budget and keep negotiating until agreement (or hard cap)"
            >
              <input
                type="checkbox"
                checked={untilAgreement}
                onChange={(e) => setUntilAgreement(e.target.checked)}
                disabled={conn === "open"}
              />
              Until agreement
            </label>
            <button onClick={start} disabled={conn === "open"}>
              Start negotiation
            </button>
          </div>
        </header>

        <div className="statusbar">
          <span className={`pill pill-${conn}`}>ws: {conn}</span>
          {sessionId && <span className="pill">session: {sessionId.slice(0, 8)}</span>}
          {untilAgreement && (
            <span className="pill pill-accent">mode: until agreement</span>
          )}
          {mode && (
            <span className={`pill ${mode === "live" ? "pill-open" : "pill-muted"}`}>
              mode: {mode}
            </span>
          )}
          {model && <span className="pill">model: {model}</span>}
          {events.length > 0 && <span className="pill">events: {events.length}</span>}
          {offers > 0 && <span className="pill">offers: {offers}</span>}
          {toolCalls > 0 && <span className="pill">tool calls: {toolCalls}</span>}
          {error && <span className="pill pill-error">error: {error}</span>}
        </div>
      </div>

      <main className="stage">
        <div className="phone" aria-label="Negotiation chat">
          <ContactCard
            kind={kind}
            untilAgreement={untilAgreement}
            conn={conn}
            sessionId={sessionId}
            mode={mode}
            model={model}
            hasMessages={events.length > 0}
            round={currentRound}
          />

          <nav className="view-toggle" aria-label="Dashboard view">
            <button
              className={view === "transcript" ? "active" : ""}
              onClick={() => setView("transcript")}
            >
              Negotiation
            </button>
            <button
              className={view === "log" ? "active" : ""}
              onClick={() => setView("log")}
            >
              Raw event log
            </button>
          </nav>

          <div className="view-body">
            {view === "transcript" ? (
              <Transcript
                events={events}
                mode={mode}
                model={model}
                untilAgreement={untilAgreement}
              />
            ) : (
              <EventFeed events={events} />
            )}
          </div>

          <div className="composer">
            <button className="composer-input" onClick={start} disabled={conn === "open"}>
              {conn === "open"
                ? "Negotiation in progress…"
                : events.length > 0
                  ? "Start a new negotiation…"
                  : "Start negotiation…"}
            </button>
            <button
              className="composer-send"
              onClick={start}
              disabled={conn === "open"}
              aria-label="Start negotiation"
            >
              ▲
            </button>
          </div>
        </div>
      </main>

      {summary && <MetricsModal summary={summary} onClose={() => setSummary(null)} />}
    </div>
  );
}

function MetricsModal({
  summary,
  onClose,
}: {
  summary: SessionSummary;
  onClose: () => void;
}) {
  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Negotiation summary" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div className="modal-title">Negotiation summary</div>
          <button className="modal-close" onClick={onClose} aria-label="Dismiss summary">
            ×
          </button>
        </div>
        <div className="modal-body">
          <Metrics summary={summary} />
        </div>
        <div className="modal-foot">
          <button onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
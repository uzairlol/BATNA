import type { StreamEvent } from "../feed";
import ToolCallRow from "./ToolCallRow";

const LABELS: Record<string, string> = {
  session_start: "Session started",
  session_end: "Session ended",
  discovery: "Tool discovery",
  reasoning: "Agent reasoning",
  tool_call_start: "Tool call",
  tool_call_result: "Tool result",
  tool_call_error: "Tool error",
  offer: "Offer",
  acceptance_check: "Acceptance check",
  finalize: "Finalize",
  error: "Error",
  audit: "Theory-of-Mind audit",
  approval_gate: "Approval gate",
};

function isToolCall(type: StreamEvent["type"]): boolean {
  return (
    type === "tool_call_start" || type === "tool_call_result" || type === "tool_call_error"
  );
}

export default function EventFeed({ events }: { events: StreamEvent[] }) {
  return (
    <main className="feed">
      {events.length === 0 ? (
        <div className="empty">
          <p>No events yet.</p>
          <p>Start a negotiation to watch a live BATNA session stream in.</p>
        </div>
      ) : (
        events.map((event, i) => {
          const label = LABELS[event.type] ?? event.type;
          const side = event.side ?? "";
          return (
            <article key={`${event.session_id}-${event.seq}-${i}`} className={`ev ev-${event.type}`}>
              <div className="ev-head">
                <span className="ev-seq">#{event.seq}</span>
                <span className="ev-type">{label}</span>
                {side && <span className={`side side-${side}`}>{side}</span>}
                <span className="ev-ts">{new Date(event.ts).toLocaleTimeString()}</span>
              </div>
              {isToolCall(event.type) ? (
                <ToolCallRow event={event} />
              ) : (
                <pre className="ev-payload">{JSON.stringify(event.payload, null, 2)}</pre>
              )}
            </article>
          );
        })
      )}
    </main>
  );
}
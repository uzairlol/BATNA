import { useState } from "react";
import type { StreamEvent } from "../feed";

interface ToolPayload {
  name?: string;
  arguments?: Record<string, unknown>;
  response?: unknown;
  error?: unknown;
}

/**
 * Renders a tool-call event with a summary line and a toggleable view of the
 * RAW JSON payload the backend streamed — the full request arguments and the
 * response text the MCP tool really returned.
 */
export default function ToolCallRow({ event }: { event: StreamEvent }) {
  const payload = (event.payload ?? {}) as ToolPayload;
  const [expanded, setExpanded] = useState(false);
  const args = payload.arguments ?? {};
  const argKeys = Object.keys(args);

  return (
    <div className="tool">
      <button className="tool-toggle" onClick={() => setExpanded((v) => !v)}>
        <span className="status-dot" aria-hidden />
        <code className="tool-name">{payload.name ?? "?"}</code>
        <span className="tool-args">
          {argKeys.length > 0 ? String(args[argKeys[0]]) : "(no args)"}
        </span>
        <span className="tool-caret">{expanded ? "▾" : "▸"}</span>
      </button>
      {expanded && (
        <pre className="tool-json">{JSON.stringify(event.payload, null, 2)}</pre>
      )}
    </div>
  );
}
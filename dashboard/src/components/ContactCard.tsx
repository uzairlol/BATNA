import type { ConnectionState } from "../feed";

interface ContactCardProps {
  kind: string;
  untilAgreement: boolean;
  conn: ConnectionState;
  sessionId: string | null;
  mode: string | null;
  model: string | null;
  hasMessages: boolean;
  round: number;
}

const KIND_LABEL: Record<string, string> = {
  wide: "Wide mandate",
  narrow: "Narrow mandate",
  asymmetric: "Asymmetric",
  no_zopa: "No ZOPA",
};

/**
 * iMessage-style "Business Chat" contact header for the negotiation thread.
 * Shows the two parties as a stacked avatar, a verified contact line and the
 * live status, with scenario/mode pills on the right hand side like an iOS
 * contact-detail bar.
 */
export default function ContactCard({
  kind,
  untilAgreement,
  conn,
  sessionId,
  mode,
  model,
  hasMessages,
  round,
}: ContactCardProps) {
  let statusText: string;
  let statusCls = "contact-live";
  if (conn === "open") {
    statusText = round > 0 ? `Negotiating… round ${round}` : "Negotiation started — listening live…";
    statusCls += " on";
  } else if (conn === "connecting") {
    statusText = "Connecting to session…";
    statusCls += " pending";
  } else if (hasMessages) {
    statusText = "Session ended";
  } else {
    statusText = "Idle — tap start to begin";
  }

  return (
    <header className="contact">
      <div className="contact-stack">
        <span className="avatar avatar-buyer" aria-hidden>
          B
        </span>
        <span className="avatar avatar-seller" aria-hidden>
          S
        </span>
        <span className={statusCls} aria-hidden />
      </div>

      <div className="contact-mid">
        <div className="contact-name">
          Buyer <i>vs</i> Seller
          <span className="contact-tick" title="Verified business chat">
            ✓
          </span>
        </div>
        <div className="contact-sub">
          <span className={`contact-status ${statusCls}`}>{statusText}</span>
          {mode && <span className="contact-mode">{mode}</span>}
          {sessionId && (
            <span className="contact-session">session {sessionId.slice(0, 6)}</span>
          )}
        </div>
      </div>

      <div className="contact-pills">
        <span className="pill pill-soft">{KIND_LABEL[kind] ?? kind}</span>
        {untilAgreement && <span className="pill pill-accent">until agreement</span>}
        {model && <span className="pill pill-soft" title="Model">{model}</span>}
      </div>
    </header>
  );
}
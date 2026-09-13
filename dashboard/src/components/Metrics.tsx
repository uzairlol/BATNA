import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SessionSummary } from "../feed";

interface MetricsProps {
  summary: SessionSummary;
}

const BUYER_COLOR = "#58a6ff";
const SELLER_COLOR = "#d29922";
const ZOPA_COLOR = "#3fb950";

function money(v: number | null): string {
  if (v === null || !Number.isFinite(v)) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function moneyK(v: number): string {
  return `$${Math.round(v / 1000)}k`;
}

function ms(v: number): string {
  if (!Number.isFinite(v) || v <= 0) return "—";
  if (v < 1000) return `${Math.round(v)}ms`;
  return `${(v / 1000).toFixed(1)}s`;
}

export default function Metrics({ summary }: MetricsProps) {
  const { outcome, roundLabel, agreed_price, bannerClass, label } = useMemo(() => {
    const o = summary.outcome;
    let lbl: string;
    let cls: string;
    if (o === "agreement") {
      lbl = "Agreement reached";
      cls = "banner-ok";
    } else if (o === "no_zopa") {
      lbl = "No agreement — mandates deadlocked from the start";
      cls = "banner-bad";
    } else {
      lbl = "No agreement — rounds exhausted without a deal";
      cls = "banner-warn";
    }
    return {
      outcome: o,
      roundLabel: `${summary.rounds_elapsed}${summary.until_agreement ? "" : ` / ${summary.max_rounds}`}`,
      agreed_price: summary.agreed_price,
      bannerClass: cls,
      label: lbl,
    };
  }, [summary]);

  const chartData = useMemo(() => {
    const b = summary.buyer?.offers ?? [];
    const s = summary.seller?.offers ?? [];
    const len = Math.max(b.length, s.length);
    const rows: Array<{ round: number; buyer: number | null; seller: number | null }> = [];
    for (let i = 0; i < len; i++) {
      rows.push({
        round: i + 1,
        buyer: i < b.length ? b[i] : null,
        seller: i < s.length ? s[i] : null,
      });
    }
    return rows;
  }, [summary]);

  const zone = summary.price_zone;
  const zopaLow = Math.max(zone.buyer_min, zone.seller_min);
  const zopaHigh = Math.min(zone.buyer_max, zone.seller_max);
  const hasZopa = zopaLow < zopaHigh;

  const allPrices = [
    zone.buyer_min,
    zone.buyer_max,
    zone.seller_min,
    zone.seller_max,
    ...(summary.buyer?.offers ?? []),
    ...(summary.seller?.offers ?? []),
  ].filter((v): v is number => Number.isFinite(v));
  const lo = Math.min(...(allPrices.length ? allPrices : [0]));
  const hi = Math.max(...(allPrices.length ? allPrices : [1]));

  const yDomain: [number, number] = [
    Math.floor((lo - (hi - lo) * 0.12) / 500) * 500,
    Math.ceil((hi + (hi - lo) * 0.12) / 500) * 500,
  ];

  return (
    <div className="metrics">
      <div className={`outcome-banner ${bannerClass}`}>
        <div className="outcome-title">{label}</div>
        <div className="outcome-sub">
          {outcome === "agreement"
            ? `Deal closed at ${money(agreed_price)} after ${summary.rounds_elapsed} round(s).`
            : `Buyer and seller never shook hands. Reset and try a different scenario.`}
        </div>
      </div>

      <div className="kpi-grid">
        <Kpi label="Outcome" value={label.split(" ")[0]} accent={bannerClass} />
        <Kpi label="Rounds used" value={roundLabel} />
        <Kpi
          label="Agreed price"
          value={money(agreed_price)}
          sub={outcome === "agreement" ? `round ${summary.agreed_at_round ?? "?"}` : "no deal"}
        />
        <Kpi
          label="Convergence gap"
          value={outcome === "agreement" ? "$0" : money(summary.convergence_gap)}
          sub={outcome === "agreement" ? "fully converged" : "final offer distance"}
        />
        <Kpi label="Time" value={ms(summary.duration_ms)} />
        <Kpi
          label="Acceptance checks"
          value={String(summary.acceptance_checks)}
          sub={`${summary.near_misses} near-miss`}
        />
      </div>

      <div className="metrics-panel">
        <div className="metrics-panel-title">Price trajectory by round</div>
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 12, right: 16, bottom: 4, left: 8 }}>
              <CartesianGrid stroke="#2d333b" strokeDasharray="3 3" />
              <XAxis dataKey="round" stroke="#8b949e" tick={{ fill: "#8b949e", fontSize: 12 }} />
              <YAxis domain={yDomain} tickFormatter={moneyK} stroke="#8b949e" tick={{ fill: "#8b949e", fontSize: 12 }} width={56} />
              <Tooltip
                contentStyle={{
                  background: "#1c2330",
                  border: "1px solid #2d333b",
                  borderRadius: 8,
                  color: "#e6edf3",
                  fontSize: 12,
                }}
                labelFormatter={(r) => `Round ${r}`}
                formatter={(value, name) => [money(value as number | null), String(name)]}
              />
              <Legend wrapperStyle={{ color: "#8b949e", fontSize: 12 }} />
              {hasZopa && (
                <ReferenceArea
                  y1={zopaLow}
                  y2={zopaHigh}
                  fill={ZOPA_COLOR}
                  fillOpacity={0.1}
                  stroke={ZOPA_COLOR}
                  strokeOpacity={0.4}
                  strokeDasharray="4 4"
                  label={{ value: "ZOPA", position: "right", fill: ZOPA_COLOR, fontSize: 11 }}
                />
              )}
              <ReferenceLine
                y={zone.buyer_max}
                stroke={BUYER_COLOR}
                strokeDasharray="4 4"
                strokeOpacity={0.5}
                label={{ value: "buyer reserv.", position: "insideTopLeft", fill: BUYER_COLOR, fontSize: 10 }}
              />
              <ReferenceLine
                y={zone.seller_min}
                stroke={SELLER_COLOR}
                strokeDasharray="4 4"
                strokeOpacity={0.5}
                label={{ value: "seller reserv.", position: "insideBottomLeft", fill: SELLER_COLOR, fontSize: 10 }}
              />
              <Line type="monotone" dataKey="buyer" name="Buyer offer" stroke={BUYER_COLOR} strokeWidth={2.5} dot={{ r: 4, fill: BUYER_COLOR }} activeDot={{ r: 6 }} connectNulls />
              <Line type="monotone" dataKey="seller" name="Seller offer" stroke={SELLER_COLOR} strokeWidth={2.5} dot={{ r: 4, fill: SELLER_COLOR }} activeDot={{ r: 6 }} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-legend-hint">
          Shaded band = Zone of Possible Agreement (overlap of price mandates); dashed lines = each side&rsquo;s reservation price.
        </div>
      </div>

      <div className="side-grid">
        <SidePanel role="buyer" title="Buyer" color="var(--accent)" s={summary.buyer} tools={summary.tool_breakdown?.buyer ?? {}} />
        <SidePanel role="seller" title="Seller" color="var(--amber)" s={summary.seller} tools={summary.tool_breakdown?.seller ?? {}} />
      </div>
    </div>
  );
}

function Kpi({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div className={`kpi ${accent ?? ""}`}>
      <div className="kpi-label">{label}</div>
      <div className="kpi-value">{value}</div>
      {sub ? <div className="kpi-sub">{sub}</div> : null}
    </div>
  );
}

function SidePanel({
  title,
  color,
  s,
  tools,
  role,
}: {
  title: string;
  role: string;
  color: string;
  s: SessionSummary["buyer"];
  tools: Record<string, number>;
}) {
  const toolRows = Object.entries(tools);
  return (
    <div className="side-panel" style={{ borderTopColor: color }}>
      <div className="side-panel-title" style={{ color }}>
        {title}
      </div>
      <div className="side-rows">
        <SideRow label="Opened at" value={money(s.opening_price)} />
        <SideRow label={role === "buyer" ? "Moved toward seller" : "Moved toward buyer"} value={money(s.total_concession)} sub="total concession" />
        <SideRow label="Largest step" value={money(s.max_step)} />
        <SideRow label="Avg step" value={money(s.avg_step)} sub="per concession" />
      </div>
      {toolRows.length > 0 && (
        <div className="side-tools">
          <div className="side-tools-label">Tool calls: {Object.values(tools).reduce((a, b) => a + b, 0)}</div>
          {toolRows.map(([name, count]) => (
            <div className="side-tool" key={name}>
              <span className="side-tool-name">{name}</span>
              <span className="side-tool-count">{count}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SideRow({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="side-row">
      <span className="side-row-label">{label}</span>
      <span className="side-row-value">
        {value}
        {sub ? <span className="side-row-sub"> {sub}</span> : null}
      </span>
    </div>
  );
}
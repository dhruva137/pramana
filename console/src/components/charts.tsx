/** Lightweight SVG charts — no chart library. Ink/teal + danger for baseline. */

export type VolumePoint = { day: string; count: number };
export type MixSlice = { key: string; label: string; count: number };
export type MoneySlice = { key: string; label: string; paise: number };

const TEAL = "#0c5c63";
const TEAL_BRIGHT = "#1a8a94";
const DANGER = "#8b2e1f";
const INK_MUTED = "#5a6f74";
const OK = "#1f6b3a";
const WARN = "#9a6b12";

export function AreaSpark({
  points,
  height = 72,
  label = "Episodes · 14d",
}: {
  points: VolumePoint[];
  height?: number;
  label?: string;
}) {
  const w = 320;
  const h = height;
  const pad = 4;
  const counts = points.map((p) => p.count);
  const max = Math.max(1, ...counts);
  const n = Math.max(1, points.length - 1);
  const coords = points.map((p, i) => {
    const x = pad + (i / n) * (w - pad * 2);
    const y = h - pad - (p.count / max) * (h - pad * 2);
    return { x, y, ...p };
  });
  const line = coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");
  const area =
    coords.length > 0
      ? `${line} L${coords[coords.length - 1].x.toFixed(1)},${h - pad} L${coords[0].x.toFixed(1)},${h - pad} Z`
      : "";
  const total = counts.reduce((a, b) => a + b, 0);

  return (
    <div className="chart-block">
      <div className="chart-hd">
        <span>{label}</span>
        <span className="mono">{total}</span>
      </div>
      <svg viewBox={`0 0 ${w} ${h}`} className="chart-svg" role="img" aria-label={label}>
        <defs>
          <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={TEAL_BRIGHT} stopOpacity="0.35" />
            <stop offset="100%" stopColor={TEAL_BRIGHT} stopOpacity="0" />
          </linearGradient>
        </defs>
        {area && <path d={area} fill="url(#sparkFill)" />}
        {line && <path d={line} fill="none" stroke={TEAL} strokeWidth="2" />}
      </svg>
      <div className="chart-ft hint">
        {points[0]?.day?.slice(5) ?? "—"} → {points[points.length - 1]?.day?.slice(5) ?? "—"}
      </div>
    </div>
  );
}

export function VerdictDonut({
  slices,
  size = 132,
}: {
  slices: MixSlice[];
  size?: number;
}) {
  const total = slices.reduce((a, s) => a + s.count, 0) || 1;
  const colors: Record<string, string> = {
    admit: OK,
    deny: DANGER,
    escalate: WARN,
  };
  const r = 48;
  const c = 2 * Math.PI * r;
  let offset = 0;
  const arcs = slices.map((s) => {
    const frac = s.count / total;
    const len = frac * c;
    const arc = {
      ...s,
      dash: `${len} ${c - len}`,
      offset: -offset,
      color: colors[s.key] ?? TEAL,
    };
    offset += len;
    return arc;
  });

  return (
    <div className="chart-block">
      <div className="chart-hd">
        <span>Verdict mix</span>
        <span className="mono">{slices.reduce((a, s) => a + s.count, 0)}</span>
      </div>
      <div className="donut-row">
        <svg width={size} height={size} viewBox="0 0 120 120" className="chart-svg donut">
          <g transform="translate(60,60) rotate(-90)">
            <circle r={r} fill="none" stroke="rgba(10,28,33,0.08)" strokeWidth="14" />
            {arcs.map((a) =>
              a.count > 0 ? (
                <circle
                  key={a.key}
                  r={r}
                  fill="none"
                  stroke={a.color}
                  strokeWidth="14"
                  strokeDasharray={a.dash}
                  strokeDashoffset={a.offset}
                  strokeLinecap="butt"
                />
              ) : null,
            )}
          </g>
          <text x="60" y="56" textAnchor="middle" className="donut-center">
            {((slices.find((s) => s.key === "deny")?.count ?? 0) / total * 100).toFixed(0)}%
          </text>
          <text x="60" y="72" textAnchor="middle" className="donut-sub">
            deny
          </text>
        </svg>
        <ul className="chart-legend">
          {slices.map((s) => (
            <li key={s.key}>
              <span className={`swatch ${s.key}`} />
              {s.label} <span className="mono">{s.count}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function MoneyBars({ slices }: { slices: MoneySlice[] }) {
  const max = Math.max(1, ...slices.map((s) => s.paise));
  const colors: Record<string, string> = {
    protected: TEAL,
    captured: DANGER,
    held: WARN,
  };
  return (
    <div className="chart-block">
      <div className="chart-hd">
        <span>Money flow</span>
        <span className="hint">paise · int</span>
      </div>
      <div className="money-bars">
        {slices.map((s) => (
          <div key={s.key} className="money-row">
            <div className="money-label">{s.label}</div>
            <div className="money-track">
              <div
                className="money-fill"
                style={{
                  width: `${(s.paise / max) * 100}%`,
                  background: colors[s.key] ?? TEAL,
                }}
              />
            </div>
            <div className="mono money-val">₹{(s.paise / 100).toLocaleString("en-IN")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function AsrCompareHero({
  baseline,
  pramana,
  baselineDisplay,
  pramanaDisplay,
}: {
  baseline?: number | null;
  pramana?: number | null;
  baselineDisplay?: string | null;
  pramanaDisplay?: string | null;
}) {
  const b = clamp01(baseline ?? 0);
  const p = clamp01(pramana ?? 0);
  return (
    <div className="chart-block asr-hero">
      <div className="chart-hd">
        <span>Overall attack success</span>
        <span className="hint">lower is safer</span>
      </div>
      <div className="asr-hero-tracks">
        <div className="asr-hero-arm">
          <span className="name danger-text">Baseline</span>
          <div className="asr-hero-bar">
            <div className="fill baseline" style={{ width: `${b * 100}%` }} />
          </div>
          <span className="mono">{baselineDisplay ?? pct(baseline)}</span>
        </div>
        <div className="asr-hero-arm">
          <span className="name teal-text">Pramana</span>
          <div className="asr-hero-bar">
            <div className="fill pramana" style={{ width: `${p * 100}%` }} />
          </div>
          <span className="mono">{pramanaDisplay ?? pct(pramana)}</span>
        </div>
      </div>
    </div>
  );
}

export function LatencyMeter({ p95Ms }: { p95Ms?: number | null }) {
  const v = typeof p95Ms === "number" ? p95Ms : null;
  const max = 50;
  const pctW = v == null ? 0 : Math.min(100, (v / max) * 100);
  return (
    <div className="chart-block">
      <div className="chart-hd">
        <span>Gate latency p95</span>
        <span className="mono">{v == null ? "—" : `${v.toFixed(1)} ms`}</span>
      </div>
      <div className="latency-track">
        <div className="latency-fill" style={{ width: `${pctW}%` }} />
        <span className="latency-mark" style={{ left: "20%" }} title="10ms" />
      </div>
      <div className="chart-ft hint">Target: low tens of ms · scale to {max}ms</div>
    </div>
  );
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  if (n > 1) return Math.min(1, n / 100);
  return Math.max(0, Math.min(1, n));
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const v = n > 1 ? n : n * 100;
  return `${v.toFixed(1)}%`;
}

// silence unused ink muted if tree-shaken — keep for future ticks
void INK_MUTED;

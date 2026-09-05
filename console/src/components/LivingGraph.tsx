import { useMemo, useState } from "react";
import { kindColor, type GraphModel, type GraphNode } from "../lib/graph";

type Props = {
  graph: GraphModel;
  selectedId?: string | null;
  highlightId?: string | null;
  onSelect?: (node: GraphNode | null) => void;
  height?: number;
};

const W = 1000;
const H = 520;

const KIND_TAG: Record<string, string> = {
  user: "USER",
  seal: "SEAL",
  envelope: "ENV",
  context: "CTX",
  gate: "GATE",
  rule: "R6",
  ledger: "LED",
  money: "RZP",
  proof: "DVP",
  baseline: "BASE",
  decision: "TXN",
};

function pos(n: GraphNode, i: number): { x: number; y: number } {
  const x = (n.x ?? 0.12 + (i % 5) * 0.18) * W;
  const y = (n.y ?? 0.22 + Math.floor(i / 5) * 0.2) * H;
  return { x, y };
}

export function LivingGraph({
  graph,
  selectedId,
  highlightId,
  onSelect,
}: Props) {
  const [hint, setHint] = useState("Click a node — packets follow live authorizes");
  const laid = useMemo(
    () => graph.nodes.map((n, i) => ({ ...n, ...pos(n, i) })),
    [graph.nodes],
  );
  const byId = useMemo(() => new Map(laid.map((n) => [n.id, n])), [laid]);

  return (
    <div className="living-graph">
      <svg viewBox={`0 0 ${W} ${H}`} className="living-svg" role="img" aria-label="Architecture graph">
        <defs>
          <radialGradient id="gGlow" cx="50%" cy="40%" r="70%">
            <stop offset="0%" stopColor="#1a8a94" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#061014" stopOpacity="0.95" />
          </radialGradient>
          <filter id="soft">
            <feGaussianBlur stdDeviation="2.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect width={W} height={H} fill="url(#gGlow)" />
        {[
          { x: 8, w: 250, fill: "rgba(226,196,138,0.06)", label: "Trusted" },
          { x: 258, w: 260, fill: "rgba(154,168,173,0.08)", label: "Quarantine" },
          { x: 518, w: 250, fill: "rgba(62,200,212,0.07)", label: "Decision" },
          { x: 768, w: 224, fill: "rgba(224,177,74,0.07)", label: "Money / proof" },
        ].map((z) => (
          <g key={z.label}>
            <rect x={z.x} y={12} width={z.w} height={H - 28} fill={z.fill} rx="8" />
            <text x={z.x + 14} y={34} className="zone-label">
              {z.label}
            </text>
          </g>
        ))}
        <g className="graph-legend" transform="translate(24,488)">
          <circle r="5" fill="#6fbf86" />
          <text x="12" y="4">admit</text>
          <circle cx="78" r="5" fill="#ef8b78" />
          <text x="90" y="4">deny</text>
          <circle cx="150" r="5" fill="#3ec8d4" />
          <text x="162" y="4">live</text>
        </g>

        {graph.edges.map((e, i) => {
          const a = byId.get(e.source);
          const b = byId.get(e.target);
          if (!a || !b) return null;
          const mx = (a.x + b.x) / 2;
          const my = (a.y + b.y) / 2 - 24;
          const d = `M ${a.x} ${a.y} Q ${mx} ${my} ${b.x} ${b.y}`;
          const live = Boolean(e.active || a.state === "live" || b.state === "live" || a.state === "deny" || a.state === "admit");
          return (
            <g key={`${e.source}-${e.target}-${i}`}>
              <path d={d} className={`edge${live ? " live" : ""}`} />
              {e.label && (
                <text x={mx} y={my - 6} className="edge-lab">
                  {e.label}
                </text>
              )}
              {live && (
                <circle r="3.5" className="packet">
                  <animateMotion dur="2.4s" repeatCount="indefinite" path={d} />
                </circle>
              )}
            </g>
          );
        })}

        {laid.map((n) => {
          const selected = selectedId === n.id;
          const hot = highlightId === n.id;
          const r = n.kind === "gate" ? 28 : 22;
          return (
            <g
              key={n.id}
              className={`gnode st-${n.state ?? "idle"}${selected ? " sel" : ""}${hot ? " hot" : ""}`}
              transform={`translate(${n.x},${n.y})`}
              onClick={() => {
                onSelect?.(n);
                setHint(`${n.label} — ${n.detail || n.kind}`);
              }}
              role="button"
            >
              <circle r={r + 10} className="halo" />
              <circle r={r} fill={kindColor(n.kind)} filter="url(#soft)" />
              <text className="gkind" y="4">
                {KIND_TAG[n.kind] ?? n.kind.slice(0, 4).toUpperCase()}
              </text>
              <text className="glabel" y={r + 16}>
                {n.label.length > 18 ? `${n.label.slice(0, 16)}…` : n.label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="living-graph-hint">{hint}</div>
    </div>
  );
}

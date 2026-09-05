export type GraphNode = {
  id: string;
  label: string;
  kind: string;
  detail?: string;
  state?: string;
  x?: number;
  y?: number;
  meta?: Record<string, unknown>;
};

export type GraphEdge = {
  source: string;
  target: string;
  label?: string;
  active?: boolean;
};

export type GraphModel = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export const EMPTY_GRAPH: GraphModel = { nodes: [], edges: [] };

const KIND_COLOR: Record<string, string> = {
  user: "#e2c48a",
  seal: "#3ec8d4",
  envelope: "#7ad4c8",
  context: "#9aa8ad",
  gate: "#f2ebe0",
  rule: "#e07a62",
  ledger: "#6fbf86",
  money: "#e0b14a",
  proof: "#ef8b78",
  baseline: "#c96b5a",
  decision: "#8fd4de",
};

export const SKELETON_GRAPH: GraphModel = {
  nodes: [
    { id: "user", label: "User intent", kind: "user", detail: "Trusted channel", x: 0.1, y: 0.42, state: "idle" },
    { id: "seal", label: "Seal", kind: "seal", detail: "Ed25519 envelope", x: 0.26, y: 0.28, state: "idle" },
    { id: "envelope", label: "Envelope", kind: "envelope", detail: "Caps · payees", x: 0.42, y: 0.22, state: "idle" },
    { id: "context", label: "Context", kind: "context", detail: "Taint chain", x: 0.42, y: 0.62, state: "idle" },
    { id: "gate", label: "Gate R1–R12", kind: "gate", detail: "No LLM", x: 0.62, y: 0.42, state: "idle" },
    { id: "r6", label: "R6 ledger", kind: "rule", detail: "Episode ceiling", x: 0.62, y: 0.68, state: "idle" },
    { id: "ledger", label: "Spend", kind: "ledger", detail: "exposure vs seal", x: 0.78, y: 0.62, state: "idle" },
    { id: "exec", label: "Razorpay", kind: "money", detail: "HOLD then capture", x: 0.82, y: 0.28, state: "idle" },
    { id: "proof", label: "Proof", kind: "proof", detail: "DVP", x: 0.78, y: 0.82, state: "idle" },
    { id: "baseline", label: "Baseline", kind: "baseline", detail: "Per-txn only", x: 0.26, y: 0.78, state: "idle" },
  ],
  edges: [
    { source: "user", target: "seal", label: "utterance" },
    { source: "seal", target: "envelope", label: "sign" },
    { source: "user", target: "context", label: "USER" },
    { source: "envelope", target: "gate", label: "constraints" },
    { source: "context", target: "gate", label: "provenance" },
    { source: "gate", target: "r6", label: "sequence" },
    { source: "r6", target: "ledger", label: "exposure" },
    { source: "gate", target: "exec", label: "ADMIT" },
    { source: "gate", target: "proof", label: "DENY" },
    { source: "baseline", target: "exec", label: "blind" },
  ],
};

export function kindColor(kind: string): string {
  return KIND_COLOR[kind] ?? "#0c5c63";
}

export function statePulse(state?: string): number {
  if (state === "live" || state === "admit" || state === "deny") return 1;
  if (state === "warn") return 0.7;
  if (state === "done") return 0.35;
  return 0.12;
}

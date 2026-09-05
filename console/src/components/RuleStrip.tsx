import type { RuleTraceEntry } from "../lib/types";

const RULES = [
  "R1",
  "R2",
  "R3",
  "R4",
  "R5",
  "R6",
  "R7",
  "R8",
  "R9",
  "R10",
  "R11",
  "R12",
] as const;

function normalize(v: string | undefined): "pass" | "deny" | "escalate" | "idle" {
  if (!v) return "idle";
  const u = v.toUpperCase();
  if (u === "DENY" || u === "FAIL") return "deny";
  if (u === "ESCALATE") return "escalate";
  if (u === "ADMIT" || u === "PASS" || u === "OK") return "pass";
  if (u.includes("DENY") || u.includes("FAIL")) return "deny";
  return "pass";
}

type Props = {
  trace?: RuleTraceEntry[] | null;
};

export function RuleStrip({ trace }: Props) {
  const byId = new Map<string, RuleTraceEntry>();
  for (const t of trace ?? []) {
    if (t.rule_id) byId.set(t.rule_id.toUpperCase(), t);
  }

  return (
    <div className="rule-strip" aria-label="Rule verdict strip R1–R12">
      {RULES.map((id) => {
        const entry = byId.get(id);
        let verdict = entry?.verdict;
        if (!verdict && entry?.pass === true) verdict = "PASS";
        if (!verdict && entry?.pass === false) verdict = "DENY";
        const state = normalize(verdict);
        const label =
          state === "idle"
            ? "—"
            : state === "pass"
              ? "ok"
              : state === "escalate"
                ? "esc"
                : "deny";
        return (
          <div
            key={id}
            className={`rule-cell ${state === "idle" ? "" : state}`}
            title={
              entry
                ? `${id} ${entry.name ?? ""} · ${entry.verdict}${
                    entry.expected ? `\nexpected: ${entry.expected}` : ""
                  }${entry.actual ? `\nactual: ${entry.actual}` : ""}`
                : id
            }
          >
            <span className="rid">{id}</span>
            <span className="rv">{label}</span>
          </div>
        );
      })}
    </div>
  );
}

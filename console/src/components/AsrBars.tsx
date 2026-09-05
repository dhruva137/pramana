import { formatPct } from "../lib/format";
import type { FamilyAsr } from "../lib/types";

type Props = {
  rows: FamilyAsr[];
};

export function AsrBars({ rows }: Props) {
  if (!rows.length) {
    return <div className="empty">No ASR data yet. Run a benchmark arm.</div>;
  }

  return (
    <div className="bars">
      {rows.map((row) => {
        const fam = row.family.toUpperCase();
        const isF3 = fam === "F3" || fam.includes("FRAGMENT");
        const b = clamp01(row.baseline_asr);
        const p = clamp01(row.pramana_asr);
        return (
          <div
            key={row.family}
            className={`bar-row${isF3 ? " highlight" : ""}`}
          >
            <div className="bar-label">{row.label ?? row.family}</div>
            <div className="bar-tracks">
              <div className="bar-track baseline">
                <span className="name">baseline</span>
                <div className="track">
                  <div className="fill" style={{ width: `${b * 100}%` }} />
                </div>
                <span className="val">
                  {row.baseline_display ?? formatPct(row.baseline_asr)}
                </span>
              </div>
              <div className="bar-track pramana">
                <span className="name">pramana</span>
                <div className="track">
                  <div className="fill" style={{ width: `${p * 100}%` }} />
                </div>
                <span className="val">
                  {row.pramana_display ?? formatPct(row.pramana_asr)}
                </span>
              </div>
              {row.note && <p className="annotate">{row.note}</p>}
              {!row.note && isF3 && (
                <p className="annotate">
                  F3 — per-transaction validation cannot see this
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  if (n > 1) return Math.min(1, n / 100);
  return Math.max(0, Math.min(1, n));
}

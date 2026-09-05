/** Integer paise → display rupees. Never float-math the ledger. */
export function formatPaise(paise: number | null | undefined): string {
  if (paise == null || Number.isNaN(paise)) return "—";
  const sign = paise < 0 ? "-" : "";
  const abs = Math.abs(Math.trunc(paise));
  const rupees = Math.floor(abs / 100);
  const rem = abs % 100;
  return `${sign}₹${rupees.toLocaleString("en-IN")}.${String(rem).padStart(2, "0")}`;
}

export function formatPct(rate: number | null | undefined): string {
  if (rate == null || Number.isNaN(rate)) return "—";
  const pct = rate <= 1 ? rate * 100 : rate;
  return `${pct.toFixed(1)}%`;
}

/** The gate is a pure function and runs well under a millisecond — rounding to
 *  whole ms collapsed p50/p95/p99 to an identical "1 ms" and hid the point. */
export function formatMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 10) return `${ms.toFixed(2)} ms`;
  if (ms < 100) return `${ms.toFixed(1)} ms`;
  return `${Math.round(ms)} ms`;
}

export function shortId(id: string | null | undefined, n = 10): string {
  if (!id) return "—";
  return id.length <= n ? id : `${id.slice(0, n)}…`;
}

export function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n - 1)}…`;
}

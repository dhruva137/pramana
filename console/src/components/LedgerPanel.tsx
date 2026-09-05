import { formatPaise } from "../lib/format";
import type { LedgerState } from "../lib/types";

type Props = {
  ledger?: LedgerState | null;
  /** Episode status from the API — the ledger payload does not carry it. */
  status?: string | null;
  capFallback?: number | null;
  maxTxnFallback?: number | null;
};

export function LedgerPanel({
  ledger,
  status,
  capFallback,
  maxTxnFallback,
}: Props) {
  if (!ledger) {
    return <div className="empty">Ledger idle.</div>;
  }

  // The API reports exposure (committed + held) — that is what R6 tests, so it is
  // what the bar must show. A stuck/AMBIGUOUS payment keeps its hold and therefore
  // keeps consuming the cap; showing only committed spend would overstate headroom.
  const spent = ledger.exposure_paise ?? ledger.spent_paise ?? 0;
  const cap =
    ledger.cap_paise ?? ledger.episode_total_max_paise ?? capFallback ?? 0;
  const txn = ledger.txn_count ?? 0;
  const maxTxn = ledger.max_transactions ?? maxTxnFallback ?? 0;
  // distinct_payees arrives as a list of merchant ids, not a count.
  const payeesRaw = ledger.distinct_payees;
  const payees = Array.isArray(payeesRaw) ? payeesRaw.length : (payeesRaw ?? 0);
  const held = (ledger.held_paise as number | undefined) ?? 0;
  const pct = cap > 0 ? Math.min(100, Math.round((spent / cap) * 100)) : 0;
  const atCap = cap > 0 && spent >= cap;

  return (
    <div>
      <dl className="kv">
        <dt>Exposure / cap</dt>
        <dd className={atCap ? "emphatic danger" : "emphatic"}>
          {formatPaise(spent)} / {formatPaise(cap)}
        </dd>
        {held > 0 && (
          <>
            <dt>of which held</dt>
            <dd className="mono">{formatPaise(held)}</dd>
          </>
        )}
        <dt>Transactions</dt>
        <dd className={maxTxn > 0 && txn >= maxTxn ? "emphatic danger" : undefined}>
          {txn} of {maxTxn || "—"}
        </dd>
        <dt>Distinct payees</dt>
        <dd>{payees}</dd>
        <dt>Status</dt>
        <dd className={status === "FROZEN" || status === "QUARANTINED" ? "emphatic danger" : undefined}>
          {status ?? ledger.status ?? "OPEN"}
        </dd>
      </dl>
      <div
        className={`ledger-bar${atCap ? " at-cap" : ""}`}
        role="img"
        aria-label={`Episode exposure ${pct}% of cap`}
      >
        <span style={{ width: `${pct}%` }} />
      </div>
      <p className="hint mono">
        {pct}% of episode cap · exposure = committed + held · integer paise
      </p>
    </div>
  );
}

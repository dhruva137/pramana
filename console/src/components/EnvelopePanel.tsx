import { formatPaise } from "../lib/format";
import type { Envelope } from "../lib/types";

type Props = {
  envelope?: Envelope | null;
};

/**
 * A Sealed Intent Envelope nests its limits under `constraints` (see
 * docs/05-PROTOCOL-SPEC.md §2.1). Reading them off the top level rendered every
 * value as an em-dash even on a perfectly sealed episode — the panel that is
 * supposed to prove the intent was captured showed nothing at all.
 * Flat lookups are kept as a fallback for hand-rolled fixtures.
 */
export function EnvelopePanel({ envelope }: Props) {
  if (!envelope) {
    return <div className="empty">No sealed envelope yet.</div>;
  }

  const c = (envelope.constraints ?? {}) as Record<string, unknown>;
  const pick = <T,>(key: string): T | undefined =>
    (c[key] ?? envelope[key]) as T | undefined;

  const merchants = pick<string[]>("merchants_allow") ?? [];
  const total = pick<number>("episode_total_max_paise");
  const perTxn = pick<number>("per_txn_max_paise");
  const maxTxn = pick<number>("max_transactions");
  const confirm = pick<number>("confirm_above_paise");
  const instruments = pick<string[]>("allowed_instruments");
  const instrument =
    instruments?.[0] ?? (pick<string>("instrument") as string | undefined);
  const addressHash = pick<string>("delivery_address_hash");

  return (
    <div>
      <dl className="kv">
        <dt>Episode total max</dt>
        <dd className="emphatic">{formatPaise(total)}</dd>
        <dt>Per-txn max</dt>
        <dd>{formatPaise(perTxn)}</dd>
        <dt>Max transactions</dt>
        <dd className="emphatic">{maxTxn ?? "—"}</dd>
        <dt>Confirm above</dt>
        <dd>{formatPaise(confirm)}</dd>
        <dt>Instrument</dt>
        <dd className="mono">{instrument ?? "—"}</dd>
        <dt>Address hash</dt>
        <dd className="mono" title={addressHash}>
          {addressHash ? `${addressHash.slice(0, 22)}…` : "—"}
        </dd>
        <dt>Expires</dt>
        <dd className="mono">{String(envelope.expires_at ?? "—")}</dd>
      </dl>
      {merchants.length > 0 && (
        <div className="tag-list">
          {merchants.map((m) => (
            <span className="tag" key={m}>
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ApiError, getProof, listProofs, narrateProof, verifyProof } from "../lib/api";
import { formatPaise, shortId } from "../lib/format";
import type { CausalStep, DivergenceProof } from "../lib/types";
import { EnvelopePanel } from "../components/EnvelopePanel";
import { RuleStrip } from "../components/RuleStrip";

function highlightExcerpt(step: CausalStep): ReactNode {
  const text = step.full_text ?? step.excerpt ?? "";
  const span = step.span;
  if (!text) return <span className="hint">No excerpt.</span>;
  if (!span || span.length < 2) {
    const injected = Boolean(step.injected || step.detector?.flagged);
    return (
      <span className="excerpt">
        {injected ? <mark>{text}</mark> : text}
      </span>
    );
  }
  const [a, b] = span;
  const start = Math.max(0, Math.min(a, text.length));
  const end = Math.max(start, Math.min(b, text.length));
  return (
    <span className="excerpt">
      {text.slice(0, start)}
      <mark>{text.slice(start, end)}</mark>
      {text.slice(end)}
    </span>
  );
}

type ProofRow = {
  proof_id: string;
  episode_id?: string;
  created_at?: string;
  verdict?: string;
  rule_id?: string | null;
};

export function ProofViewer() {
  const [params, setParams] = useSearchParams();
  const [recent, setRecent] = useState<ProofRow[]>([]);
  const [proof, setProof] = useState<DivergenceProof | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifyMsg, setVerifyMsg] = useState<string | null>(null);
  const [narrate, setNarrate] = useState<string | null>(null);

  async function load(id: string, replace = true) {
    const trimmed = id.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    setVerifyMsg(null);
    setNarrate(null);
    try {
      const p = await getProof(trimmed);
      setProof(p);
      if (replace && params.get("id") !== trimmed) {
        setParams({ id: trimmed });
      }
      const res = await verifyProof(p);
      const accepted = res.accepted === true || res.accept === true;
      setVerifyMsg(accepted ? "Verifier ACCEPT" : `Verifier REJECT · ${res.check ?? ""}`);
    } catch (e) {
      setProof(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await listProofs();
        if (!cancelled) setRecent(rows);
        const qid = params.get("id");
        if (qid) {
          await load(qid, false);
        } else if (rows[0]?.proof_id) {
          await load(rows[0].proof_id);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof ApiError ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
    // initial mount only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const id = params.get("id");
    if (id && id !== proof?.dvp_id) void load(id, false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  const envelope = proof?.sealed_intent?.envelope;
  const executed = proof?.executed_action;
  const predicates = proof?.violated_predicates ?? [];
  const chain = proof?.causal_chain ?? [];
  const payeeSealed = useMemo(() => {
    const m = envelope?.merchants_allow ?? envelope?.constraints?.merchants_allow;
    return Array.isArray(m) ? m.join(", ") : "—";
  }, [envelope]);

  return (
    <div className="stack">
      <div className="section-title">
        <div>
          <h1>Divergence proofs</h1>
          <p>
            A proof is emitted when the gate denies. You do not paste IDs — pick a
            recent deny, or arrive here from a live episode. Offline verify runs
            automatically.
          </p>
        </div>
        <Link className="btn ghost" to="/live">
          Run a deny (J3)
        </Link>
      </div>

      {error && <div className="error-banner">{error}</div>}

      <div className="proof-layout">
        <aside className="panel">
          <div className="panel-hd">
            <h2>Recent</h2>
            <span className="meta">{recent.length}</span>
          </div>
          <div className="panel-bd proof-list">
            {recent.length === 0 && (
              <div className="empty tight">
                No proofs yet. Run J2 or J3 on the command graph.
              </div>
            )}
            {recent.map((r) => (
              <button
                key={r.proof_id}
                type="button"
                className={`proof-row${
                  params.get("id") === r.proof_id ? " on" : ""
                }`}
                onClick={() => void load(r.proof_id)}
              >
                <span className={`pill ${(r.verdict ?? "deny").toLowerCase()}`}>
                  {r.verdict ?? "DENY"}
                </span>
                <span className="mono">{shortId(r.proof_id, 14)}</span>
                <span className="hint">
                  {r.rule_id ?? "—"} · {r.created_at?.slice(0, 19) ?? ""}
                </span>
              </button>
            ))}
          </div>
        </aside>

        <div className="stack">
          {!proof && !busy && (
            <div className="empty">Select a proof from the left.</div>
          )}
          {proof && (
            <>
              <div className="panel">
                <div className="panel-hd">
                  <h2>
                    {shortId(proof.dvp_id, 16)} · {proof.verdict ?? "—"}
                  </h2>
                  <span className="meta">{verifyMsg ?? (busy ? "…" : "")}</span>
                </div>
                <div className="panel-bd">
                  <p className="hint">
                    Why this page exists: when an agent drifts, Pramana mints a
                    portable document a third party can verify without trusting us.
                  </p>
                  <div className="btn-row">
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={async () => {
                        if (!proof.dvp_id) return;
                        try {
                          const n = await narrateProof(proof.dvp_id);
                          setNarrate(n.narrative ?? JSON.stringify(n));
                        } catch (e) {
                          setNarrate(e instanceof ApiError ? e.message : String(e));
                        }
                      }}
                    >
                      Explain (post-hoc AI)
                    </button>
                  </div>
                  {narrate && <pre className="narrate-block">{narrate}</pre>}
                  <div className="compare">
                    <div className="compare-card sealed">
                      <h4>Sealed intent</h4>
                      <EnvelopePanel envelope={envelope} />
                      <p className="hint">Merchants allow: {payeeSealed}</p>
                    </div>
                    <div className="compare-card executed">
                      <h4>Proposed action</h4>
                      <dl className="kv">
                        <dt>Amount</dt>
                        <dd>{formatPaise(executed?.amount_paise)}</dd>
                        <dt>Payee</dt>
                        <dd>{executed?.payee?.merchant_id ?? "—"}</dd>
                      </dl>
                    </div>
                  </div>
                </div>
              </div>
              <div className="panel">
                <div className="panel-hd">
                  <h2>Why it failed</h2>
                </div>
                <div className="panel-bd">
                  {predicates.length === 0 && (
                    <div className="empty">No violated predicates.</div>
                  )}
                  {predicates.map((p, i) => (
                    <div className="predicate" key={`${p.rule_id}-${i}`}>
                      <strong>{p.rule_id}</strong>
                      <div className="arrow">
                        expected: {p.expected ?? "—"}
                        <br />
                        actual: {p.actual ?? "—"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="panel">
                <div className="panel-hd">
                  <h2>Causal chain</h2>
                </div>
                <div className="panel-bd causal">
                  {chain.map((step, i) => (
                    <div
                      key={i}
                      className={`causal-step${
                        step.injected || step.detector?.flagged ? " injected" : ""
                      }`}
                    >
                      {highlightExcerpt(step)}
                    </div>
                  ))}
                </div>
              </div>
              <div className="panel">
                <div className="panel-hd">
                  <h2>Rule trace</h2>
                </div>
                <div className="panel-bd">
                  <RuleStrip trace={proof.rule_trace} />
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

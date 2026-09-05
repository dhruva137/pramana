import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getProof, listEpisodes, verifyProof } from "../lib/api";
import { formatPaise, shortId } from "../lib/format";
import type { EpisodeSummary } from "../lib/types";

export function History() {
  const [rows, setRows] = useState<EpisodeSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifyNote, setVerifyNote] = useState<Record<string, string>>({});

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setRows(await listEpisodes());
    } catch (e) {
      setRows([]);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function verifyRow(row: EpisodeSummary) {
    if (!row.proof_id) return;
    setVerifyNote((m) => ({ ...m, [row.episode_id]: "…" }));
    try {
      const proof = await getProof(row.proof_id);
      const res = await verifyProof(proof);
      const accepted = res.accepted === true || res.accept === true;
      setVerifyNote((m) => ({
        ...m,
        [row.episode_id]: accepted ? "ACCEPT" : `REJECT ${res.check ?? ""}`,
      }));
    } catch (e) {
      setVerifyNote((m) => ({
        ...m,
        [row.episode_id]: e instanceof ApiError ? e.message : String(e),
      }));
    }
  }

  return (
    <div className="stack">
      <div className="section-title">
        <div>
          <h1>Episodes</h1>
          <p>
            Every sealed conversation. Open Live to replay the graph, or a proof
            when the gate denied.
          </p>
        </div>
        <button type="button" className="btn ghost" disabled={busy} onClick={() => void load()}>
          {busy ? "…" : "Refresh"}
        </button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      {rows.length === 0 && !error ? (
        <div className="empty">
          Nothing yet. <Link to="/live">Seal an intent on the command graph</Link>.
        </div>
      ) : (
        <div className="episode-cards">
          {rows.map((r) => (
            <article key={r.episode_id} className="episode-card">
              <header>
                <span className={`pill ${(r.verdict ?? r.status ?? "open").toLowerCase()}`}>
                  {r.verdict ?? r.status ?? "OPEN"}
                </span>
                <span className="tag">{String(r.arm ?? "pramana")}</span>
              </header>
              <p className="episode-utterance">
                {r.utterance || "Sealed episode"}
              </p>
              <dl className="kv compact">
                <dt>Spend</dt>
                <dd className="mono">
                  {formatPaise(r.spent_paise)}
                  {r.cap_paise ? ` / ${formatPaise(r.cap_paise)}` : ""}
                </dd>
                <dt>Id</dt>
                <dd className="mono">{shortId(r.episode_id, 16)}</dd>
              </dl>
              <div className="btn-row">
                <Link
                  className="btn ghost sm"
                  to={`/live?episode=${encodeURIComponent(r.episode_id)}`}
                >
                  Open in graph
                </Link>
                {r.proof_id ? (
                  <>
                    <Link
                      className="btn ghost sm"
                      to={`/proof?id=${encodeURIComponent(r.proof_id)}`}
                    >
                      Proof
                    </Link>
                    <button
                      type="button"
                      className="btn ghost sm"
                      onClick={() => void verifyRow(r)}
                    >
                      Verify
                    </button>
                  </>
                ) : null}
              </div>
              {verifyNote[r.episode_id] && (
                <p className="hint">{verifyNote[r.episode_id]}</p>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

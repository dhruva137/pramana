import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, getBenchSummary } from "../lib/api";
import { formatMs, formatPaise, formatPct } from "../lib/format";
import type { BenchSummary } from "../lib/types";
import { AsrBars } from "../components/AsrBars";
import { AsrCompareHero, LatencyMeter } from "../components/charts";

export function Benchmark() {
  const [data, setData] = useState<BenchSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const summary = await getBenchSummary();
      setData(summary);
    } catch (e) {
      setData(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const utility = data?.utility;
  const latency = data?.latency;
  const families = data?.asr_by_family ?? [];

  return (
    <div className="stack">
      <div className="section-title">
        <div>
          <h1>Benchmark dashboard</h1>
          <p>
            Attack success rate by family (baseline vs Pramana), utility cost,
            and gate latency — F3 called out because per-txn checks are blind to
            it.
          </p>
        </div>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() => void load()}
        >
          {busy ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {/* Never let a viewer mistake placeholder data for a measured run. */}
      {data?.source === "mock" && (
        <div className="warn-banner">
          <strong>Placeholder data.</strong> No runner report was found in{" "}
          <code>reports/</code>. Run{" "}
          <code>python -m bench.runner --arm baseline</code> and{" "}
          <code>--arm pramana</code> to populate real numbers.
        </div>
      )}

      {data && data.source !== "mock" && (
        <div className="panel" style={{ marginBottom: "0.75rem" }}>
          <div className="panel-bd hint">
            Provenance:{" "}
            <code>{String(data.source ?? "?")}</code>
            {data.shopper_mode != null && (
              <>
                {" "}
                · shopper <code>{String(data.shopper_mode)}</code>
              </>
            )}
            {data.run_kind != null && (
              <>
                {" "}
                · <code>{String(data.run_kind)}</code>
              </>
            )}
            {data.corpus_hash != null && (
              <>
                {" "}
                · corpus <code>{String(data.corpus_hash).slice(0, 12)}…</code>
              </>
            )}
            {" "}
            — protocol/ledger eval, not live-LLM agent robustness. Residual ASR
            is F8 (confidentiality), out of integrity scope.
          </div>
        </div>
      )}

      {data && data.source !== "mock" && (
        <div className="chart-grid" style={{ marginBottom: "0.85rem" }}>
          <AsrCompareHero
            baseline={data.asr_overall?.baseline}
            pramana={data.asr_overall?.pramana}
            baselineDisplay={
              typeof data.asr_overall?.baseline_display === "string"
                ? data.asr_overall.baseline_display
                : null
            }
            pramanaDisplay={
              typeof data.asr_overall?.pramana_display === "string"
                ? data.asr_overall.pramana_display
                : null
            }
          />
          <LatencyMeter p95Ms={latency?.p95_ms} />
          <div className="chart-block">
            <div className="chart-hd">
              <span>Utility snapshot</span>
            </div>
            <div className="stat-grid">
              <div className="stat">
                <div className="label">Benign</div>
                <div className="value">{formatPct(utility?.benign_completion)}</div>
              </div>
              <div className="stat">
                <div className="label">False deny</div>
                <div className="value">{formatPct(utility?.false_denial)}</div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-hd">
          <h2>ASR by family</h2>
          <span className="meta">
            {data?.corpus_version
              ? `${data.corpus_version} · n=${data.n_episodes ?? "?"} · ${
                  data.source === "reports" ? "measured" : String(data.source ?? "")
                }`
              : "GET /v1/bench/summary"}
          </span>
        </div>
        <div className="panel-bd">
          <AsrBars rows={families} />
          {data?.corpus_hash && (
            <p className="hint mono" style={{ marginTop: "0.75rem" }}>
              corpus sha256:{data.corpus_hash.slice(0, 16)}…
            </p>
          )}
        </div>
      </div>

      <div className="grid-2">
        <div className="panel">
          <div className="panel-hd">
            <h2>Utility</h2>
            <span className="meta">false-positive cost</span>
          </div>
          <div className="panel-bd">
            <div className="stat-grid">
              <div className="stat">
                <div className="label">Benign completion</div>
                <div className="value">
                  {formatPct(utility?.benign_completion)}
                </div>
              </div>
              <div className="stat">
                <div className="label">False escalation</div>
                <div className="value">
                  {formatPct(utility?.false_escalation)}
                </div>
              </div>
              <div className="stat">
                <div className="label">False denial</div>
                <div className="value">{formatPct(utility?.false_denial)}</div>
              </div>
              <div className="stat">
                <div className="label">Confirm taps</div>
                <div className="value">{utility?.taps ?? "—"}</div>
              </div>
              <div className="stat">
                <div className="label">₹ prevented</div>
                <div className="value" style={{ fontSize: "1.15rem" }}>
                  {utility?.rupees_prevented != null
                    ? formatPaise(Math.round(utility.rupees_prevented * 100))
                    : "—"}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-hd">
            <h2>Latency</h2>
            <span className="meta">gate decision</span>
          </div>
          <div className="panel-bd">
            <div className="stat-grid">
              <div className="stat">
                <div className="label">p50</div>
                <div className="value">{formatMs(latency?.p50_ms)}</div>
              </div>
              <div className="stat">
                <div className="label">p95</div>
                <div className="value">{formatMs(latency?.p95_ms)}</div>
              </div>
              <div className="stat">
                <div className="label">p99</div>
                <div className="value">{formatMs(latency?.p99_ms)}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {(data?.sample_proofs?.length ?? 0) > 0 && (
        <div className="panel">
          <div className="panel-hd">
            <h2>Drill-down</h2>
            <span className="meta">open a real episode proof</span>
          </div>
          <div className="panel-bd btn-row">
            {data!.sample_proofs!.map((s) => (
              <Link
                key={s.proof_id}
                className="btn ghost sm"
                to={`/proof?id=${encodeURIComponent(s.proof_id)}`}
              >
                {s.family} · {s.proof_id.slice(0, 12)}…
              </Link>
            ))}
          </div>
        </div>
      )}

      {(data?.known_weaknesses?.length ?? 0) > 0 && (
        <div className="panel">
          <div className="panel-hd">
            <h2>Known weaknesses</h2>
            <span className="meta">written, not generated</span>
          </div>
          <div className="panel-bd">
            <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
              {data!.known_weaknesses!.map((w, i) => (
                <li key={i} className="hint" style={{ marginBottom: "0.35rem" }}>
                  {w}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

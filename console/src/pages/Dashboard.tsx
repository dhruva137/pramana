import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AsrBars } from "../components/AsrBars";
import {
  AreaSpark,
  AsrCompareHero,
  LatencyMeter,
  MoneyBars,
  VerdictDonut,
} from "../components/charts";
import { ApiError, getDashboardSummary } from "../lib/api";
import { formatPaise, formatPct, shortId } from "../lib/format";
import type { DashboardSummary, FamilyAsr } from "../lib/types";

export function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const summary = await getDashboardSummary();
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

  const episodes = data?.episodes?.total ?? 0;
  const denials = data?.decisions?.deny ?? 0;
  const captures = data?.money?.captured_paise;
  const proofs = data?.proofs?.count ?? 0;
  const recent = data?.recent ?? [];
  const empty = !error && episodes === 0 && recent.length === 0;
  const bench = data?.bench;
  const charts = data?.charts;
  const volume = charts?.episode_volume ?? [];
  const verdictMix = charts?.verdict_mix ?? [];
  const moneySplit = charts?.money_split ?? [];
  const familyRows = (bench?.asr_by_family ?? []) as FamilyAsr[];
  const hasBench =
    bench &&
    (bench.overall_asr_baseline != null || bench.overall_asr_pramana != null);

  return (
    <div className="dash stack">
      <header className="dash-hero">
        <p className="eyebrow">Intent custody · control plane</p>
        <h1 className="dash-brand">Pramana</h1>
        <p className="lede">
          Overview of the sandbox: money the gate stopped, captures that were
          allowed, and the measured fragmentation win. The living graph lives
          on <Link to="/live">Command</Link> — that is where you run a journey.
        </p>
        <div className="btn-row dash-cta">
          <Link className="btn" to="/live">
            Open command graph
          </Link>
          <Link className="btn ghost" to="/live">
            Run J3 fragmentation
          </Link>
          <button
            type="button"
            className="btn ghost sm"
            disabled={busy}
            onClick={() => void load()}
          >
            {busy ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}

      {empty ? (
        <div className="dash-empty">
          <p>
            No episodes yet.{" "}
            <Link to="/live">Run J3 fragmentation on /live</Link>
          </p>
        </div>
      ) : (
        <>
          <section className="kpi-strip" aria-label="Key metrics">
            <div className="kpi">
              <span className="kpi-label">Episodes</span>
              <span className="kpi-value">{episodes}</span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Denials</span>
              <span className="kpi-value">{denials}</span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Captures</span>
              <span className="kpi-value mono">{formatPaise(captures)}</span>
            </div>
            <div className="kpi">
              <span className="kpi-label">Proofs</span>
              <span className="kpi-value">{proofs}</span>
            </div>
          </section>

          <section className="chart-grid" aria-label="Analytics">
            <AreaSpark points={volume} />
            <VerdictDonut slices={verdictMix} />
            <MoneyBars slices={moneySplit} />
            {hasBench ? (
              <AsrCompareHero
                baseline={bench?.overall_asr_baseline}
                pramana={bench?.overall_asr_pramana}
                baselineDisplay={bench?.baseline_display}
                pramanaDisplay={bench?.pramana_display}
              />
            ) : (
              <div className="chart-block">
                <div className="chart-hd">
                  <span>Bench ASR</span>
                </div>
                <p className="hint">
                  No measured report yet — open{" "}
                  <Link to="/bench">Benchmark</Link>.
                </p>
              </div>
            )}
            <LatencyMeter p95Ms={bench?.latency_p95_ms} />
            <div className="chart-block">
              <div className="chart-hd">
                <span>Protected vs captured</span>
                <span className="hint">thesis snapshot</span>
              </div>
              <p className="lede sm">
                Denied intended{" "}
                <strong className="mono">
                  {formatPaise(data?.money?.denied_intended_paise)}
                </strong>{" "}
                · captured{" "}
                <strong className="mono">{formatPaise(captures)}</strong>
              </p>
              <Link className="btn ghost sm" to="/live">
                Compare J3 arms
              </Link>
            </div>
          </section>

          {familyRows.length > 0 && (
            <section className="panel">
              <div className="panel-hd">
                <h2>ASR by family</h2>
                <span className="meta">
                  {bench?.shopper_mode ? `${bench.shopper_mode} · ` : ""}
                  {bench?.source ?? "reports"}
                </span>
              </div>
              <div className="panel-bd">
                <AsrBars rows={familyRows} />
                <div className="btn-row" style={{ marginTop: "0.75rem" }}>
                  <Link className="btn ghost sm" to="/bench">
                    Full bench + caveats
                  </Link>
                </div>
              </div>
            </section>
          )}

          {hasBench && familyRows.length === 0 && (
            <section className="dash-bench">
              <div className="section-label">
                <h2>Bench ASR</h2>
                <span>{bench?.source ?? "summary"}</span>
              </div>
              <div className="dash-bench-row">
                <div>
                  <span className="kpi-label">Baseline</span>
                  <span className="kpi-value">
                    {formatPct(bench?.overall_asr_baseline)}
                  </span>
                </div>
                <div className="dash-bench-vs" aria-hidden>
                  vs
                </div>
                <div>
                  <span className="kpi-label">Pramana</span>
                  <span className="kpi-value teal">
                    {formatPct(bench?.overall_asr_pramana)}
                  </span>
                </div>
                <Link className="btn ghost sm" to="/bench">
                  Full bench
                </Link>
              </div>
            </section>
          )}

          <section className="panel">
            <div className="panel-hd">
              <h2>Recent episodes</h2>
              <span className="meta">{recent.length} shown</span>
            </div>
            <div className="panel-bd table-wrap">
              {recent.length === 0 ? (
                <div className="empty">
                  <Link to="/live">Run J3 fragmentation on /live</Link>
                </div>
              ) : (
                <table className="data">
                  <thead>
                    <tr>
                      <th>Episode</th>
                      <th>Arm</th>
                      <th>Verdict</th>
                      <th>Spend</th>
                      <th>Open</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recent.map((r) => (
                      <tr key={r.episode_id}>
                        <td>
                          <div className="mono">
                            {shortId(r.episode_id, 14)}
                          </div>
                          <div className="hint">{r.created_at ?? ""}</div>
                        </td>
                        <td>
                          <span className="tag">{String(r.arm ?? "—")}</span>
                        </td>
                        <td>
                          <span
                            className={`pill ${(r.verdict ?? r.status ?? "open").toLowerCase()}`}
                          >
                            {r.verdict ?? r.status ?? "open"}
                          </span>
                        </td>
                        <td className="mono">{formatPaise(r.spent_paise)}</td>
                        <td>
                          <div className="btn-row">
                            <Link
                              className="btn ghost sm"
                              to={`/live?episode=${encodeURIComponent(r.episode_id)}`}
                            >
                              Live
                            </Link>
                            {r.proof_id ? (
                              <Link
                                className="btn ghost sm"
                                to={`/proof?id=${encodeURIComponent(r.proof_id)}`}
                              >
                                Proof
                              </Link>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}

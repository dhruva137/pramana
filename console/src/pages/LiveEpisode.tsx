import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { LivingGraph } from "../components/LivingGraph";
import { OperatorChat } from "../components/OperatorChat";
import { EnvelopePanel } from "../components/EnvelopePanel";
import { LedgerPanel } from "../components/LedgerPanel";
import { RuleStrip } from "../components/RuleStrip";
import {
  ApiError,
  checkoutEpisode,
  confirmEscalation,
  createEpisode,
  extractAuthorizeSteps,
  getEpisode,
  getGraphSnapshot,
  planGraphPrompt,
  runDemo,
  runDemoCompare,
} from "../lib/api";
import { formatPaise } from "../lib/format";
import { SKELETON_GRAPH, type GraphModel, type GraphNode } from "../lib/graph";
import type {
  Arm,
  ChatMessage,
  DemoRunResult,
  DemoScenario,
  Envelope,
  LedgerState,
  RuleTraceEntry,
} from "../lib/types";

const JOURNEYS: {
  id: DemoScenario;
  title: string;
  beat: string;
}[] = [
  { id: "J1", title: "Benign checkout", beat: "Seal → admit → capture" },
  { id: "J2", title: "Payee hijack", beat: "Baseline pays hostile; Pramana denies" },
  { id: "J3", title: "Fragmentation", beat: "Two legal ₹450; only R6 sees the sum" },
  { id: "J4", title: "Graceful fault", beat: "Timeout → hold, no double charge" },
];

const JOURNEY_FROM_API: Record<string, DemoScenario> = {
  benign: "J1",
  payee_hijack: "J2",
  fragmentation: "J3",
  fault: "J4",
};

type ArmSnapshot = {
  arm: Arm;
  episodeId: string | null;
  proofId: string | null;
  ruleId: string | null;
  messages: ChatMessage[];
  envelope: Envelope | null;
  ledger: LedgerState | null;
  trace: RuleTraceEntry[];
  verdict: string | null;
  status: string | null;
  narrative: string | null;
  raw: DemoRunResult | null;
};

function emptySnap(arm: Arm): ArmSnapshot {
  return {
    arm,
    episodeId: null,
    proofId: null,
    ruleId: null,
    messages: [],
    envelope: null,
    ledger: null,
    trace: [],
    verdict: null,
    status: null,
    narrative: null,
    raw: null,
  };
}

function genesisLedger(env: Envelope | null, status?: string | null): LedgerState {
  const cap =
    env?.constraints?.episode_total_max_paise ?? env?.episode_total_max_paise ?? 0;
  return {
    exposure_paise: 0,
    spent_paise: 0,
    committed_paise: 0,
    held_paise: 0,
    cap_paise: typeof cap === "number" ? cap : 0,
    txn_count: 0,
    max_transactions:
      env?.constraints?.max_transactions ?? env?.max_transactions ?? 0,
    distinct_payees: [],
    status: status ?? "OPEN",
  };
}

function friendlyError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 0) {
      return "Cannot reach the API. Start the server on port 8000.";
    }
    if (e.status === 422) {
      return "Request shape rejected (422). Refresh and try a journey button.";
    }
    return e.message;
  }
  return String(e);
}

function snapFromDemo(arm: Arm, res: DemoRunResult): ArmSnapshot {
  const v = res.verdict ?? res.proof?.verdict ?? null;
  const rid =
    (res as { rule_id?: string }).rule_id ??
    res.proof?.violated_predicates?.[0]?.rule_id ??
    null;
  const env =
    res.envelope ??
    (res.proof?.sealed_intent?.envelope as Envelope | undefined) ??
    null;
  return {
    arm,
    episodeId: res.episode_id ?? null,
    proofId: res.proof_id ?? res.proof?.dvp_id ?? null,
    ruleId: rid,
    messages: res.messages ?? [],
    envelope: env,
    ledger: res.ledger ?? res.proof?.episode_ledger_snapshot ?? genesisLedger(env, res.status),
    trace: res.rule_trace ?? res.proof?.rule_trace ?? [],
    verdict: v,
    status: res.status ?? null,
    narrative:
      typeof (res as { narrative?: string }).narrative === "string"
        ? (res as { narrative: string }).narrative
        : null,
    raw: res,
  };
}

function MoneyTimeline({ result }: { result: DemoRunResult | null }) {
  const steps = useMemo(() => extractAuthorizeSteps(result), [result]);
  if (!steps.length) {
    return (
      <div className="empty tight">
        No money movement yet. Run a journey, or seal then Propose checkout.
      </div>
    );
  }
  return (
    <ol className="money-timeline">
      {steps.map((s) => {
        const proofAmtRaw =
          s.raw.proof && typeof s.raw.proof === "object"
            ? (s.raw.proof as { executed_action?: { amount_paise?: number } })
                .executed_action?.amount_paise
            : undefined;
        const amount: number | undefined =
          typeof s.amount_paise === "number"
            ? s.amount_paise
            : typeof proofAmtRaw === "number"
              ? proofAmtRaw
              : undefined;
        const execState =
          typeof s.execution?.state === "string" ? s.execution.state : null;
        return (
          <li key={s.key} className={`money-step ${(s.verdict ?? "").toLowerCase()}`}>
            <div className="money-step-hd">
              <span className="money-idx">Authorize #{s.index}</span>
              <span className={`pill ${(s.verdict ?? "open").toLowerCase()}`}>
                {s.verdict ?? "—"}
              </span>
              {s.rule_id ? <span className="tag">{s.rule_id}</span> : null}
            </div>
            <div className="money-step-bd">
              {amount != null && (
                <span className="mono">{formatPaise(amount)}</span>
              )}
              {s.merchant_id && <span> → {s.merchant_id}</span>}
              {execState && <span className="hint"> · exec {execState}</span>}
              {s.proof_id && (
                <>
                  {" · "}
                  <Link to={`/proof?id=${encodeURIComponent(s.proof_id)}`}>
                    open proof
                  </Link>
                </>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function CapMeter({
  exposure,
  cap,
  arm,
}: {
  exposure: number;
  cap: number;
  arm: "baseline" | "pramana";
}) {
  const safeCap = Math.max(1, cap);
  const pct = Math.min(120, (exposure / safeCap) * 100);
  const over = exposure > safeCap;
  return (
    <div className={`cap-meter ${arm}${over ? " over" : ""}`}>
      <div className="cap-meter-hd">
        <span>Episode spend vs seal</span>
        <span className="mono">
          ₹{(exposure / 100).toLocaleString("en-IN")} / ₹
          {(safeCap / 100).toLocaleString("en-IN")}
        </span>
      </div>
      <div className="cap-track">
        <div className="cap-fill" style={{ width: `${Math.min(pct, 100)}%` }} />
        <div className="cap-seal" title="sealed ceiling" />
      </div>
    </div>
  );
}

function ComparePane({ title, snap }: { title: string; snap: ArmSnapshot }) {
  const cap =
    Number(
      snap.envelope?.constraints?.episode_total_max_paise ??
        snap.envelope?.episode_total_max_paise ??
        0,
    ) || 60000;
  const exposure = Number(snap.ledger?.exposure_paise ?? 0);
  return (
    <div className={`compare-pane ${snap.arm}`}>
      <div className="compare-pane-hd">
        <h3>{title}</h3>
        <span className={`pill ${(snap.verdict ?? "open").toLowerCase()}`}>
          {snap.verdict ?? "idle"}
        </span>
      </div>
      {snap.narrative && <p className="compare-narrative">{snap.narrative}</p>}
      <div className="panel-bd">
        <CapMeter exposure={exposure} cap={cap} arm={snap.arm} />
        <LedgerPanel
          ledger={snap.ledger}
          status={snap.status}
          capFallback={cap}
          maxTxnFallback={
            snap.envelope?.constraints?.max_transactions ??
            snap.envelope?.max_transactions
          }
        />
      </div>
      <div className="panel-bd">
        <RuleStrip trace={snap.trace} />
      </div>
      <MoneyTimeline result={snap.raw} />
      {snap.proofId && (
        <p className="hint episode-meta">
          <Link to={`/proof?id=${encodeURIComponent(snap.proofId)}`}>
            Open divergence proof
          </Link>
        </p>
      )}
    </div>
  );
}

export function LiveEpisode() {
  const [arm, setArm] = useState<Arm>("pramana");
  const [compareMode, setCompareMode] = useState(true);
  const [prompt, setPrompt] = useState(
    "Order dinner from Swiggy, keep it under ₹600.",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeJourney, setActiveJourney] = useState<DemoScenario | null>(null);
  const [confirmNote, setConfirmNote] = useState<string | null>(null);
  const [primary, setPrimary] = useState<ArmSnapshot>(() => emptySnap("pramana"));
  const [baselineSnap, setBaselineSnap] = useState<ArmSnapshot>(() =>
    emptySnap("baseline"),
  );
  const [pramanaSnap, setPramanaSnap] = useState<ArmSnapshot>(() =>
    emptySnap("pramana"),
  );
  const [graph, setGraph] = useState<GraphModel>(SKELETON_GRAPH);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [highlightId, setHighlightId] = useState<string | null>(null);

  const showCompare =
    compareMode &&
    activeJourney != null &&
    (activeJourney === "J2" || activeJourney === "J3") &&
    (baselineSnap.raw != null || pramanaSnap.raw != null);

  const active = showCompare ? pramanaSnap : primary;

  const refreshGraph = useCallback(async (episodeId?: string | null) => {
    try {
      const snap = await getGraphSnapshot(episodeId ?? undefined);
      setGraph({ nodes: snap.nodes ?? [], edges: snap.edges ?? [] });
    } catch {
      /* keep last graph */
    }
  }, []);

  const applyOperator = useCallback(
    async (info: { episodeId?: string | null; highlight?: string | null }) => {
      setHighlightId(info.highlight ?? null);
      const eid = info.episodeId ?? null;
      if (!eid) {
        await refreshGraph(primary.episodeId);
        return;
      }
      try {
        const ep = await getEpisode(eid);
        const env = ep.envelope ?? null;
        const mode = String((ep as { mode?: string }).mode ?? ep.arm ?? "");
        const lastDec = Array.isArray(ep.decisions)
          ? ep.decisions[ep.decisions.length - 1]
          : null;
        setPrimary({
          arm:
            mode.toUpperCase() === "BASELINE" || ep.arm === "baseline"
              ? "baseline"
              : "pramana",
          episodeId: ep.episode_id,
          proofId: ep.proof_id ?? null,
          ruleId:
            typeof lastDec?.rule_id === "string" ? lastDec.rule_id : null,
          messages: [],
          envelope: env,
          ledger: ep.ledger ?? genesisLedger(env, ep.status),
          trace: lastDec?.rule_trace ?? ep.rule_trace ?? [],
          verdict:
            (ep.last_verdict as string | undefined) ??
            (typeof lastDec?.verdict === "string" ? lastDec.verdict : null),
          status: ep.status ?? null,
          narrative: "Updated from the operator.",
          raw: null,
        });
        await refreshGraph(eid);
      } catch {
        await refreshGraph(eid);
      }
    },
    [primary.episodeId, refreshGraph],
  );

  const [params] = useSearchParams();

  useEffect(() => {
    void refreshGraph(null);
  }, [refreshGraph]);

  useEffect(() => {
    const eid = params.get("episode");
    if (!eid) return;
    let cancelled = false;
    (async () => {
      try {
        const ep = await getEpisode(eid);
        if (cancelled) return;
        const env = ep.envelope ?? null;
        const mode = String((ep as { mode?: string }).mode ?? ep.arm ?? "");
        setPrimary({
          arm: mode.toUpperCase() === "BASELINE" || ep.arm === "baseline" ? "baseline" : "pramana",
          episodeId: ep.episode_id,
          proofId: ep.proof_id ?? null,
          ruleId: null,
          messages: [],
          envelope: env,
          ledger: ep.ledger ?? genesisLedger(env, ep.status),
          trace: ep.rule_trace ?? [],
          verdict: (ep.last_verdict as string | undefined) ?? null,
          status: ep.status ?? null,
          narrative: "Loaded from episode history.",
          raw: null,
        });
        await refreshGraph(eid);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params, refreshGraph]);

  useEffect(() => {
    if (!highlightId) return;
    const node = graph.nodes.find((n) => n.id === highlightId);
    if (node) setSelected(node);
  }, [highlightId, graph]);

  const outcomeCopy = useMemo(() => {
    const verdict = active.verdict;
    if (!verdict) {
      if (active.episodeId && !active.raw) {
        return {
          tone: "admit" as const,
          title: "Intent sealed — ledger is live at ₹0",
          body: "Propose checkout to send a payment through the gate, or run J3 to see fragmentation.",
        };
      }
      return null;
    }
    if (verdict === "DENY") {
      return {
        tone: "deny" as const,
        title: "Denied — the product worked",
        body: `HTTP 200 + DENY is a successful custody outcome${
          active.ruleId ? ` (${active.ruleId})` : ""
        }.`,
      };
    }
    if (verdict === "ADMIT") {
      return {
        tone: "admit" as const,
        title: "Admitted and (if mock) captured",
        body: "Every predicate held. Money may move.",
      };
    }
    if (verdict === "ESCALATE") {
      return {
        tone: "escalate" as const,
        title: "Needs a human tap",
        body: "Confirm below — the classifier can only add friction.",
      };
    }
    return null;
  }, [active]);

  async function applyDemo(scenario: DemoScenario) {
    setBusy(true);
    setError(null);
    setConfirmNote(null);
    setActiveJourney(scenario);
    try {
      const useCompare =
        compareMode && (scenario === "J2" || scenario === "J3");
      if (useCompare) {
        const { baseline, pramana } = await runDemoCompare(scenario);
        const b = snapFromDemo("baseline", baseline);
        const p = snapFromDemo("pramana", pramana);
        setBaselineSnap(b);
        setPramanaSnap(p);
        setPrimary(p);
        if (typeof pramana.utterance === "string") setPrompt(pramana.utterance);
        await refreshGraph(p.episodeId);
      } else {
        const res = await runDemo({ scenario, arm });
        const snap = snapFromDemo(arm, res);
        setPrimary(snap);
        setBaselineSnap(emptySnap("baseline"));
        setPramanaSnap(emptySnap("pramana"));
        if (typeof res.utterance === "string") setPrompt(res.utterance);
        await refreshGraph(snap.episodeId);
      }
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  async function sealUtterance() {
    const text = prompt.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    setConfirmNote(null);
    setActiveJourney(null);
    try {
      const ep = await createEpisode({ utterance: text, arm });
      const env = ep.envelope ?? null;
      const led = ep.ledger ?? genesisLedger(env, ep.status);
      setPrimary({
        arm,
        episodeId: ep.episode_id,
        proofId: ep.proof_id ?? null,
        ruleId: null,
        messages: [
          { role: "user", content: text, taint: "USER" },
          {
            role: "system",
            content: `Sealed. Episode ledger starts at ${formatPaise(0)} against the envelope cap.`,
          },
        ],
        envelope: env,
        ledger: led,
        trace: [],
        verdict: null,
        status: ep.status ?? "OPEN",
        narrative: "Seal-before-read: catalog has not entered context yet.",
        raw: null,
      });
      setBaselineSnap(emptySnap("baseline"));
      setPramanaSnap(emptySnap("pramana"));
      await refreshGraph(ep.episode_id);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  async function proposeCheckout() {
    if (!primary.episodeId) return;
    setBusy(true);
    setError(null);
    try {
      const res = await checkoutEpisode(primary.episodeId);
      const snap = snapFromDemo(arm, res);
      setPrimary(snap);
      await refreshGraph(snap.episodeId);
    } catch (e) {
      setError(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitPrompt() {
    const text = prompt.trim();
    if (!text) return;
    setBusy(true);
    setError(null);
    try {
      const { plan } = await planGraphPrompt(text, primary.episodeId);
      if (plan.intent === "demo" && plan.journey) {
        const sc = JOURNEY_FROM_API[plan.journey];
        if (sc) {
          setBusy(false);
          await applyDemo(sc);
          return;
        }
      }
      if (plan.intent === "checkout" && primary.episodeId) {
        setBusy(false);
        await proposeCheckout();
        return;
      }
      setBusy(false);
      await sealUtterance();
    } catch (e) {
      setError(friendlyError(e));
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!active.episodeId || active.verdict !== "ESCALATE") return;
    setBusy(true);
    try {
      const steps = extractAuthorizeSteps(active.raw);
      const last = steps[steps.length - 1];
      const res = await confirmEscalation(active.episodeId, {
        approved: true,
        decision_id: last?.decision_id ?? undefined,
      });
      setConfirmNote(`Confirmed · ${String(res.verdict ?? res.status ?? "ok")}`);
    } catch (e) {
      setConfirmNote(friendlyError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="demo-page command-page">
      <header className="demo-hero">
        <div>
          <p className="eyebrow">Command graph</p>
          <h1>Watch custody move</h1>
          <p className="lede">
            Each node is a real subsystem. Ask the local operator, or run a
            scripted journey — the graph lights the path the money actually took.
          </p>
        </div>
        <div className="demo-hero-controls">
          <label className="compare-toggle">
            <input
              type="checkbox"
              checked={compareMode}
              onChange={(e) => setCompareMode(e.target.checked)}
            />
            Compare arms on J2 / J3
          </label>
          {!compareMode && (
            <div className="arm-switch" role="group" aria-label="Arm">
              <button
                type="button"
                className={arm === "baseline" ? "on" : ""}
                onClick={() => setArm("baseline")}
              >
                Baseline
              </button>
              <button
                type="button"
                className={arm === "pramana" ? "on" : ""}
                onClick={() => setArm("pramana")}
              >
                Pramana
              </button>
            </div>
          )}
        </div>
      </header>

      <div className="prompt-dock">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") void submitPrompt();
          }}
          placeholder='Try “run fragmentation” or seal a dinner order…'
          aria-label="Command prompt"
        />
        <button
          type="button"
          className="btn"
          disabled={busy || !prompt.trim()}
          onClick={() => void submitPrompt()}
        >
          {busy ? "Running…" : "Send"}
        </button>
        <button
          type="button"
          className="btn ghost"
          disabled={busy || !prompt.trim()}
          onClick={() => void sealUtterance()}
        >
          Seal only
        </button>
        {primary.episodeId && !primary.verdict && (
          <button
            type="button"
            className="btn ghost"
            disabled={busy}
            onClick={() => void proposeCheckout()}
          >
            Propose checkout
          </button>
        )}
      </div>

      <div className="journey-chips" aria-label="Scripted journeys">
        {JOURNEYS.map((j) => (
          <button
            key={j.id}
            type="button"
            className={`chip${activeJourney === j.id ? " on" : ""}`}
            disabled={busy}
            onClick={() => void applyDemo(j.id)}
          >
            <strong>{j.id}</strong> {j.title}
            <span>{j.beat}</span>
          </button>
        ))}
      </div>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}

      <div className="graph-stage">
        <LivingGraph
          graph={graph.nodes.length ? graph : SKELETON_GRAPH}
          selectedId={selected?.id}
          highlightId={highlightId}
          onSelect={setSelected}
        />
        <aside className="graph-inspect">
          <h2>Inspector</h2>
          {selected ? (
            <>
              <p className="inspect-kind">{selected.kind}</p>
              <h3>{selected.label}</h3>
              <p>{selected.detail || "No excerpt."}</p>
              {selected.state && (
                <span className={`pill ${selected.state}`}>{selected.state}</span>
              )}
            </>
          ) : (
            <p className="hint">
              Click Seal, Gate, Ledger, or Proof. Packets on edges are live
              authorizes.
            </p>
          )}
          {outcomeCopy && (
            <div className={`outcome-banner ${outcomeCopy.tone}`}>
              <strong>{outcomeCopy.title}</strong>
              <span>{outcomeCopy.body}</span>
              {active.proofId && (
                <Link
                  className="outcome-link"
                  to={`/proof?id=${encodeURIComponent(active.proofId)}`}
                >
                  Open this proof →
                </Link>
              )}
              {active.verdict === "ESCALATE" && (
                <button
                  type="button"
                  className="btn sm"
                  disabled={busy}
                  onClick={() => void handleConfirm()}
                >
                  Confirm
                </button>
              )}
            </div>
          )}
          {confirmNote && <p className="hint">{confirmNote}</p>}
        </aside>
      </div>

      <OperatorChat episodeId={active.episodeId} onApplied={(info) => void applyOperator(info)} />

      {showCompare && (
        <div
          className={`thesis-ribbon ${
            baselineSnap.verdict === "ADMIT" && pramanaSnap.verdict === "DENY"
              ? "win"
              : ""
          }`}
        >
          {baselineSnap.verdict === "ADMIT" && pramanaSnap.verdict === "DENY" ? (
            <>
              <strong>Thesis visible.</strong> Same injection. Baseline admits.
              Pramana denies
              {pramanaSnap.ruleId ? ` on ${pramanaSnap.ruleId}` : ""}.
            </>
          ) : (
            <>Side-by-side: per-txn rail vs sealed episode.</>
          )}
        </div>
      )}

      {showCompare ? (
        <div className="compare-grid">
          <ComparePane title="Arm A · Baseline" snap={baselineSnap} />
          <ComparePane title="Arm B · Pramana" snap={pramanaSnap} />
        </div>
      ) : (
        <div className="command-grid">
          <div className="panel">
            <div className="panel-hd">
              <h2>Sealed envelope</h2>
              <span className="meta">{active.status ?? "no episode"}</span>
            </div>
            <div className="panel-bd">
              <EnvelopePanel envelope={active.envelope} />
            </div>
          </div>
          <div className="panel">
            <div className="panel-hd">
              <h2>Episode ledger</h2>
              <span className="meta">what R6 sees</span>
            </div>
            <div className="panel-bd">
              <LedgerPanel
                ledger={active.ledger}
                status={active.status}
                capFallback={
                  active.envelope?.constraints?.episode_total_max_paise ??
                  active.envelope?.episode_total_max_paise
                }
                maxTxnFallback={
                  active.envelope?.constraints?.max_transactions ??
                  active.envelope?.max_transactions
                }
              />
            </div>
          </div>
          <div className="panel">
            <div className="panel-hd">
              <h2>Money trail</h2>
              <span className="meta">authorize steps</span>
            </div>
            <div className="panel-bd">
              <MoneyTimeline result={active.raw} />
            </div>
          </div>
          <div className="panel">
            <div className="panel-hd">
              <h2>Gate strip</h2>
              <span className="meta">
                {active.verdict ?? "awaiting a money action"}
              </span>
            </div>
            <div className="panel-bd">
              <RuleStrip trace={active.trace} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

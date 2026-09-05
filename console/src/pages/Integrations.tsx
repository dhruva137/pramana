import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  getIntegrationsGuide,
  testRazorpay,
} from "../lib/api";
import { loadKeys } from "../lib/keys";
import type { IntegrationsGuide, RazorpayTestResult } from "../lib/types";

const FALLBACK_CURL = `# 1. Seal intent BEFORE any catalog tool results
curl -s localhost:8000/v1/episodes -H 'Content-Type: application/json' -d '{
  "utterance": "Order dinner from Swiggy, under 600 total",
  "mode": "PRAMANA_ON",
  "consent_cap_paise": 200000
}'

# 2. Authorize — DENY is HTTP 200 with verdict in body
curl -s localhost:8000/v1/actions/authorize -H 'Content-Type: application/json' -d '{
  "episode_id": "EP",
  "action": {
    "kind": "PAYMENT",
    "amount_paise": 45000,
    "currency": "INR",
    "payee": {"merchant_id": "swiggy", "account_ref": "acc_swiggy_settle"},
    "instrument": "upi_reserve_pay:tok_x",
    "delivery_address_hash": "sha256:demo_address",
    "human_confirmed": true
  },
  "provenance": { "amount_paise": {"taint": "MERCHANT_STRUCTURED", "ledger_idx": 1} }
}'`;

const FALLBACK_PYTHON = `from examples.pramana_client import PramanaClient

client = PramanaClient("http://127.0.0.1:8000")
ep = client.create_episode("Order biryani from Swiggy under 600")
decision = client.authorize(ep["episode_id"], action, provenance)
if decision["verdict"] == "ADMIT":
    client.execute(decision["decision_id"])
elif decision["verdict"] == "DENY":
    proof = client.get_proof(decision["proof_id"])`;

function asCodeBlock(
  value: string | Record<string, string> | undefined,
  fallback: string,
): string {
  if (!value) return fallback;
  if (typeof value === "string") return value;
  return Object.entries(value)
    .map(([k, v]) => `# ${k}\n${v}`)
    .join("\n\n");
}

export function Integrations() {
  const [guide, setGuide] = useState<IntegrationsGuide | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testNote, setTestNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setGuide(await getIntegrationsGuide());
    } catch (e) {
      setGuide(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const curl = useMemo(
    () => asCodeBlock(guide?.curl ?? guide?.snippets?.curl, FALLBACK_CURL),
    [guide],
  );
  const python = useMemo(
    () => asCodeBlock(guide?.python ?? guide?.snippets?.python, FALLBACK_PYTHON),
    [guide],
  );

  const steps = useMemo(() => {
    if (Array.isArray(guide?.steps) && guide.steps.length) return guide.steps;
    if (Array.isArray(guide?.clone_local)) return guide.clone_local as string[];
    if (typeof guide?.clone_local === "string") return [guide.clone_local];
    const flow = (guide as { flow?: Array<{ purpose?: string; path?: string }> } | null)
      ?.flow;
    if (Array.isArray(flow) && flow.length) {
      return flow.map(
        (f) => `${f.purpose ?? "step"}${f.path ? ` → ${f.path}` : ""}`,
      );
    }
    return [
      "Clone repo · pip install -r requirements.txt",
      "Optional: paste rzp_test_* / Gemini in Settings",
      "uvicorn core.app:app --port 8000",
      "Open Dashboard → Live → run J3 compare",
    ];
  }, [guide]);

  async function handleTest() {
    const keys = loadKeys();
    setTestNote("Testing…");
    try {
      const res: RazorpayTestResult = await testRazorpay({
        key_id: keys.razorpayKeyId || undefined,
        key_secret: keys.razorpayKeySecret || undefined,
      });
      setTestNote(
        res.ok
          ? `${res.mode ?? "ok"}: ${res.message ?? "connection ok"}`
          : res.error ?? res.message ?? "Test failed",
      );
    } catch (e) {
      setTestNote(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <div className="integrations-page stack">
      <header className="section-title">
        <div>
          <h1>Integrations</h1>
          <p>
            {guide?.architecture ??
              "Agent → Pramana gate → Razorpay test API. You do not replace Razorpay — you refuse money moves until the episode admits."}
          </p>
        </div>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() => void load()}
        >
          {busy ? "Loading…" : "Refresh guide"}
        </button>
      </header>

      <div className="callout warn">
        Defense-only sandbox. Use <code>rzp_test_*</code> only. DENY is HTTP 200
        with <code>verdict</code> in the body — not a transport failure.
      </div>

      {error && (
        <div className="error-banner">
          Guide API unavailable ({error}). Showing docs fallback snippets.
        </div>
      )}

      <section className="panel">
        <div className="panel-hd">
          <h2>{guide?.title ?? "Clone-local"}</h2>
          <span className="meta">sidecar path</span>
        </div>
        <div className="panel-bd">
          <ol className="integ-steps">
            {steps.map((s, i) => (
              <li key={`${i}-${s.slice(0, 24)}`}>{s}</li>
            ))}
          </ol>
          <div className="btn-row" style={{ marginTop: "0.85rem" }}>
            <Link className="btn" to="/settings">
              Paste keys in Settings
            </Link>
            <button
              type="button"
              className="btn ghost"
              onClick={() => void handleTest()}
            >
              Test Razorpay connection
            </button>
            <Link className="btn ghost sm" to="/live">
              Run live demo
            </Link>
          </div>
          {testNote && <p className="hint settings-feedback">{testNote}</p>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-hd">
          <h2>curl</h2>
          <span className="meta">minimal flow</span>
        </div>
        <div className="panel-bd">
          <pre className="code-block">{curl}</pre>
        </div>
      </section>

      <section className="panel">
        <div className="panel-hd">
          <h2>Python</h2>
          <span className="meta">examples/pramana_client.py</span>
        </div>
        <div className="panel-bd">
          <pre className="code-block">{python}</pre>
        </div>
      </section>

      {Array.isArray(guide?.notes) && guide.notes.length > 0 && (
        <ul className="integ-notes">
          {guide.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

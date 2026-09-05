import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  getSettingsStatus,
  pingLlm,
  testRazorpay,
} from "../lib/api";
import {
  clearKeys,
  EMPTY_KEYS,
  hasAnyKey,
  loadKeys,
  saveKeys,
} from "../lib/keys";
import type { ApiKeys, PingLlmResult, RazorpayTestResult, SettingsStatus } from "../lib/types";

export function Settings() {
  const [draft, setDraft] = useState<ApiKeys>(() => loadKeys());
  const [status, setStatus] = useState<SettingsStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNote, setSavedNote] = useState<string | null>(null);
  const [pingNote, setPingNote] = useState<string | null>(null);
  const [rzpNote, setRzpNote] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setStatus(await getSettingsStatus());
    } catch (e) {
      setStatus(null);
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  function update<K extends keyof ApiKeys>(key: K, value: string) {
    setDraft((d) => ({ ...d, [key]: value }));
    setSavedNote(null);
  }

  function handleSave() {
    saveKeys(draft);
    setSavedNote("Keys saved to localStorage on this device.");
    void refreshStatus();
  }

  function handleClear() {
    clearKeys();
    setDraft({ ...EMPTY_KEYS });
    setSavedNote("Keys cleared.");
    setPingNote(null);
    setRzpNote(null);
  }

  async function handlePing(provider: "gemini" | "anthropic") {
    setPingNote(`Pinging ${provider}…`);
    try {
      const res: PingLlmResult = await pingLlm(provider);
      setPingNote(
        res.ok
          ? `${provider}: ok${res.status_code != null ? ` · HTTP ${res.status_code}` : ""}`
          : `${provider}: ${res.error ?? `failed · ${res.status_code ?? "?"}`}`,
      );
    } catch (e) {
      setPingNote(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function handleTestRazorpay() {
    setRzpNote("Testing Razorpay…");
    try {
      const res: RazorpayTestResult = await testRazorpay({
        key_id: draft.razorpayKeyId || undefined,
        key_secret: draft.razorpayKeySecret || undefined,
      });
      setRzpNote(
        res.ok
          ? `${res.mode ?? "ok"}: ${res.message ?? "reachable"}`
          : res.error ?? res.message ?? "Razorpay test failed",
      );
    } catch (e) {
      setRzpNote(e instanceof ApiError ? e.message : String(e));
    }
  }

  const llm = status?.llm;
  const rzp = status?.razorpay;

  return (
    <div className="settings-page stack">
      <header className="section-title">
        <div>
          <h1>Settings</h1>
          <p>
            Keys stay in <code>localStorage</code> and ride as{" "}
            <code>X-Pramana-*-Key</code> headers — never written to server env
            from this UI. MOCK works with zero keys.
          </p>
        </div>
        <button
          type="button"
          className="btn ghost"
          disabled={busy}
          onClick={() => void refreshStatus()}
        >
          {busy ? "Refreshing…" : "Refresh status"}
        </button>
      </header>

      {error && <div className="error-banner">{error}</div>}

      <section className="panel">
        <div className="panel-hd">
          <h2>Environment</h2>
          <span className="meta">{status?.env ?? "—"}</span>
        </div>
        <div className="panel-bd settings-status-grid">
          <div className="status-tile">
            <span className="kpi-label">Mock mode</span>
            <span className="kpi-value sm">
              {status?.mock_mode == null ? "—" : status.mock_mode ? "ON" : "OFF"}
            </span>
          </div>
          <div className="status-tile">
            <span className="kpi-label">Sealer</span>
            <span className="kpi-value sm">{llm?.sealer_mode ?? "—"}</span>
          </div>
          <div className="status-tile">
            <span className="kpi-label">Gemini (server)</span>
            <span className="kpi-value sm">
              {llm?.gemini_configured ? "configured" : "empty"}
            </span>
          </div>
          <div className="status-tile">
            <span className="kpi-label">Anthropic (server)</span>
            <span className="kpi-value sm">
              {llm?.anthropic_configured ? "configured" : "empty"}
            </span>
          </div>
          <div className="status-tile">
            <span className="kpi-label">Razorpay</span>
            <span className="kpi-value sm">
              {rzp?.configured
                ? `${rzp.key_id_prefix ?? "rzp_test"}…`
                : "not configured"}
            </span>
          </div>
          <div className="status-tile">
            <span className="kpi-label">Operator</span>
            <span className="kpi-value sm">
              {status?.operator?.model ?? "qwen3:1.7b"}
            </span>
          </div>
          <div className="status-tile">
            <span className="kpi-label">JWKS</span>
            <span className="kpi-value sm mono">
              {status?.jwks_url ? (
                <a href={status.jwks_url} target="_blank" rel="noreferrer">
                  {status.jwks_url}
                </a>
              ) : (
                "/.well-known/pramana-jwks.json"
              )}
            </span>
          </div>
        </div>
        {status?.operator?.note && (
          <p className="hint settings-note">{status.operator.note}</p>
        )}
        {status?.note && <p className="hint settings-note">{status.note}</p>}
        <dl className="kv settings-kids">
          <dt>Seal kid</dt>
          <dd className="mono">{status?.keys?.seal_kid ?? "—"}</dd>
          <dt>Proof kid</dt>
          <dd className="mono">{status?.keys?.proof_kid ?? "—"}</dd>
          <dt>Ephemeral keys</dt>
          <dd>{status?.keys?.ephemeral ? "yes" : "no"}</dd>
        </dl>
      </section>

      <section className="panel">
        <div className="panel-hd">
          <h2>LLM keys</h2>
          <span className="meta">optional · live sealing</span>
        </div>
        <div className="panel-bd">
          <div className="callout" style={{ marginBottom: "1rem" }}>
            Free Gemini key:{" "}
            <a
              href="https://aistudio.google.com/apikey"
              target="_blank"
              rel="noreferrer"
            >
              aistudio.google.com/apikey
            </a>
            . Leave empty for MOCK sealer.
          </div>
          <div className="field">
            <label htmlFor="set-gemini">GEMINI_API_KEY</label>
            <input
              id="set-gemini"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="AIza…"
              value={draft.gemini}
              onChange={(e) => update("gemini", e.target.value.trim())}
            />
          </div>
          <div className="field">
            <label htmlFor="set-anthropic">ANTHROPIC_API_KEY</label>
            <input
              id="set-anthropic"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="sk-ant-…"
              value={draft.anthropic}
              onChange={(e) => update("anthropic", e.target.value.trim())}
            />
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn ghost"
              disabled={!draft.gemini}
              onClick={() => void handlePing("gemini")}
            >
              Ping Gemini
            </button>
            <button
              type="button"
              className="btn ghost"
              disabled={!draft.anthropic}
              onClick={() => void handlePing("anthropic")}
            >
              Ping Anthropic
            </button>
          </div>
          {pingNote && <p className="hint settings-feedback">{pingNote}</p>}
        </div>
      </section>

      <section className="panel">
        <div className="panel-hd">
          <h2>Razorpay test keys</h2>
          <span className="meta">rzp_test_* only</span>
        </div>
        <div className="panel-bd">
          <div className="callout warn" style={{ marginBottom: "1rem" }}>
            Live keys (<code>rzp_live_*</code>) are refused. Empty keys → mock
            executor.
          </div>
          <div className="field">
            <label htmlFor="set-rzp-id">RAZORPAY_KEY_ID</label>
            <input
              id="set-rzp-id"
              type="text"
              autoComplete="off"
              spellCheck={false}
              placeholder="rzp_test_…"
              value={draft.razorpayKeyId}
              onChange={(e) => update("razorpayKeyId", e.target.value.trim())}
            />
          </div>
          <div className="field">
            <label htmlFor="set-rzp-secret">RAZORPAY_KEY_SECRET</label>
            <input
              id="set-rzp-secret"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft.razorpayKeySecret}
              onChange={(e) =>
                update("razorpayKeySecret", e.target.value.trim())
              }
            />
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn ghost"
              onClick={() => void handleTestRazorpay()}
            >
              Test Razorpay connection
            </button>
            <Link className="btn ghost sm" to="/integrations">
              Integrations guide
            </Link>
          </div>
          {rzpNote && <p className="hint settings-feedback">{rzpNote}</p>}
        </div>
      </section>

      <div className="settings-actions btn-row">
        <button type="button" className="btn" onClick={handleSave}>
          Save keys
        </button>
        <button type="button" className="btn ghost" onClick={handleClear}>
          Clear
        </button>
        <span className="hint">
          {hasAnyKey(draft)
            ? "At least one key is set locally."
            : "No local keys — MOCK sealer + mock payments."}
        </span>
      </div>
      {savedNote && <p className="hint settings-feedback">{savedNote}</p>}
    </div>
  );
}

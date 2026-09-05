import { useEffect, useState } from "react";
import {
  clearKeys,
  EMPTY_KEYS,
  hasAnyKey,
  loadKeys,
  saveKeys,
} from "../lib/keys";
import type { ApiKeys } from "../lib/types";

type Props = {
  open: boolean;
  onClose: () => void;
  onSaved: (keys: ApiKeys) => void;
};

export function SettingsPanel({ open, onClose, onSaved }: Props) {
  const [draft, setDraft] = useState<ApiKeys>(EMPTY_KEYS);

  useEffect(() => {
    if (open) setDraft(loadKeys());
  }, [open]);

  if (!open) return null;

  function update<K extends keyof ApiKeys>(key: K, value: string) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function handleSave() {
    saveKeys(draft);
    onSaved(draft);
    onClose();
  }

  function handleClear() {
    clearKeys();
    setDraft({ ...EMPTY_KEYS });
    onSaved({ ...EMPTY_KEYS });
  }

  return (
    <div className="settings-backdrop" onClick={onClose} role="presentation">
      <aside
        className="settings-panel"
        onClick={(e) => e.stopPropagation()}
        aria-label="API keys settings"
      >
        <div className="panel-hd">
          <h2>Settings · API keys</h2>
          <button type="button" className="btn ghost sm" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="panel-bd">
          <div className="callout" style={{ marginBottom: "1rem" }}>
            App works in <strong>MOCK</strong> mode with zero keys. Paste a free
            Gemini key only if you want live LLM sealing.
          </div>
          <p className="hint" style={{ marginBottom: "1rem" }}>
            Keys stay in <code>localStorage</code> on this device and are sent
            per-request as <code>X-Pramana-*-Key</code> headers — never written
            to the server env from this UI.
          </p>

          <div className="field">
            <label htmlFor="gemini">GEMINI_API_KEY</label>
            <input
              id="gemini"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="AIza…"
              value={draft.gemini}
              onChange={(e) => update("gemini", e.target.value.trim())}
            />
            <p className="hint">
              Free key:{" "}
              <a
                href="https://aistudio.google.com/apikey"
                target="_blank"
                rel="noreferrer"
              >
                aistudio.google.com/apikey
              </a>
            </p>
          </div>

          <div className="field">
            <label htmlFor="anthropic">ANTHROPIC_API_KEY (optional)</label>
            <input
              id="anthropic"
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder="sk-ant-…"
              value={draft.anthropic}
              onChange={(e) => update("anthropic", e.target.value.trim())}
            />
          </div>

          <div className="field">
            <label htmlFor="rzp-id">RAZORPAY_KEY_ID (optional, test only)</label>
            <input
              id="rzp-id"
              type="text"
              autoComplete="off"
              spellCheck={false}
              placeholder="rzp_test_…"
              value={draft.razorpayKeyId}
              onChange={(e) => update("razorpayKeyId", e.target.value.trim())}
            />
          </div>

          <div className="field">
            <label htmlFor="rzp-secret">RAZORPAY_KEY_SECRET (optional)</label>
            <input
              id="rzp-secret"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft.razorpayKeySecret}
              onChange={(e) =>
                update("razorpayKeySecret", e.target.value.trim())
              }
            />
          </div>

          <p className="hint">
            {hasAnyKey(draft)
              ? "At least one key is set."
              : "No keys set — MOCK sealer + mock payments."}
          </p>
        </div>
        <div className="settings-foot">
          <button type="button" className="btn" onClick={handleSave}>
            Save keys
          </button>
          <button type="button" className="btn ghost" onClick={handleClear}>
            Clear
          </button>
        </div>
      </aside>
    </div>
  );
}

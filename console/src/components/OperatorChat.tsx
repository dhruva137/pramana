import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  approveOperator,
  operatorChat,
  operatorStatus,
} from "../lib/api";

type Trace = {
  name: string;
  args?: Record<string, unknown>;
  status?: string;
  result?: unknown;
};

type Msg = {
  role: "user" | "assistant" | "system";
  content: string;
  trace?: Trace[];
};

type Pending = {
  approval_id: string;
  tool: string;
  args?: Record<string, unknown>;
  reason?: string;
};

type Props = {
  episodeId?: string | null;
  onApplied?: (info: {
    episodeId?: string | null;
    highlight?: string | null;
  }) => void;
};

const STARTERS = [
  "Prepare demo data",
  "Run fragmentation on Pramana",
  "What’s on the dashboard?",
  "List recent proofs",
];

export function OperatorChat({ episodeId, onApplied }: Props) {
  const [status, setStatus] = useState("checking Ollama…");
  const [auto, setAuto] = useState(false);
  const [text, setText] = useState("Prepare demo data");
  const [busy, setBusy] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([
    {
      role: "system",
      content:
        "Local Qwen 1.7B operator. It can read every surface and run journeys. Money tools wait for Approve unless Auto is on. The gate itself never talks to this model.",
    },
  ]);
  const [pending, setPending] = useState<Pending | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void operatorStatus()
      .then((s) => {
        const o = s.ollama;
        if (o?.ok && o.has_model) {
          setStatus(`${o.model} · tools live`);
        } else if (o?.ok) {
          setStatus(`Ollama up · missing ${o.model} · keyword fallback`);
        } else {
          setStatus("Ollama offline · keyword fallback");
        }
      })
      .catch(() => setStatus("Operator API unreachable"));
  }, []);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, pending]);

  async function send(preset?: string) {
    const message = (preset ?? text).trim();
    if (!message || busy) return;
    setBusy(true);
    if (!preset) setText("");
    const next = [...msgs, { role: "user" as const, content: message }];
    setMsgs(next);
    try {
      const prior = next
        .filter((m) => m.role !== "system")
        .slice(0, -1)
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await operatorChat({
        message,
        episode_id: episodeId,
        auto_approve: auto,
        history: prior,
      });
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          content: res.reply,
          trace: res.tool_trace,
        },
      ]);
      setPending((cur) => res.pending_approval ?? cur);
      onApplied?.({
        episodeId: res.episode_id,
        highlight: res.highlight,
      });
    } catch (e) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          content: e instanceof ApiError ? e.message : String(e),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  async function decide(ok: boolean) {
    if (!pending) return;
    setBusy(true);
    try {
      const res = await approveOperator(pending.approval_id, ok);
      setPending(null);
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          content: ok
            ? `Approved ${res.tool}. ${JSON.stringify(res.result ?? {}).slice(0, 180)}`
            : `Rejected ${pending.tool}.`,
        },
      ]);
      if (ok) {
        onApplied?.({
          episodeId: res.episode_id,
          highlight: res.highlight,
        });
      }
    } catch (e) {
      setMsgs((m) => [
        ...m,
        {
          role: "assistant",
          content: e instanceof ApiError ? e.message : String(e),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="op-chat">
      <div className="op-chat-hd">
        <div>
          <h2>Operator</h2>
          <span className="meta">{status}</span>
        </div>
        <label className="compare-toggle">
          <input
            type="checkbox"
            checked={auto}
            onChange={(e) => setAuto(e.target.checked)}
          />
          Auto-approve
        </label>
      </div>
      <div className="op-starters" aria-label="Starter prompts">
        {STARTERS.map((s) => (
          <button
            key={s}
            type="button"
            className="chip sm"
            disabled={busy}
            onClick={() => void send(s)}
          >
            {s}
          </button>
        ))}
      </div>
      <div className="op-log" ref={logRef}>
        {msgs.map((m, i) => (
          <div key={i} className={`op-msg ${m.role}`}>
            <span className="role">{m.role}</span>
            <p>{m.content}</p>
            {m.trace && m.trace.length > 0 && (
              <ul className="op-trace">
                {m.trace.map((t, j) => (
                  <li key={j}>
                    <code>{t.name}</code> · {t.status}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
      {pending && (
        <div className="op-approve">
          <p>
            Approve <strong>{pending.tool}</strong>? {pending.reason}
          </p>
          <div className="btn-row">
            <button
              type="button"
              className="btn sm"
              disabled={busy}
              onClick={() => void decide(true)}
            >
              Approve
            </button>
            <button
              type="button"
              className="btn ghost sm"
              disabled={busy}
              onClick={() => void decide(false)}
            >
              Reject
            </button>
          </div>
        </div>
      )}
      <div className="op-compose">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder="Ask: seed demo, run J3, what’s on the ledger…"
          aria-label="Operator message"
        />
        <button
          type="button"
          className="btn"
          disabled={busy || !text.trim()}
          onClick={() => void send()}
        >
          {busy ? "…" : "Ask"}
        </button>
      </div>
    </div>
  );
}

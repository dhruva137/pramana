import { loadKeys } from "./keys";
import type {
  Arm,
  BenchSummary,
  DashboardSummary,
  DemoRunResult,
  DemoScenario,
  DivergenceProof,
  Envelope,
  EpisodeDetail,
  EpisodeSummary,
  IntegrationsGuide,
  NarrateResult,
  PingLlmResult,
  RazorpayTestResult,
  SettingsStatus,
  VerifyResult,
} from "./types";

export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") ??
  (import.meta.env.PROD ? "" : "http://127.0.0.1:8000");

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function authHeaders(): Record<string, string> {
  const keys = loadKeys();
  const h: Record<string, string> = {
    Accept: "application/json",
  };
  if (keys.gemini) h["X-Pramana-Gemini-Key"] = keys.gemini;
  if (keys.anthropic) h["X-Pramana-Anthropic-Key"] = keys.anthropic;
  if (keys.razorpayKeyId) h["X-Pramana-Razorpay-Key-Id"] = keys.razorpayKeyId;
  if (keys.razorpayKeySecret) {
    h["X-Pramana-Razorpay-Key-Secret"] = keys.razorpayKeySecret;
  }
  return h;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  const headers = new Headers(init.headers);
  const auth = authHeaders();
  for (const [k, v] of Object.entries(auth)) {
    if (!headers.has(k)) headers.set(k, v);
  }
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let res: Response;
  try {
    res = await fetch(url, { ...init, headers });
  } catch (err) {
    throw new ApiError(
      `Network error talking to ${API_BASE}. Is the API up?`,
      0,
      err,
    );
  }

  const text = await res.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!res.ok) {
    const msg =
      typeof body === "object" &&
      body &&
      "error" in body &&
      typeof (body as { error?: { message?: string } }).error?.message === "string"
        ? (body as { error: { message: string } }).error.message
        : `HTTP ${res.status}`;
    throw new ApiError(msg, res.status, body);
  }

  return body as T;
}

export async function createEpisode(body: {
  utterance: string;
  arm: Arm;
}): Promise<EpisodeDetail> {
  // Only force mock sealing when the operator has no LLM keys locally.
  const keys = loadKeys();
  const force_mock = !(keys.gemini || keys.anthropic);
  const raw = await apiFetch<
    EpisodeDetail | { ok?: boolean; episode_id?: string; envelope?: Envelope }
  >("/v1/episodes", {
    method: "POST",
    body: JSON.stringify({
      utterance: body.utterance,
      mode: body.arm === "pramana" ? "PRAMANA_ON" : "BASELINE",
      force_mock,
    }),
  });
  return raw as EpisodeDetail;
}

export async function getEpisode(id: string): Promise<EpisodeDetail> {
  return apiFetch(`/v1/episodes/${encodeURIComponent(id)}`);
}

export async function listEpisodes(): Promise<EpisodeSummary[]> {
  const data = await apiFetch<EpisodeSummary[] | { episodes: EpisodeSummary[] }>(
    "/v1/episodes",
  );
  if (Array.isArray(data)) return data;
  return data.episodes ?? [];
}

/** Console scenario ids → the journey vocabulary `POST /v1/demo/run` accepts. */
const DEMO_JOURNEY: Record<DemoScenario, string> = {
  J1: "benign",
  J2: "payee_hijack",
  J3: "fragmentation",
  J4: "fault",
};

export async function runDemo(body: {
  scenario: DemoScenario;
  arm: Arm;
}): Promise<DemoRunResult> {
  const journey = DEMO_JOURNEY[body.scenario];
  if (!journey) {
    throw new ApiError(`no demo journey mapped for ${body.scenario}`, 400, null);
  }
  // The API takes {journey, mode}; the console speaks {scenario, arm}. Translate
  // here rather than at each call site — sending the console's own vocabulary was
  // a silent 422 on every demo button.
  return apiFetch("/v1/demo/run", {
    method: "POST",
    body: JSON.stringify({ journey, mode: body.arm }),
  });
}

export async function getProof(id: string): Promise<DivergenceProof> {
  // Endpoint wraps as {ok, proof_id, document}; the viewer wants the document.
  const raw = await apiFetch<
    DivergenceProof | { ok?: boolean; proof_id?: string; document?: DivergenceProof }
  >(`/v1/proofs/${encodeURIComponent(id)}`);
  if (raw && typeof raw === "object" && "document" in raw && raw.document) {
    return raw.document as DivergenceProof;
  }
  return raw as DivergenceProof;
}

export async function verifyProof(
  proof: DivergenceProof | Record<string, unknown>,
): Promise<VerifyResult> {
  // POST /v1/verify expects {document: <proof>}; posting the bare proof was a 422.
  return apiFetch("/v1/verify", {
    method: "POST",
    body: JSON.stringify({ document: proof }),
  });
}

export async function getBenchSummary(): Promise<BenchSummary> {
  // The endpoint wraps its payload as {ok, source, metrics}. Reading the wrapper
  // as the summary made every tile render an em-dash even with a finished run.
  const raw = await apiFetch<
    BenchSummary | { ok?: boolean; source?: string; metrics?: BenchSummary }
  >("/v1/bench/summary");
  if (raw && typeof raw === "object" && "metrics" in raw && raw.metrics) {
    return { ...raw.metrics, source: raw.source };
  }
  return raw as BenchSummary;
}

export async function healthz(): Promise<{ status?: string }> {
  return apiFetch("/healthz");
}

export async function getDashboardSummary(): Promise<DashboardSummary> {
  const raw = await apiFetch<DashboardSummary | { ok?: boolean }>(
    "/v1/dashboard/summary",
  );
  return raw as DashboardSummary;
}

export async function getGraphSnapshot(episodeId?: string | null): Promise<{
  nodes: import("./graph").GraphNode[];
  edges: import("./graph").GraphEdge[];
  episode?: Record<string, unknown> | null;
}> {
  const q = episodeId ? `?episode_id=${encodeURIComponent(episodeId)}` : "";
  return apiFetch(`/v1/graph/snapshot${q}`);
}

export async function planGraphPrompt(
  text: string,
  episodeId?: string | null,
): Promise<{
  plan: {
    intent: string;
    journey?: string;
    utterance?: string;
    label?: string;
    compare?: boolean;
  };
}> {
  return apiFetch("/v1/graph/prompt", {
    method: "POST",
    body: JSON.stringify({ text, episode_id: episodeId ?? null }),
  });
}

export async function checkoutEpisode(
  episodeId: string,
  amountPaise = 54_000,
): Promise<DemoRunResult> {
  return apiFetch(`/v1/episodes/${encodeURIComponent(episodeId)}/checkout`, {
    method: "POST",
    body: JSON.stringify({ amount_paise: amountPaise, human_confirmed: true }),
  });
}

export async function listProofs(): Promise<
  Array<{
    proof_id: string;
    episode_id?: string;
    created_at?: string;
    verdict?: string;
    rule_id?: string | null;
  }>
> {
  const raw = await apiFetch<
    | { proofs?: Array<{ proof_id: string; episode_id?: string; created_at?: string; verdict?: string; rule_id?: string | null }> }
    | Array<{ proof_id: string }>
  >("/v1/proofs");
  if (Array.isArray(raw)) return raw;
  return raw.proofs ?? [];
}

export async function getSettingsStatus(): Promise<SettingsStatus> {
  return apiFetch("/v1/settings/status");
}

export type OperatorStatus = {
  ok?: boolean;
  ollama?: {
    ok?: boolean;
    host?: string;
    model?: string;
    models?: string[];
    has_model?: boolean;
    error?: string;
  };
  tools?: string[];
  money_tools?: string[];
  note?: string;
};

export type OperatorTrace = {
  name: string;
  args?: Record<string, unknown>;
  status?: string;
  result?: unknown;
};

export type OperatorPending = {
  approval_id: string;
  tool: string;
  args?: Record<string, unknown>;
  reason?: string;
};

export type OperatorChatResult = {
  ok?: boolean;
  reply: string;
  used_ollama?: boolean;
  model?: string;
  tool_trace?: OperatorTrace[];
  pending_approval?: OperatorPending | null;
  episode_id?: string | null;
  highlight?: string | null;
};

export async function operatorStatus(): Promise<OperatorStatus> {
  return apiFetch("/v1/operator/status");
}

export async function operatorChat(body: {
  message: string;
  episode_id?: string | null;
  auto_approve?: boolean;
  history?: Array<{ role: string; content: string }>;
}): Promise<OperatorChatResult> {
  return apiFetch("/v1/operator/chat", {
    method: "POST",
    body: JSON.stringify({
      message: body.message,
      episode_id: body.episode_id ?? null,
      auto_approve: Boolean(body.auto_approve),
      history: body.history ?? [],
    }),
  });
}

export async function approveOperator(
  approvalId: string,
  approved: boolean,
): Promise<{
  ok?: boolean;
  status?: string;
  tool?: string;
  result?: Record<string, unknown>;
  episode_id?: string | null;
  highlight?: string | null;
}> {
  return apiFetch("/v1/operator/approve", {
    method: "POST",
    body: JSON.stringify({ approval_id: approvalId, approved }),
  });
}

export async function pingLlm(
  provider: "gemini" | "anthropic",
): Promise<PingLlmResult> {
  return apiFetch("/v1/settings/ping-llm", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

export async function testRazorpay(body?: {
  key_id?: string;
  key_secret?: string;
}): Promise<RazorpayTestResult> {
  return apiFetch("/v1/integrations/razorpay/test", {
    method: "POST",
    body: JSON.stringify(body ?? {}),
  });
}

export async function getIntegrationsGuide(): Promise<IntegrationsGuide> {
  return apiFetch("/v1/integrations/guide");
}

export async function narrateProof(id: string): Promise<NarrateResult> {
  return apiFetch(`/v1/proofs/${encodeURIComponent(id)}/narrate`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function confirmEscalation(
  episodeId: string,
  body: {
    approved?: boolean;
    decision_id?: string;
    action?: Record<string, unknown>;
    provenance?: Record<string, unknown> | unknown[];
  } = { approved: true },
): Promise<Record<string, unknown>> {
  return apiFetch(`/v1/episodes/${encodeURIComponent(episodeId)}/confirm`, {
    method: "POST",
    body: JSON.stringify({
      approved: body.approved ?? true,
      decision_id: body.decision_id,
      action: body.action,
      provenance: body.provenance,
    }),
  });
}

/** Fire baseline + Pramana demos in parallel for side-by-side compare. */
export async function runDemoCompare(scenario: DemoScenario): Promise<{
  baseline: DemoRunResult;
  pramana: DemoRunResult;
}> {
  const [baseline, pramana] = await Promise.all([
    runDemo({ scenario, arm: "baseline" }),
    runDemo({ scenario, arm: "pramana" }),
  ]);
  return { baseline, pramana };
}

/** Ordered authorize steps from a demo payload (authorize, authorize_1, …). */
export function extractAuthorizeSteps(
  result: DemoRunResult | Record<string, unknown> | null | undefined,
): Array<{
  key: string;
  index: number;
  verdict?: string;
  rule_id?: string | null;
  decision_id?: string | null;
  proof_id?: string | null;
  action?: Record<string, unknown>;
  amount_paise?: number;
  merchant_id?: string;
  execution?: Record<string, unknown> | null;
  raw: Record<string, unknown>;
}> {
  if (!result || typeof result !== "object") return [];
  const keys = Object.keys(result)
    .filter((k) => k === "authorize" || /^authorize_\d+$/.test(k))
    .sort((a, b) => {
      if (a === "authorize") return -1;
      if (b === "authorize") return 1;
      return a.localeCompare(b, undefined, { numeric: true });
    });

  return keys.map((key, i) => {
    const raw = (result as Record<string, unknown>)[key];
    const step =
      raw && typeof raw === "object"
        ? (raw as Record<string, unknown>)
        : {};
    const action =
      step.action && typeof step.action === "object"
        ? (step.action as Record<string, unknown>)
        : undefined;
    const payee =
      action?.payee && typeof action.payee === "object"
        ? (action.payee as Record<string, unknown>)
        : undefined;
    const execKey =
      key === "authorize" ? "execution" : key.replace("authorize", "execution");
    const executionRaw = (result as Record<string, unknown>)[execKey];
    const execution =
      executionRaw && typeof executionRaw === "object"
        ? (executionRaw as Record<string, unknown>)
        : null;
    const proofObj =
      step.proof && typeof step.proof === "object"
        ? (step.proof as Record<string, unknown>)
        : null;
    const executed =
      proofObj?.executed_action && typeof proofObj.executed_action === "object"
        ? (proofObj.executed_action as Record<string, unknown>)
        : null;
    const amount =
      typeof action?.amount_paise === "number"
        ? action.amount_paise
        : typeof step.amount_paise === "number"
          ? step.amount_paise
          : typeof executed?.amount_paise === "number"
            ? executed.amount_paise
            : undefined;

    return {
      key,
      index: i + 1,
      verdict: typeof step.verdict === "string" ? step.verdict : undefined,
      rule_id:
        typeof step.rule_id === "string"
          ? step.rule_id
          : step.rule_id == null
            ? null
            : String(step.rule_id),
      decision_id:
        typeof step.decision_id === "string" ? step.decision_id : null,
      proof_id: typeof step.proof_id === "string" ? step.proof_id : null,
      action,
      amount_paise: amount,
      merchant_id:
        typeof payee?.merchant_id === "string"
          ? payee.merchant_id
          : undefined,
      execution,
      raw: step,
    };
  });
}

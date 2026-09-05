export type Arm = "baseline" | "pramana";
export type Verdict = "ADMIT" | "ESCALATE" | "DENY" | "PASS" | "FAIL" | string;

/** The four journeys the API implements (see core/api/demo_journeys.py). */
export type DemoScenario = "J1" | "J2" | "J3" | "J4";

export interface ApiKeys {
  gemini: string;
  anthropic: string;
  razorpayKeyId: string;
  razorpayKeySecret: string;
}

export interface RuleTraceEntry {
  rule_id: string;
  name?: string;
  verdict: Verdict;
  expected?: string;
  actual?: string;
  inputs?: Record<string, unknown>;
  pass?: boolean;
}

export interface EnvelopeConstraints {
  merchants_allow?: string[];
  merchants_deny?: string[];
  categories_allow?: string[];
  episode_total_max_paise?: number;
  per_txn_max_paise?: number;
  max_transactions?: number;
  max_distinct_payees?: number;
  confirm_above_paise?: number;
  allowed_instruments?: string[];
  delivery_address_hash?: string;
  currency?: string;
  [key: string]: unknown;
}

export interface Envelope {
  /** Limits live here (docs/05-PROTOCOL-SPEC.md §2.1), not at the top level. */
  constraints?: EnvelopeConstraints;
  merchants_allow?: string[];
  episode_total_max_paise?: number;
  per_txn_max_paise?: number;
  max_transactions?: number;
  items?: unknown[];
  confirm_above_paise?: number;
  instrument?: string;
  expires_at?: string;
  ttl_seconds?: number;
  [key: string]: unknown;
}

export interface LedgerState {
  spent_paise?: number;
  exposure_paise?: number;
  cap_paise?: number;
  episode_total_max_paise?: number;
  committed_paise?: number;
  held_paise?: number;
  txn_count?: number;
  max_transactions?: number;
  /** The API returns the merchant ids, not a count. */
  distinct_payees?: string[] | number;
  status?: string;
  [key: string]: unknown;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  taint?: string;
}

export interface EpisodeSummary {
  episode_id: string;
  created_at?: string;
  status?: string;
  arm?: Arm | string;
  utterance?: string;
  verdict?: Verdict;
  spent_paise?: number;
  cap_paise?: number;
  proof_id?: string | null;
  decision_chain_head?: string | null;
  context_ledger_head?: string | null;
}

export interface EpisodeDetail {
  episode_id: string;
  status?: string;
  arm?: Arm | string;
  utterance?: string;
  envelope?: Envelope;
  sealed_intent?: { envelope?: Envelope; [key: string]: unknown };
  ledger?: LedgerState;
  messages?: ChatMessage[];
  rule_trace?: RuleTraceEntry[];
  last_verdict?: Verdict;
  proof_id?: string | null;
  decisions?: Array<{
    decision_id?: string;
    verdict?: Verdict;
    rule_trace?: RuleTraceEntry[];
    [key: string]: unknown;
  }>;
  [key: string]: unknown;
}

export interface CausalStep {
  step?: number;
  ledger_idx?: number;
  tool?: string;
  source_uri?: string;
  taint?: string;
  excerpt?: string;
  span?: [number, number];
  excerpt_sha?: string;
  determined_fields?: string[];
  detector?: { flagged?: boolean; signature?: string };
  injected?: boolean;
  full_text?: string;
}

export interface DivergenceProof {
  dvp_id?: string;
  dvp_version?: string;
  issued_at?: string;
  episode?: { episode_id?: string; mode?: string; [key: string]: unknown };
  sealed_intent?: {
    envelope?: Envelope;
    seal_verified?: boolean;
    [key: string]: unknown;
  };
  executed_action?: {
    kind?: string;
    amount_paise?: number;
    currency?: string;
    payee?: { merchant_id?: string; account_ref?: string };
    [key: string]: unknown;
  };
  verdict?: Verdict;
  violated_predicates?: Array<{
    rule_id?: string;
    name?: string;
    expected?: string;
    actual?: string;
  }>;
  rule_trace?: RuleTraceEntry[];
  causal_chain?: CausalStep[];
  episode_ledger_snapshot?: LedgerState;
  signature?: { alg?: string; kid?: string; sig?: string };
  [key: string]: unknown;
}

export interface FamilyAsr {
  family: string;
  label?: string;
  baseline_asr: number;
  pramana_asr: number;
  n?: number;
  baseline_display?: string;
  pramana_display?: string;
  note?: string | null;
}

export interface BenchSummary {
  /** "reports" = measured run on disk, "db" = stored run, "mock" = placeholder. */
  source?: string;
  corpus_version?: string;
  corpus_hash?: string;
  n_episodes?: number;
  n_attack?: number;
  n_benign?: number;
  shopper_mode?: string;
  run_kind?: string;
  asr_by_family?: FamilyAsr[];
  asr_overall?: {
    baseline?: number | null;
    pramana?: number | null;
    baseline_display?: string | null;
    pramana_display?: string | null;
  };
  utility?: {
    benign_completion?: number;
    false_escalation?: number;
    false_denial?: number;
    taps?: number;
    rupees_prevented?: number;
  };
  latency?: {
    p50_ms?: number;
    p95_ms?: number;
    p99_ms?: number;
  };
  sample_proofs?: Array<{ family: string; proof_id: string; episode_id?: string }>;
  known_weaknesses?: string[];
  [key: string]: unknown;
}

export interface VerifyResult {
  accept?: boolean;
  accepted?: boolean;
  ok?: boolean;
  /** API field name for the failing verifier step. */
  check?: string | null;
  /** Legacy alias some clients used; prefer `check`. */
  failing_check?: string | null;
  message?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface DemoRunResult {
  episode_id?: string;
  proof_id?: string | null;
  arm?: Arm | string;
  scenario?: string;
  status?: string;
  utterance?: string;
  messages?: ChatMessage[];
  envelope?: Envelope;
  ledger?: LedgerState;
  rule_trace?: RuleTraceEntry[];
  verdict?: Verdict;
  rule_id?: string | null;
  narrative?: string;
  proof?: DivergenceProof | null;
  [key: string]: unknown;
}

export interface DashboardRecentEpisode {
  episode_id: string;
  status?: string;
  arm?: Arm | string;
  verdict?: Verdict;
  spent_paise?: number;
  proof_id?: string | null;
  created_at?: string;
  utterance?: string;
}

export interface DashboardSummary {
  ok?: boolean;
  generated_at?: string;
  health?: {
    ok?: boolean;
    mock?: boolean;
    mode?: string;
    ephemeral_keys?: boolean;
  };
  episodes?: {
    total?: number;
    open?: number;
    frozen?: number;
    quarantined?: number;
    closed?: number;
  };
  decisions?: {
    admit?: number;
    deny?: number;
    escalate?: number;
    last_24h?: number;
  };
  money?: {
    captured_paise?: number;
    held_paise?: number;
    denied_intended_paise?: number;
  };
  proofs?: {
    count?: number;
    last_id?: string | null;
  };
  charts?: {
    episode_volume?: Array<{ day: string; count: number }>;
    verdict_mix?: Array<{ key: string; label: string; count: number }>;
    money_split?: Array<{ key: string; label: string; paise: number }>;
  };
  recent?: DashboardRecentEpisode[];
  bench?: {
    source?: string;
    overall_asr_baseline?: number | null;
    overall_asr_pramana?: number | null;
    asr_by_family?: FamilyAsr[];
    shopper_mode?: string | null;
    latency_p95_ms?: number | null;
    baseline_display?: string | null;
    pramana_display?: string | null;
  };
  [key: string]: unknown;
}

export interface SettingsStatus {
  ok?: boolean;
  mock_mode?: boolean;
  env?: string;
  razorpay?: {
    configured?: boolean;
    key_id_prefix?: string | null;
    test_mode?: boolean;
    live_refused_guard?: boolean;
  };
  llm?: {
    gemini_configured?: boolean;
    anthropic_configured?: boolean;
    sealer_mode?: "mock" | "gemini" | "anthropic" | string;
  };
  keys?: {
    seal_kid?: string | null;
    proof_kid?: string | null;
    ephemeral?: boolean;
  };
  jwks_url?: string;
  operator?: {
    host?: string;
    model?: string;
    note?: string;
  };
  note?: string;
  [key: string]: unknown;
}

export interface PingLlmResult {
  ok?: boolean;
  provider?: string;
  status_code?: number;
  snippet?: string;
  error?: string;
  [key: string]: unknown;
}

export interface RazorpayTestResult {
  ok?: boolean;
  mode?: string;
  message?: string;
  status_code?: number;
  error?: string;
  [key: string]: unknown;
}

export interface IntegrationsGuide {
  ok?: boolean;
  title?: string;
  architecture?: string;
  clone_local?: string[] | string;
  steps?: string[];
  curl?: string | Record<string, string>;
  python?: string | Record<string, string>;
  snippets?: {
    curl?: string | Record<string, string>;
    python?: string | Record<string, string>;
  };
  notes?: string[];
  deny_is_http_200?: boolean;
  razorpay?: {
    amount_unit?: string;
    test_only?: boolean;
  };
  [key: string]: unknown;
}

export interface NarrateResult {
  ok?: boolean;
  proof_id?: string;
  narrative?: string;
  source?: "llm" | "template" | string;
  provider?: string | null;
  [key: string]: unknown;
}

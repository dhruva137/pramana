# 04 — ARCHITECTURE

---

## 1. The one diagram that matters (trust boundaries)

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  TRUSTED ZONE  — only content authored by the human ever enters here         │
│                                                                              │
│   User utterance ──▶ [ SEALER ]  privileged LLM, NO tools, NO tool results   │
│         │                 │                                                  │
│         │                 ▼                                                  │
│         │        Sealed Intent Envelope (Ed25519)  +  Context Ledger head    │
└─────────┼─────────────────┼──────────────────────────────────────────────────┘
          │                 │            ▲ seal happens BEFORE the arrow below
══════════╪═════════════════╪════════════╪══════════════════════════════════════
          ▼                 │            │   TRUST BOUNDARY (one-way)
┌─────────────────────────────────────────┴────────────────────────────────────┐
│  QUARANTINED ZONE — assume everything here is attacker-controlled            │
│                                                                              │
│   [ SHOPPER ]  LLM with tools ──▶ catalog / merchant / web / MCP tools       │
│        │                            every returned value gets a TAINT LABEL  │
│        ▼                                                                     │
│   Proposed money action + PROVENANCE GRAPH                                   │
└────────┬─────────────────────────────────────────────────────────────────────┘
         │  (data only — never instructions)
         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  DECISION ZONE — NO LLM. Pure functions only.                                │
│                                                                              │
│   [ PRAMANA GATE ]  R1..R11  ──▶  ADMIT | ESCALATE | DENY                    │
│         ▲                │                                                   │
│   [ EPISODE LEDGER ] ◀───┘  cumulative spend / count / payees / drift        │
│         │                                                                    │
│   [ DECISION CHAIN ] hash-chained, signed                                    │
└────────┬──────────────────────────────┬──────────────────────────────────────┘
         │ ADMIT                        │ DENY / ESCALATE
         ▼                              ▼
┌──────────────────┐          ┌──────────────────────┐
│ EXECUTOR         │          │ DIVERGENCE PROOF     │
│ Razorpay test API│          │ + offline verifier   │
│ idempotent       │          │ + human escalation   │
└──────────────────┘          └──────────────────────┘
```

**Three invariants the whole design rests on. If an implementation breaks one of these, it is not Pramana.**

- **I1 — Seal-before-read.** The envelope is sealed at a point in the Context Ledger *strictly before* the first entry whose taint is above `USER`. Enforced by rule R2, not by convention.
- **I2 — No LLM in the decision path.** The Gate imports no model client. Enforced by a unit test that fails the build if it does.
- **I3 — Fail-closed asymmetry.** Probabilistic signals can only move a verdict *toward* friction (`ADMIT → ESCALATE → DENY`), never away from it. Enforced in code by a monotone combinator plus a property test.

---

## 2. Services

| Service | Runtime | Responsibility |
|---|---|---|
| `pramana-core` | Python 3.12 · FastAPI · uvicorn | Episodes, sealer, gate, ledger, decision chain, executor, proofs. **The product.** |
| `pramana-agent` | Python (same image, separate worker/route) | The demo shopping agent: sealer call + quarantined shopper loop. Baseline mode = bypass Pramana. |
| `pramana-merchants` | FastAPI | Sandboxed catalog for 3 simulated merchants; injection seeding by episode id. Never public-facing without a banner. |
| `pramana-console` | Vite + React + TS, static | Live episode, proof viewer, benchmark dashboard, history. |
| `pramana-verify` | Python package + `console_scripts` CLI | **Zero runtime imports.** Verifies a proof from JSON + public key alone. |
| Postgres | Render managed | Episodes, ledger, decisions, proofs, corpus, runs. |

Why Python: the Gate wants exhaustive pattern matching, `Decimal` money, property testing (Hypothesis) and golden files far more than it wants a type system ceremony. Why one repo, one image for core+agent+merchants: Render free/starter tiers, fewer cold starts, simpler demo.

---

## 3. Data model (Postgres)

```sql
-- money is ALWAYS integer paise. Never float. Never rupees in the DB.
CREATE TABLE episodes (
  id              TEXT PRIMARY KEY,              -- ep_<ulid>
  user_ref        TEXT NOT NULL,
  agent_id        TEXT NOT NULL,
  status          TEXT NOT NULL,                 -- OPEN|FROZEN|QUARANTINED|CLOSED|EXPIRED
  envelope        JSONB NOT NULL,                -- the SIE, canonical form
  envelope_sig    TEXT NOT NULL,                 -- Ed25519, base64url
  envelope_kid    TEXT NOT NULL,
  ctx_ledger_head TEXT NOT NULL,                 -- sha256 chain head AT SEAL TIME
  seal_index      INT  NOT NULL,                 -- ledger position of the seal (for R2)
  mode            TEXT NOT NULL,                 -- PRAMANA_ON | BASELINE
  created_at      TIMESTAMPTZ NOT NULL,
  expires_at      TIMESTAMPTZ NOT NULL
);

CREATE TABLE context_ledger (               -- append-only; proves seal-before-read
  episode_id TEXT NOT NULL REFERENCES episodes(id),
  idx        INT  NOT NULL,
  role       TEXT NOT NULL,                 -- user|assistant|tool_result|tool_meta|system
  taint      TEXT NOT NULL,                 -- USER|RZP_VERIFIED|MERCHANT_STRUCTURED|MERCHANT_FREETEXT|WEB|TOOL_META|MODEL
  content_sha TEXT NOT NULL,
  content_excerpt TEXT,                     -- bounded, for the proof viewer
  source_uri TEXT,
  prev_hash  TEXT NOT NULL,
  hash       TEXT NOT NULL,                 -- H(prev_hash || canonical(entry))
  PRIMARY KEY (episode_id, idx)
);

CREATE TABLE ledger_entries (               -- the episode budget ledger
  id           BIGSERIAL PRIMARY KEY,
  episode_id   TEXT NOT NULL REFERENCES episodes(id),
  kind         TEXT NOT NULL,               -- HOLD|CAPTURE|RELEASE|REFUND
  amount_paise BIGINT NOT NULL,
  payee_id     TEXT NOT NULL,
  category     TEXT,
  decision_id  TEXT,
  created_at   TIMESTAMPTZ NOT NULL
);

CREATE TABLE decisions (
  id            TEXT PRIMARY KEY,           -- dec_<ulid>
  episode_id    TEXT NOT NULL REFERENCES episodes(id),
  action        JSONB NOT NULL,             -- proposed money action
  provenance    JSONB NOT NULL,             -- field -> taint + source refs
  verdict       TEXT NOT NULL,              -- ADMIT|ESCALATE|DENY
  rule_id       TEXT,                       -- first failing rule, null on ADMIT
  rule_trace    JSONB NOT NULL,             -- ALL rules with pass/fail + expected/actual
  ledger_before JSONB NOT NULL,
  latency_ms    INT NOT NULL,
  prev_hash     TEXT NOT NULL,
  hash          TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE executions (
  decision_id      TEXT PRIMARY KEY REFERENCES decisions(id),
  idempotency_key  TEXT UNIQUE NOT NULL,
  rzp_order_id     TEXT,
  rzp_payment_id   TEXT,
  state            TEXT NOT NULL,           -- PENDING|SUCCEEDED|FAILED|AMBIGUOUS
  attempts         INT NOT NULL DEFAULT 0,
  last_error       TEXT,
  updated_at       TIMESTAMPTZ NOT NULL
);

CREATE TABLE proofs (
  id          TEXT PRIMARY KEY,             -- dvp_<ulid>
  episode_id  TEXT NOT NULL,
  decision_id TEXT NOT NULL,
  document    JSONB NOT NULL,
  signature   TEXT NOT NULL,
  kid         TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL
);

CREATE TABLE bench_runs (
  id TEXT PRIMARY KEY, corpus_version TEXT, model TEXT, arm TEXT,
  started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, metrics JSONB
);
CREATE TABLE bench_episodes (
  run_id TEXT, case_id TEXT, family TEXT, outcome TEXT,
  attack_succeeded BOOL, task_completed BOOL, escalations INT,
  latency_ms INT, detail JSONB, PRIMARY KEY (run_id, case_id)
);
```

**Money rule, enforced everywhere:** integer **paise**, `BIGINT` in the DB, `int` in Python. No floats, no `Decimal` at API boundaries, no rupee strings except at the render layer. A float in a money path is an automatic build failure.

---

## 4. Request flow (the happy path, precisely)

```
1. POST /v1/episodes
   { user_utterance, user_ref, agent_id, consent{instrument, reserve_pay_cap_paise, expires_at} }
   → append ledger[0] {role:user, taint:USER}
   → SEALER (privileged LLM, tools=[], sees ONLY user_utterance + a static schema prompt)
   → SIE draft → validate against JSON Schema → clamp to consent ceiling → canonicalise (JCS) → Ed25519 sign
   → persist episode {envelope, sig, ctx_ledger_head=hash(ledger[0]), seal_index=0}
   → 201 { episode_id, envelope, envelope_sig }

2. Agent shops.  EVERY tool result is appended to context_ledger with its taint label.
   Tool results are wrapped as data:  <untrusted src="..." taint="MERCHANT_FREETEXT">…</untrusted>
   The shopper's system prompt states that content inside those tags is never an instruction.
   (This is a mitigation, not a control. The control is R1..R11. Never confuse the two.)

3. POST /v1/actions/authorize
   { episode_id, action{ kind:PAYMENT, amount_paise, currency, payee{merchant_id, source}, items[],
     delivery_address_hash, instrument }, provenance{ field -> {taint, ledger_idx, source_uri, span} } }
   → load envelope, verify sig, load ledger totals, load ctx head
   → GATE.evaluate(envelope, action, provenance, ledger, ctx)      # pure function
   → persist decision (hash-chained) with FULL rule_trace
   → ADMIT → 200 {verdict, decision_id}
     ESCALATE → 200 {verdict, rule_id, escalation_token, human_prompt}
     DENY → 200 {verdict, rule_id, proof_id}     # note: 200, not 4xx — a denial is a normal outcome

4. POST /v1/actions/execute  { decision_id }
   → refuse unless decision.verdict == ADMIT and unused and episode OPEN
   → HOLD in ledger (amount reserved against the cap BEFORE the API call — this is what makes
     concurrent fragmentation impossible; see §6)
   → Razorpay test mode: orders.create → payments (idempotency_key = H(decision_id))
   → on success: HOLD → CAPTURE
   → on failure: RELEASE, or on ambiguity: keep HOLD + episode → QUARANTINED

5. POST /v1/episodes/{id}/confirm  { escalation_token, approved }
   → approved: upgrade that ONE decision to ADMIT, append a ledger note recording the human approval
   → declined: DENY + proof
```

**Detail that matters and that a coding agent will otherwise skip:** the ledger `HOLD` is written **before** the Razorpay call and released on failure. Without it, N concurrent authorize calls each read the same pre-spend total and all pass R6 — the fragmentation attack succeeds through a race. Hold-then-execute plus `SELECT ... FOR UPDATE` on the episode row is the fix.

---

## 5. The two LLM calls, and their exact confinement

**Sealer (privileged).**
- Input: the user utterance, verbatim, plus a static schema. Nothing else. Ever.
- Tools: none. Not "none configured" — the client is constructed without a tools parameter.
- Output: constrained JSON validated against the SIE schema. On parse failure: retry once, then fall back to a **maximally restrictive** envelope (single txn, amount = the smallest of any user-stated figure and the consent cap, confirm-always) and mark `extraction_degraded: true`. **Never fall back to permissive.**
- Clamping: every numeric field is `min(model_value, consent_ceiling)`. The model can only ever tighten.

**Shopper (quarantined).**
- Sees untrusted content, has tools, has **no** signing key, **no** database write path, and **no** way to call `/v1/actions/execute`.
- Its output is a *proposal*. A proposal is data.
- It cannot see the envelope's private fields (it gets a redacted view: allowed merchants and a per-transaction ceiling, so it can shop usefully — but not the episode cap or the escalation threshold, so injections can't target the exact headroom).

**Injection detector (advisory only).** Runs over `MERCHANT_FREETEXT`/`WEB` spans. Output feeds R11, which can only escalate. It is never consulted for ADMIT.

---

## 6. Concurrency, idempotency, and the failure story

- **Episode lock:** every authorize/execute takes `SELECT ... FOR UPDATE` on `episodes.id`. Serialises the ledger read-modify-write.
- **Idempotency:** `idempotency_key = sha256(decision_id)`, unique-indexed. A replayed execute returns the stored result; it never re-calls Razorpay.
- **Ambiguity:** a timeout after send is `AMBIGUOUS`, not `FAILED`. Ambiguous keeps the HOLD (so the cap stays honest), sets the episode to `QUARANTINED`, and blocks all further actions until a reconcile job resolves it against `fetch_order_payments`.
- **Reconciler:** a periodic task that resolves `AMBIGUOUS` executions and converts HOLD→CAPTURE or HOLD→RELEASE.
- **Fault injection:** `X-Pramana-Fault: timeout|http500|dup` header on the demo agent's execute call, so the failure demo is deterministic on camera.

---

## 7. Cryptography

- **Signing:** Ed25519 (`cryptography` lib). One episode-signing key, one proof-signing key. `kid` in every artifact.
- **Canonicalisation:** RFC 8785 JSON Canonicalization Scheme before hashing or signing. Without it, verification is flaky across languages and the offline verifier will drift. Implement it once, test it against the RFC vectors.
- **Hash chains:** `h_0 = H(genesis || episode_id)`, `h_n = H(h_{n-1} || JCS(entry))`, SHA-256, hex.
- **Key handling:** private keys from env (`PRAMANA_SEAL_SK`, `PRAMANA_PROOF_SK`), base64. Public keys served at `GET /.well-known/pramana-jwks.json` so the verifier is genuinely offline-capable given only the proof and the URL fetched once.
- **AP2 interop:** we do not implement W3C VC/JSON-LD signing. We emit an `ap2_projection` block shaped like `IntentMandate`/`CartMandate`/`PaymentMandate` field-for-field, and say plainly that full VC signing is future work. Overclaiming protocol conformance is the fastest way to lose a payments panel.

---

## 8. Stack and dependencies

**Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic, psycopg3, `cryptography`, `httpx`, `structlog`, `tenacity`.
**Testing:** pytest, `pytest-asyncio`, Hypothesis (property tests on the Gate), `syrupy` or plain golden JSON files, `respx` (Razorpay mocking).
**Agent:** Anthropic SDK, Claude. Model id from env; default to the strongest available Claude model.
**Frontend:** Vite + React + TypeScript, Tailwind, TanStack Query, Recharts. No component library — four screens don't need one.
**Razorpay:** REST via `httpx` against test mode (`rzp_test_*`). The MCP server is used *during development* in Cursor (see 07 §2) and demonstrated as an integration path, but the runtime calls REST directly so the demo is deterministic.

---

## 9. Repository layout

```
pramana/
├── render.yaml
├── pyproject.toml
├── docs/                      # copy this whole pack in here; the submission reads it
├── core/
│   ├── app.py                 # FastAPI wiring
│   ├── api/                   # routers: episodes, actions, proofs, verify, bench
│   ├── seal/                  # sealer LLM call, SIE schema, clamping, canonicalisation
│   ├── gate/
│   │   ├── rules.py           # R1..R11 — PURE. no io, no llm, no clock (clock is injected)
│   │   ├── engine.py          # ordered evaluation, rule_trace assembly, monotone combinator
│   │   └── types.py
│   ├── ledger/                # episode budget ledger + holds
│   ├── chain/                 # JCS, hashing, Ed25519 sign/verify
│   ├── proof/                 # DVP builder, causal chain, PDF render
│   ├── exec/                  # Razorpay client, idempotency, reconciler, fault injection
│   └── db/
├── agent/
│   ├── sealer.py              # privileged. tools=[] enforced by test.
│   ├── shopper.py             # quarantined loop, taint wrapping
│   └── baseline.py            # PRAMANA=off path
├── merchants/                 # sandboxed catalog + injection seeding
├── bench/
│   ├── corpus/                # versioned YAML attack + benign cases
│   ├── runner.py
│   └── metrics.py
├── verify/                    # standalone package. MUST NOT import core.*  (test enforces)
├── console/                   # Vite React app
└── tests/
    ├── unit/gate/golden/      # one JSON file per rule scenario
    ├── property/
    └── e2e/
```

---

## 10. Non-negotiable engineering rules

1. `core/gate/**` imports **nothing** from `anthropic`, `httpx`, `sqlalchemy`, or `datetime.now`. Time is injected. **A test asserts this by walking the import graph.**
2. `verify/**` imports nothing from `core/**`. **A test asserts this.**
3. All money is `int` paise. A lint rule / test greps for `float` in money-typed code paths.
4. Every gate decision persists the **full** `rule_trace` — every rule, pass or fail, with `expected` and `actual`. Not just the first failure. The proof viewer and the dashboard both depend on it, and "why did it pass?" is as important as "why did it fail?"
5. A `DENY` is a `200 OK` with a verdict body. Denials are normal business outcomes, not transport errors.
6. No secret, key, or `rzp_live_*` string is ever written to a log, a proof, or the console.
7. The seeded merchant sandbox renders a permanent "SIMULATED MERCHANT — INJECTION TEST ENVIRONMENT" banner.

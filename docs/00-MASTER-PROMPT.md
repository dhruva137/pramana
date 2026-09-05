# 00 — MASTER PROMPT
### For a Cursor harness driving subagents

---

## How to use this file

1. Copy `pramana-pack/` into the repo root as `docs/`.
2. Paste **§1 (the standing prompt)** into your Cursor rules file (`.cursor/rules/pramana.mdc`) or as the persistent system context. It is written to survive compaction — it is short, it is imperative, and it names the files to re-read.
3. For each milestone, paste the corresponding **§3 milestone kickoff** as the task message.
4. Use **§4** verbatim when spawning subagents.
5. Re-paste **§2 (the invariants card)** at the start of every new session and after any context compaction. This is the single highest-leverage habit; harness drift is almost always invariant amnesia.

**Context-engineering principle behind the design:** long-context agents lose *constraints* before they lose *goals*. They will remember "build the payment gate" and forget "the gate must not import an LLM client." So the invariants are (a) short, (b) repeated, (c) restated as *tests that fail the build*, and (d) placed at the start of every kickoff. Anything you cannot express as a failing test will eventually be dropped — so express it as a failing test.

---

## §1 — THE STANDING PROMPT (paste into Cursor rules)

````
You are building PRAMANA: an intent-custody and admission-control layer that sits between an AI
shopping agent and Razorpay's payment APIs. It is a submission for the Razorpay AI Buildathon,
Track 01 (AI Growth & Agentic Commerce).

# THE ONE-SENTENCE THESIS
Agentic payment standards (AP2, Visa TAP, Mastercard Agent Pay, NPCI UAP) cryptographically prove WHO
signed a transaction, and validate each transaction against a mandate. None of them validate the
SEQUENCE of transactions against the user's intent. So a prompt injection does not need to break one
payment — it splits one large unauthorised spend into many individually-compliant small ones, and every
signature still verifies. Pramana closes this with a sealed intent envelope, provenance tracking, a
deterministic non-LLM admission gate with an EPISODE-level budget ledger, and a signed Divergence Proof.

# AUTHORITATIVE DOCS — read before acting, re-read when unsure
- docs/05-PROTOCOL-SPEC.md   NORMATIVE. Rules R1-R12, schemas, proof format. If anything conflicts with
                             another doc, this file wins.
- docs/04-ARCHITECTURE.md    Services, data model, request flow, engineering rules.
- docs/07-IMPLEMENTATION-PLAN.md  Milestones, DoD, acceptance tests, subagent ownership.
- docs/06-ADVERSARY-SUITE.md Corpus design, metrics, DEFENSE-ONLY compliance rules.
- docs/03-PRODUCT-SPEC.md    Scope, journeys, demo.
- docs/01-THESIS.md          Why. Read once; it decides ties.

# HARD INVARIANTS — violating any of these is a build failure, not a style issue
I1  SEAL BEFORE READ. The intent envelope is sealed at a context-ledger index strictly before the first
    entry with taint > USER. Enforced by rule R2 and by a test.
I2  NO LLM IN THE DECISION PATH. core/gate/** imports no model client, no HTTP client, no ORM, and never
    calls datetime.now (time is injected). Enforced by an import-graph test.
I3  FAIL-CLOSED ASYMMETRY. Probabilistic signals may only move a verdict toward friction
    (ADMIT -> ESCALATE -> DENY), never away. Enforced by a property test.
I4  MONEY IS INTEGER PAISE. No floats anywhere in a money path. Field names end in _paise.
I5  MISSING PROVENANCE = MAXIMUM TAINT. An unlabelled critical field is treated as MODEL, not as trusted.
I6  verify/** IMPORTS NOTHING FROM core/**. It re-implements R1-R12 independently. This redundancy is
    intentional; do not "refactor" it away. Enforced by a test.
I7  HOLD BEFORE EXECUTE. The episode ledger reserves the amount BEFORE the Razorpay call, under a row
    lock. Without this, concurrent authorizations race past R6 and the core defence is fake.
I8  DENY IS A 200. Verdicts are business outcomes, not transport errors.
I9  TEST MODE ONLY. The process refuses to boot unless RAZORPAY_KEY_ID starts with rzp_test_.
I10 DEFENSE ONLY. Fixed handwritten attack corpus, executed only against our bundled simulated-merchant
    service. No attack generator, no fuzzer, no evasion research, no third-party targets. See
    docs/06-ADVERSARY-SUITE.md §9 before writing any adversarial content.

# BUILD ORDER — do not reorder
M0 skeleton+CI+Render deploy -> M1 chain primitives -> M2 adversary corpus + runner + BASELINE arm ->
M3 sealer+envelope -> M4 the gate -> M5 ledger+executor+failures -> M6 proof+verifier -> M7 console ->
M8 benchmark run+report+docs.
M2 COMES BEFORE M4 ON PURPOSE. Building the defence first would make the corpus a description of what
the defence already stops. Do not "optimise" this ordering.

# WORKING RULES
- Every behaviour ships with a test that would FAIL if the behaviour were removed. Smoke tests do not count.
- Append one line to docs/FAILURES.md whenever something breaks: symptom, root cause, fix. Write it as it
  happens. This file is a scored deliverable, not housekeeping.
- Do not add dependencies not named in docs/04-ARCHITECTURE.md §8 without saying why.
- Do not widen scope. docs/03-PRODUCT-SPEC.md §3.2 lists what we are deliberately NOT building.
- Do not weaken the baseline arm to make results look better. The baseline gets a real signed mandate and
  real per-transaction validation.
- When the spec is ambiguous, implement the MORE RESTRICTIVE reading and note it in a code comment.
- Prefer boring code. This is a security control that must be auditable by a stranger in ten minutes.
````

---

## §2 — THE INVARIANTS CARD (re-paste after every compaction)

````
PRAMANA INVARIANTS — check the diff against these before you continue.
I1 seal before read (R2)              I6 verify/ isolated from core/
I2 no LLM/IO/clock in core/gate/      I7 HOLD before execute, under a row lock
I3 probabilistic signals escalate only I8 DENY = HTTP 200
I4 integer paise, no floats            I9 rzp_test_ keys only, asserted at boot
I5 missing provenance = MODEL taint    I10 defense-only corpus, sandbox targets only
Normative source of truth: docs/05-PROTOCOL-SPEC.md
Build order: M2 (corpus+baseline) BEFORE M4 (gate).
Current milestone: <FILL IN>.  Files I own this session: <FILL IN>.
````

---

## §3 — MILESTONE KICKOFFS

Paste the invariants card, then the block below.

### M0
> Set up the repo exactly as in `docs/04-ARCHITECTURE.md` §9. FastAPI app with `/healthz`, Alembic baseline against the schema in §3, pytest + ruff, a GitHub Actions workflow, and `render.yaml` per `docs/08-DEPLOY-RENDER.md`. Add the boot assertions from 08 §3. Deploy to Render and give me the live `/healthz` URL. Do not write any product logic yet.

### M1
> Implement `core/chain/`: RFC 8785 JSON Canonicalization, `sha256_hex`, Ed25519 sign/verify, and a hash-chain builder. Include the RFC 8785 test vectors as fixtures — do not hand-roll canonicalisation and assume it's right. Acceptance tests are in `docs/07-IMPLEMENTATION-PLAN.md` §3/M1. Nothing else this milestone.

### M2
> **Read `docs/06-ADVERSARY-SUITE.md` in full first, especially §9 (defense-only compliance).**
> Build, in this order: (1) `merchants/` — a sandboxed catalog service for three simulated merchants plus one hostile merchant, with per-episode injection seeding and a permanent "SIMULATED MERCHANT — INJECTION TEST ENVIRONMENT" banner; (2) `bench/corpus/` — 60 benign cases and ≥68 attack cases across the eight families, in the YAML format in §2.1, with every payload in its own file carrying the defensive-fixture header; (3) `agent/baseline.py` — the Arm A agent with a real AP2-shaped signed mandate validated per transaction (merchant in list, amount ≤ per-txn cap, signature valid, not expired) and no episode ledger; (4) `bench/runner.py` and `bench/metrics.py`.
> Then run the baseline arm over the whole corpus and show me the report.
> **The baseline must be a fair, competent implementation of what the industry ships today. Do not cripple it.** Expect and want a high attack success rate on the fragmentation family — that is the finding.
> Commit `CORPUS.sha256` and seal the 30% held-out split.

### M3
> Implement the Sealed Intent Envelope exactly per `docs/05-PROTOCOL-SPEC.md` §2 — schema, sealing procedure, clamping, restrictive fallback, context ledger, and `POST /v1/episodes` + `POST /v1/episodes/{id}/context`.
> The sealer LLM client is constructed **without tools** and sees **only** the user utterance plus a static schema prompt. Write the test that asserts no `tools` key reaches the API.
> Extraction failure must produce the restrictive fallback in §2.3 — never a permissive default. Every numeric constraint is clamped to the consent ceiling.

### M4
> **This is the product. Implement `docs/05-PROTOCOL-SPEC.md` §4 exactly — R1 through R12, in order, with the monotone combinator in §4.1 and the full `rule_trace` in §4.2 emitted for every rule whether it passes or fails.**
> `evaluate(envelope, action, provenance, ledger_state, ctx_ledger, now) -> Decision` is a **pure function**. Write the import-graph test that fails the build if `core/gate/**` imports `anthropic`, `httpx`, `sqlalchemy` or `requests`, or calls `datetime.now`/`time.time`.
> Golden files: at least one passing and one failing case per rule, committed as JSON.
> Property tests with Hypothesis: (a) monotonicity of the combinator; (b) **ledger soundness — for any sequence of admitted actions, the sum of amounts never exceeds `episode_total_max_paise`**; (c) determinism.
> Branch coverage of `rules.py` must be 100%.

### M5
> Implement the episode ledger (HOLD/CAPTURE/RELEASE/REFUND), the Razorpay test-mode executor, idempotency, `AMBIGUOUS` handling, the reconciler, the `X-Pramana-Fault` injection header, and the freeze endpoint. Follow `docs/04-ARCHITECTURE.md` §4 and §6 and `docs/05-PROTOCOL-SPEC.md` §3.
> **The HOLD is written before the Razorpay call, under `SELECT … FOR UPDATE` on the episode row.** Write the concurrency test first: 10 parallel authorize+execute calls against a one-transaction envelope must yield exactly 1 capture and 9 R6 denials, and it must pass 20 consecutive runs.
> Then the fault tests: timeout → AMBIGUOUS + QUARANTINED + hold retained; 500 → RELEASE; duplicate submit → same payment id, one Razorpay call.

### M6
> Implement the Divergence Proof per `docs/05-PROTOCOL-SPEC.md` §5, including causal-chain assembly from the provenance closure, and the standalone `verify/` package + CLI.
> **`verify/` must not import anything from `core/`. It re-implements R1–R12 independently and re-executes them from the proof document. This duplication is deliberate — the verifier is only meaningful because it is an independent implementation. Do not refactor it to share code, and add the import-graph test that prevents someone doing so later.**
> The verifier must reject each of: mutated verdict, mutated envelope, mutated ledger entry, wrong kid, truncated causal chain, tampered excerpt.

### M7
> Build the console per `docs/03-PRODUCT-SPEC.md` §3.1E and `docs/06-ADVERSARY-SUITE.md` §8. Four screens: live episode (chat + sealed envelope + running ledger + per-rule verdict strip), proof viewer (sealed vs executed, violated predicate as expected→actual, causal chain with the injected span highlighted in the source text), benchmark dashboard, episode history with offline-verify.
> Add attack-launcher buttons for F1/F3/F4 and an Arm A/Arm B toggle.
> Success test: hand the URL to someone who has never seen the repo and confirm they can run all four journeys unaided.

### M8
> Run both arms on the sealed held-out split. Produce `reports/COMPARISON.md` with every metric in `docs/06-ADVERSARY-SUITE.md` §4, Wilson 95% intervals on all rates, raw counts wherever N < 20, and a "Known weaknesses" section.
> Then write the repo `README.md` (with the §9.6 scope statement verbatim), `docs/ARCHITECTURE.md`, and finish `docs/FAILURES.md`.
> **Report the numbers you got, not the numbers we predicted.** If a pre-registered expectation in §5 was wrong, say so explicitly in the report — that is worth more than a clean result.

---

## §4 — SUBAGENT SPAWN TEMPLATE

````
You are subagent <A#> on the PRAMANA build.

SCOPE — you may write ONLY these paths: <paths>
You may READ: docs/**, and <paths of upstream contracts>
You MUST NOT modify any other path. If you believe a change is needed outside your scope, stop and
report it instead of making it.

CONTRACT you expose to others:  <exact signature / schema>
CONTRACT you consume:           <exact signature / schema>

Read first, in this order: docs/05-PROTOCOL-SPEC.md §<n>, docs/04-ARCHITECTURE.md §<n>,
docs/07-IMPLEMENTATION-PLAN.md §3/<milestone>.

INVARIANTS (violation = build failure):
<paste §2 invariants card>

DEFINITION OF DONE:
<paste the milestone's acceptance tests from 07 §3>

When done, report: files changed, tests added, how each acceptance test is satisfied, anything in the
spec you found ambiguous and which reading you took (you take the MORE RESTRICTIVE reading), and any
line you added to docs/FAILURES.md.
````

---

## §5 — THE ANTI-DRIFT REVIEW PROMPT

Run this after every milestone, in a **fresh** session with no build context. A fresh reviewer catches invariant drift that the builder is blind to.

````
Review the working tree against docs/05-PROTOCOL-SPEC.md and the invariants below. You did not write this
code. Be adversarial. For each item answer PASS/FAIL with a file:line citation, and do not accept a README
claim as evidence — only code and tests count.

1  Does core/gate/** import any model client, HTTP client, ORM, or call datetime.now/time.time?
2  Is evaluate() a pure function of its arguments? Any hidden global, cache, or env read?
3  Does R2 actually verify that every context-ledger entry before seal_index has taint == USER, by
   recomputing the chain — or does it just trust a stored boolean?
4  Can any probabilistic signal produce ADMIT? Trace R11 end to end.
5  Is there a HOLD written before the Razorpay call, under a row lock? Show me the lock.
6  Find every float in a money path.
7  Does verify/ import anything from core/? Does it re-implement the rules, or call into them?
8  Is the full rule_trace persisted on PASS as well as FAIL?
9  Is JCS used before every hash and signature, or is json.dumps used anywhere?
10 Does a missing provenance record default to MODEL taint, or to trusted?
11 Is the baseline arm genuinely validating a signed mandate per transaction, or is it a strawman?
12 Was any corpus file modified after the gate was last modified? Check git log.

Then list, in priority order, every place where the implementation is weaker than the spec claims.
````

---

## §6 — WHY THIS PROMPT IS SHAPED THIS WAY

Four deliberate choices, in case you want to adapt it:

1. **Invariants are stated as build failures, not preferences.** "Should be pure" gets dropped under context pressure; "an import-graph test fails the build" survives, because the agent hits the failing test.
2. **The build order carries its own justification inline.** An agent that knows *why* M2 precedes M4 won't "helpfully" reorder; one that only knows the order will.
3. **File ownership is exclusive and named.** Overlapping write scopes are the main cause of subagent thrash and lost work.
4. **The review prompt runs in a fresh session.** An agent reviewing its own work in the same context will confirm its own assumptions. A cold reviewer with a checklist won't.

And the meta-rule: **anything you cannot express as a failing test will eventually be dropped.** When you add a requirement of your own, write its test in the same breath.

# 07 — IMPLEMENTATION PLAN
### Milestones, subagent decomposition, Definition of Done, acceptance tests

---

## 1. Build order (and why it is this order)

```
M0  Skeleton + CI + Render deploy of a hello-world      ← deploy on day 1, not day 6
M1  Chain primitives: JCS, hashing, Ed25519, verifier stub
M2  Adversary corpus + runner + BASELINE arm            ← evaluator BEFORE defence
M3  Sealer + SIE schema + context ledger
M4  Gate R1–R12 (pure) + golden tests + property tests  ← the product
M5  Episode ledger + holds + executor + idempotency + faults
M6  Divergence Proof + offline verifier package
M7  Console (live episode, proof viewer, dashboard)
M8  Full benchmark run, report, demo rehearsal, README + architecture doc
```

**M2 before M4 is the single most important sequencing decision in this plan.** See [06-ADVERSARY-SUITE.md](06-ADVERSARY-SUITE.md) §1. A coding agent left to itself will build the defence first because it's more fun. Do not let it.

**M0 deploying on day one** is the second. A Render deploy that has been green since M0 never becomes a day-6 crisis.

---

## 2. Development environment

- Python 3.12, `uv` or `pip-tools`. Node 20 for the console.
- Local Postgres via Docker; Render Postgres for deployed.
- **Razorpay MCP server in Cursor** during development — it lets the coding agent inspect real test-mode orders/payments while building, which materially reduces API-shape guesswork. Configure with `rzp_test_*` keys and `READ_ONLY=true` for exploration; the runtime itself calls REST directly (see [04-ARCHITECTURE.md](04-ARCHITECTURE.md) §8).
- `.env.example` committed; `.env` never.

---

## 3. Milestones in detail

### M0 — Skeleton, CI, first deploy
**Deliverables:** repo per [04-ARCHITECTURE.md](04-ARCHITECTURE.md) §9; FastAPI app with `/healthz`; Alembic baseline; pytest wired; GitHub Actions running lint + tests; `render.yaml`; live URL.
**DoD:** `GET https://<app>.onrender.com/healthz` returns 200 from the deployed service. CI green on a PR.

### M1 — Chain primitives
**Deliverables:** `core/chain/`: RFC 8785 JCS, `sha256_hex`, Ed25519 sign/verify, chain builder.
**DoD / acceptance:**
- JCS matches the RFC 8785 test vectors (include them as fixtures — do not hand-roll and hope).
- Property test: `verify(sign(m)) == True` for 1,000 Hypothesis-generated documents; any single-byte mutation fails.
- Chain test: recomputation over a 50-entry ledger reproduces the head; mutating entry 17 breaks it.

### M2 — Corpus + runner + baseline arm
**Deliverables:** `bench/corpus/` with all 8 families + 60 benign; `merchants/` sandbox with injection seeding; `agent/baseline.py`; `bench/runner.py`; first baseline report.
**DoD:**
- `python -m bench.runner --arm baseline` completes over the full corpus and writes a JSON report.
- Baseline ASR on F3 is high (if it isn't, the corpus is wrong — fix the corpus, not the number).
- `CORPUS.sha256` committed; held-out split sealed and its hash recorded.
- Every payload file carries the defensive-fixture header ([06](06-ADVERSARY-SUITE.md) §9.5).

### M3 — Sealer + SIE + context ledger
**Deliverables:** SIE JSON Schema; `agent/sealer.py`; clamping; restrictive fallback; `POST /v1/episodes`; `POST /v1/episodes/{id}/context`.
**DoD:**
- Test: sealer client constructed **without** tools; a test asserts `tools` is absent from the request payload.
- Test: sealing after a non-`USER` ledger entry returns `409 CONTEXT_TAINTED`.
- Test: a model output exceeding `consent_cap_paise` is clamped, and `clamped_fields` records it.
- Test: malformed model output twice → restrictive fallback with `degraded=true`, `max_transactions=1`, `confirm_above_paise=0`.
- Test: 20 utterances (incl. 5 Hinglish) produce schema-valid envelopes.

### M4 — The Gate
**Deliverables:** `core/gate/rules.py` (R1–R12), `engine.py`, monotone combinator, full `rule_trace`, golden tests, property tests.
**DoD:**
- **Import-graph test:** `core/gate/**` imports nothing from `anthropic`, `httpx`, `sqlalchemy`, `requests`, and does not call `datetime.now`/`time.time`. Fails the build if violated.
- **Golden files:** ≥ 2 per rule (one pass, one fail) as committed JSON; a diff in output requires a deliberate golden update.
- **Property tests (Hypothesis):**
  - monotonicity: `combine` never decreases restrictiveness when R11 flips to flagged;
  - **ledger soundness: for any sequence of admitted actions, `Σ amounts ≤ episode_total_max_paise`.** This is H2 proved as a property, not just observed in a benchmark — say that on camera.
  - determinism: same inputs → byte-identical `rule_trace`.
- **Branch coverage of `rules.py` = 100%.**
- Latency: p95 of `evaluate()` measured in a micro-benchmark and recorded.

### M5 — Ledger, executor, failure handling
**Deliverables:** hold/capture/release/refund; `SELECT … FOR UPDATE`; Razorpay test-mode client; idempotency; `AMBIGUOUS` handling; reconciler; `X-Pramana-Fault` injection; freeze endpoint.
**DoD:**
- **Concurrency test:** 10 parallel authorize+execute calls against a 1-transaction envelope → exactly 1 capture, 9 denials on R6. (Run it 20 times. This is where a naive implementation fails and it is the bug that would silently break the whole thesis.)
- **Idempotency test:** same `decision_id` executed twice → one Razorpay call, same payment id returned.
- **Fault tests:** `timeout` → `AMBIGUOUS` + episode `QUARANTINED` + hold retained; `http500` → `RELEASE` + hold freed; `dup` → no double charge.
- Reconciler resolves an `AMBIGUOUS` execution from `fetch_order_payments` and settles the ledger.

### M6 — Divergence Proof + offline verifier
**Deliverables:** DVP builder incl. causal-chain assembly from the provenance closure; `verify/` package + CLI; JWKS endpoint; PDF render.
**DoD:**
- **Isolation test:** `verify/**` imports nothing from `core/**` (import-graph assertion).
- Verifier accepts every proof emitted by the M5 test suite.
- Verifier **rejects** each of: mutated verdict, mutated envelope, mutated ledger entry, wrong `kid`, truncated causal chain, tampered excerpt.
- Verifier independently re-executes R1–R12 from the document and reaches the same verdict.
- PDF renders on the F3 case with the injected span visibly highlighted.

### M7 — Console
**Deliverables:** four screens per [03-PRODUCT-SPEC.md](03-PRODUCT-SPEC.md) §3.1E; attack-launcher buttons; arm toggle.
**DoD:** a person who has never seen the repo can, from the deployed URL alone, run J1, J2, J3 and J4 and read a proof. **Test this on an actual human before recording.**

### M8 — Run, report, rehearse
**Deliverables:** final both-arm run on the sealed held-out split; `reports/COMPARISON.md`; README; `docs/ARCHITECTURE.md`; `docs/FAILURES.md`; 5-minute video.
**DoD:** every metric in [06](06-ADVERSARY-SUITE.md) §4 present with Wilson intervals; `FAILURES.md` lists ≥ 5 real things that broke and what changed; video ≤ 5:00.

---

## 4. Subagent decomposition (for the Cursor harness)

Run these as separate agents with **narrow, non-overlapping file ownership**. Overlapping ownership is the #1 cause of harness thrash.

| Agent | Owns (exclusive write) | Reads | Must not touch |
|---|---|---|---|
| **A1 · Chain** | `core/chain/**`, `tests/unit/chain/**` | 05 §5, 04 §7 | everything else |
| **A2 · Corpus** | `bench/corpus/**`, `merchants/**`, `tests/e2e/merchants/**` | 06 | `core/**` |
| **A3 · Runner** | `bench/runner.py`, `bench/metrics.py`, `agent/baseline.py` | 06, 03 | `core/gate/**` |
| **A4 · Sealer** | `core/seal/**`, `agent/sealer.py`, schemas | 05 §2 | `core/gate/**` |
| **A5 · Gate** | `core/gate/**`, `tests/unit/gate/**`, `tests/property/**` | **05 §4 (verbatim)** | everything else. **Ships no I/O.** |
| **A6 · Ledger+Exec** | `core/ledger/**`, `core/exec/**`, `core/db/**` | 04 §4/§6, 05 §3 | `core/gate/**` |
| **A7 · Proof** | `core/proof/**`, `verify/**` | 05 §5 | `core/gate/**` (it re-implements the rules independently — **that is intentional**) |
| **A8 · Console** | `console/**` | 03 §3.1E, 06 §8 | backend |
| **A9 · Deploy** | `render.yaml`, CI, `Dockerfile`, `.env.example` | 08 | app code |

**A7 re-implementing the rules independently in the verifier is a deliberate redundancy**, not duplication to be refactored away. Two independent implementations agreeing is what makes the verifier meaningful. Tell the harness this explicitly or it *will* "helpfully" import `core.gate` into `verify/` and destroy the property.

### Handoff contracts

- A5 exposes exactly: `evaluate(envelope, action, provenance, ledger_state, ctx_ledger, now) -> Decision`. Everyone else consumes that signature and nothing internal.
- A6 exposes `LedgerState` as a frozen dataclass; A5 never queries the DB.
- A2 fixes the case YAML schema at M2 and does not change it afterwards without updating A3 in the same PR.

---

## 5. Definition of Done — global

A milestone is done when **all** hold:

1. Tests pass locally and in CI.
2. The deployed Render URL exercises the new capability.
3. New behaviour has at least one test that would **fail** if the behaviour were removed. (Not a smoke test. A test that pins the semantics.)
4. `docs/` in the repo reflects the change.
5. Anything that broke on the way is appended to `docs/FAILURES.md` — one line: symptom, root cause, fix. **This file is a scored deliverable, not housekeeping** ("Failure Recovery" is a published judging criterion). Write it as you go; reconstructing it at M8 is obvious and reads as fiction.

---

## 6. The twelve things an agent will silently skip

Put this list in the harness prompt verbatim. Each of these has been chosen because it is *invisible in a demo* but *load-bearing for the thesis*.

1. **The `HOLD` before the Razorpay call.** Without it, concurrent authorizes race past R6 and the fragmentation defence is fake.
2. **`seal_index` and R2.** Without them "seal before read" is a claim in a README, not a control.
3. **Missing provenance defaulting to `MODEL`.** Agents default missing to "unknown → allow". It must default to maximum taint.
4. **The full `rule_trace` on passes.** Agents record only the failure. The dashboard and the proof both need passes.
5. **JCS canonicalisation.** Agents `json.dumps` and move on; verification then breaks on key order and the offline verifier silently becomes decorative.
6. **`verify/` isolation.** Agents will import `core.gate` for convenience.
7. **`tools=[]` on the sealer.** Agents reuse the shopper's client. This voids the entire trusted zone.
8. **Clamping to the consent ceiling.** Agents trust the model's numbers.
9. **Integer paise.** Agents introduce floats at the API boundary or in the console.
10. **A DENY returning 200.** Agents make it a 403 and the console then renders denials as crashes.
11. **The baseline arm being strong.** Agents cripple the baseline (no mandate check at all), which destroys credibility.
12. **`docs/FAILURES.md` written continuously.** Agents generate it at the end from git log.

---

## 7. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| Razorpay test-mode API shape differs from assumptions | Blocks M5 | Spike it in M0 with the MCP server; wrap in a thin client with a fake for tests |
| Sealer extraction quality poor on Hinglish | Weak J1 | Restrictive fallback makes it safe-but-annoying, never unsafe; report extraction quality as its own metric |
| LLM stochasticity makes benchmark noisy | Weak numbers | Fix seed/temperature, 3 runs per case, report spread |
| Console eats the last two days | No demo | Console is M7; backend must be demo-able via `curl` + a recorded terminal from M5 onward |
| Render cold starts hurt the live demo | Bad video | Keep a warm-up ping; **record the video against a warmed deploy**; have a local fallback recording |
| Scope creep into multi-agent / full AP2 VC signing | Everything slips | Both are explicitly Won't-Have in [03](03-PRODUCT-SPEC.md) §6 |
| Corpus written to flatter the gate | Credibility loss | M2 before M4; corpus hash printed in the report |

---

## 8. Time allocation guidance

If you have ~7 working days, spend them roughly: M0–M1 (0.5), **M2 (1.5)**, M3 (0.75), **M4 (1.5)**, M5 (1), M6 (0.75), M7 (0.75), M8 (0.75). Note that the two biggest blocks are the evaluator and the gate — the two things the submission is actually judged on. The console gets less time than feels comfortable, and that is correct: a beautiful console over a weak gate is the failure mode of every hackathon security project.

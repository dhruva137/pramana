# 10 — ALTERNATE THESES
### Two fully-worked fallbacks, in case you want a different track or a different risk profile

Pramana (Track 01) is the recommendation. These two are real theses, not filler — each has its own sharp observation and each would be a strong submission. Read §3 for the honest comparison before you decide.

---

## THESIS B — **"The Liquidity Clock"**
### Track 03: AI Revenue Recovery

### B.1 The observation

> **Indian recurring-payment recovery has been imported wholesale from a market whose failures have a different cause. Western dunning optimises around *card* failure — expiry, tokenisation drift, issuer fraud rules. India's dominant failure is *insufficient balance*. Those are not the same problem: one is a property of the instrument, the other is a property of the payer's cash-flow calendar. So the state variable that actually predicts retry success in India is not the payment's error code — it is where the payer sits in their own money cycle. And you can estimate that from data the merchant already has, without any bank permission.**

The supporting facts: UPI AutoPay failure rates run roughly **8–15%**, against **2–3%** for card mandates. Insufficient funds is the most frequent cause. NPCI permits a bounded retry budget (commonly described as **1 original + 3 retries**), and the industry's own best practice is already to time retries "to coincide with periods when customer accounts are most likely to have funds — such as post-salary credit dates."

That last clause is the tell. **Everyone knows the salary cycle matters. Nobody models it per-payer.** The industry heuristic is a *calendar constant* — retry on the 1st, retry on the 7th. But payers are not synchronised: gig and daily-wage earners replenish continuously; salaried payers replenish monthly on employer-specific dates; small merchants replenish on settlement cycles. A calendar constant is a population average applied to a bimodal, high-variance individual process, which is close to the worst thing you can do with a scarce budget of exactly three retries.

### B.2 Why nobody has done it

Because it looks like it needs bank data, and it doesn't. **The merchant's own mandate history is a censored observation of the payer's balance process.** Every past success at timestamp *t* is evidence that balance ≥ amount at *t*. Every insufficient-funds failure at *t* is evidence that balance < amount at *t*. Over 6–12 months of monthly attempts across a subscriber base, that is a sparse but genuinely informative sample of each payer's replenishment phase — and it is data the merchant already owns, with no consent problem, no account aggregator integration, and no regulatory surface.

The reframe: **this is not a dunning problem, it is a survival-analysis and constrained-scheduling problem.** Estimate a per-payer hazard of "balance sufficient" over time, then spend a hard-capped retry budget to maximise expected recovery under NPCI's timing rules and RBI's pre-debit notification requirements.

### B.3 The build

1. **Liquidity phase estimator.** Per payer, fit a periodic hazard `h(t | phase, amount)` from their own attempt history — success/failure with timestamps and error codes, treated as interval-censored observations of balance sufficiency. Cold start: back off to a cohort prior by inferred payer segment. Deliberately simple and interpretable (a periodic hazard with a small feature set beats a black box you can't defend to a panel).
2. **Constrained retry scheduler.** Given the estimator, choose retry timestamps maximising expected recovery subject to: retry budget ≤ NPCI limit, mandate debit-window constraints, the **24–48h pre-debit notification** requirement, and quiet hours. This is a small combinatorial optimisation over a discrete time grid — solvable exactly at this scale, which means it is *explainable*, which is the track's bar.
3. **The intervention chooser (where the LLM earns its place).** Retry timing is deterministic. What the LLM does is pick and compose the *communication*: pre-debit nudge vs. payment-link vs. plan-downgrade offer vs. stop, in the payer's language and register (Hinglish matters here and is a real product signal). Bounded: it selects from a fixed action set with a per-payer contact budget and hard stopping rules.
4. **Compliant escalation and stopping rules.** Explicit, encoded: max contacts per window, quiet hours, opt-out honoured immediately, and a hard stop when expected recovery falls below contact cost. Track 03's bar demands exactly this.
5. **Honest measurement.** Simulated cohort of ≥ 500 mandates with a *generated but disclosed* ground-truth balance process, plus off-policy evaluation against a logged baseline policy. Report: recovery rate, ₹ recovered per contact, retries consumed, uplift vs. calendar-constant baseline, and — critically — **uplift vs. "retry immediately 3 times," which is the real-world baseline.**

### B.4 The demo

Two payers, same failed ₹499 subscription. Payer A is salaried, phase estimated at day 2 of month; Payer B is a gig worker with near-uniform replenishment. The calendar baseline retries both on the 1st and the 7th. The Liquidity Clock retries A on the 2nd and B on a 3-day cadence. Show the recovery curve, the retry budget consumed, and the counterfactual.

### B.5 Honest weaknesses

Simulated ground truth is a real limitation and you must say so; the estimator is weak for payers with few observations; and the effect size depends on how bimodal your simulated population is, which you chose. Mitigate by pre-registering the simulation parameters and showing sensitivity to them.

### B.6 Why Razorpay wants it

They run Razorpay Subscriptions and already do smart retries. This is a direct, measurable improvement to a live product line, on the India-specific failure mode, using data they already hold — and it converts a heuristic ("retry after payday") into a per-payer estimated quantity with a stated confidence.

---

## THESIS C — **"Proof-Carrying Reconciliation"**
### Track 04: AI Finance Controller

### C.1 The observation

> **Everyone is pointing LLMs at reconciliation as a matching problem — "here are two records, do they correspond?" That's the wrong use of the model, and it's unverifiable at scale: you cannot audit a million judgements. The right decomposition is that the LLM should never match a single record. It should *write the matching rule*, and a deterministic engine should execute it and emit a proof per match. Reconciliation breaks are not unique events — they follow a small number of recurring shapes (fee netting, FX rounding, T+1 timing, partial capture, refund offset, bundled settlement). So the job is not "match a million rows" — it is "induce six programs and prove their coverage."**

Track 04's own framing says the 2026 bottleneck is **verification capacity, not generation speed**. A per-record LLM matcher makes that worse — it generates a million unverifiable judgements. A rule-synthesiser makes it better: it generates six auditable artifacts.

### C.2 The build

1. **Break-shape induction.** The LLM examines *unmatched residuals* and proposes candidate transformation rules in a small constrained DSL (`amount ± fee_rate`, `date shift ≤ T+n`, `many-to-one bundling by settlement id`, `partial capture ratio`, …). It writes programs, not answers.
2. **Deterministic executor + verifier.** Rules run in a sandbox over the batch. Every match carries a **proof object**: which rule, which fields, which tolerance, what residual remains. Zero-residual matches are auto-accepted; anything else is an exception.
3. **Coverage-driven loop.** Induce → execute → measure residual → induce again on what's left. Stop when marginal coverage falls below a threshold. This is program synthesis with a coverage objective, and it is naturally explainable.
4. **The exception list is the product.** Honest, ranked, each with a stated reason for non-resolution. Track 04's bar says it plainly: *"one cherry-picked match proves nothing."* An honest exception list is the deliverable, not the embarrassment.
5. **Metrics:** match rate, precision on a hand-labelled held-out subset, throughput (records/sec), LLM cost per 1,000 records, rules induced, and coverage per rule. Because the LLM runs once per *rule* rather than once per *record*, the cost curve is flat in batch size — a genuinely strong slide.

### C.3 The sharp secondary observation

**Cost.** Per-record LLM matching costs O(n) tokens. Rule induction costs O(number of break shapes) — effectively O(1) in batch size. At 50 records the difference is invisible; at 5 million it is the entire economics of the product. Put both curves on one chart.

### C.4 Why Razorpay wants it

Settlement reconciliation is core to a PA, the MCP server already exposes `fetch_settlement_recon_details`, and the artifact — a rule set plus per-match proofs — is exactly what an auditor or a merchant finance team can actually check. Same philosophical spine as Pramana: **the LLM writes the policy; a deterministic engine executes it and emits a proof.**

---

## §3 — Choosing

| | **A · Pramana** (T01) | **B · Liquidity Clock** (T03) | **C · Proof-Carrying Recon** (T04) |
|---|---|---|---|
| Novelty of observation | **Highest** — a structural gap with named prior art and an empty cell in the map | High — a well-known heuristic turned into an estimated per-payer quantity | Medium-high — a decomposition argument, increasingly discussed |
| Strategic pull for Razorpay | **Highest** — live pilot, live regulatory surface, unbuyable | High — direct improvement to a live product line | Medium — internal ops value, less differentiating |
| Demo drama | **Very high** — a live hijack, twice | Medium — curves and cohorts | Low-medium — tables and coverage |
| Data honesty risk | Low — real test-mode transactions, real attacks | **Highest** — simulated ground truth for the balance process | Medium — synthetic ledgers, but matching is objectively checkable |
| Build risk | Medium-high — most moving parts | Medium — the estimator can underwhelm | **Lowest** — very tractable |
| "AI judgment" criterion | **Perfect fit** — the thesis *is* "be deterministic where AI is unnecessary" | Good — deterministic scheduler, bounded LLM messaging | **Perfect fit** — LLM writes rules, engine executes |
| Crowdedness of track | High (everyone picks agentic commerce) — **but almost nobody will attack it from the security side** | Low-medium | Low |

**Recommendation: build A.** The one real risk is that Track 01 is crowded — and that risk is mostly illusory here, because the crowd will build *checkout agents* and you are building *the thing that says no to checkout agents*. You will be the only submission in that track whose demo is the other submissions getting robbed.

**Pick B instead if** you'd rather ship something with cleanly measurable rupee impact and less security-narrative risk, and you're comfortable defending a simulated ground truth.

**Pick C instead if** you have less time. It is the most tractable of the three and still lands the "verification, not generation" thesis.

**Hybrid worth noting:** C's spine ("the LLM writes the policy; a deterministic engine executes it and emits a proof") is the same spine as A. If you build A, you can answer Q24 by saying the engine generalises to reconciliation — and mean it.

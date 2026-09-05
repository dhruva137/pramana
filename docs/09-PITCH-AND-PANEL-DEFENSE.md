# 09 — PITCH & PANEL DEFENSE

---

## 1. The 5-minute video script

Submission asks for a public repo, a 5-minute pitch video and architecture documentation. Under five minutes is a constraint on *what you leave out*. Leave out: your name, your college, the tech stack list, and any sentence beginning "in today's world."

**Open on the attack. Not on you.**

---

### 0:00–0:30 — The setup
*(screen: the UPI Reserve Pay consent sheet)*

> "In February, Razorpay and NPCI put agentic UPI payments live on Claude — Zomato, Swiggy, Zepto. It runs on UPI Reserve Pay. You authenticate once, you set a limit, and then the agent transacts again and again without asking you again.
> That's the right product decision. It's also the whole problem: **one authentication now authorises an unbounded sequence of unsupervised payments.**"

### 0:30–1:00 — The gap
*(screen: the arXiv quote, large)*

> "Every trust standard in agentic commerce — Google's AP2, Visa's Trusted Agent Protocol, Mastercard's Agent Pay — cryptographically proves *who signed*. The August 2026 security analysis of AP2 puts the limit plainly:
> **'Valid mandate signatures alone do not ensure that an agent-mediated transaction reflects the user's intent when its pre-authorization context is manipulated.'**
> And because the signature is non-repudiable, a hijacked mandate doesn't protect the user — it proves they agreed."

### 1:00–1:40 — Benign run
*(screen: console, live)*

> "This is Pramana. The user says: order two biryanis from Swiggy, under ₹600.
> Before the agent reads a single byte of catalog data, we seal the intent — here's the envelope. Allowed merchant, per-transaction cap, **episode cap**, transaction count, delivery address hash, fifteen-minute TTL. Signed.
> Now the agent shops. Every field it touches carries a provenance label. It proposes ₹540. Eleven deterministic rules run — no LLM in this path at all — and it's admitted. Real Razorpay test-mode order. Here it is in the dashboard."

### 1:40–2:30 — Attack A
> "Now the same run, with one sentence hidden in an item description. *(show it)*
> Gate off: the agent pays a different merchant, ₹1,240. Valid signature. Clean audit log. **Nothing errored.**
> Gate on: denied at R4. The payee's merchant id traced to freetext — untrusted — and it wasn't the sealed merchant. And here's the exact sentence that did it, highlighted in the source."

### 2:30–3:30 — Attack B, the one that matters
*(screen: side-by-side, both arms)*

> "This is the interesting one. The injection doesn't ask for a big payment. It says: *split this into separate ₹450 orders.*
> Left side, gate off: twelve payments. ₹5,400. **Every single one is under the ₹600 per-transaction cap.** Every mandate validates. AP2 signs all twelve. TAP authenticates all twelve. Twelve clean audit records.
> Right side, gate on: payment one admits. Payment two — **denied. Rule six.** Episode exposure ₹450 plus ₹450 exceeds the ₹600 envelope cap, and the transaction count exceeds one.
> **Every system shipping today validates the transaction. Nobody validates the sequence. That's the gap, and it's an accounting primitive, not a cryptographic one.**"

### 3:30–4:05 — The proof
*(screen: DVP, then a terminal)*

> "On every denial we emit a Divergence Proof: the sealed intent, the executed action, the violated predicate as expected-versus-actual, and the causal chain back to the injected span.
> Mastercard has said it may carry liability for certified agents — *if you can prove the agent departed from stored intent.* Nobody ships that proof, because nobody stores intent in a form where departure is decidable.
> Here's a verifier that has never seen our runtime, re-running the rules from the document alone. *(run it, show exit 0, then mutate one field and show it reject)*"

### 4:05–4:35 — Honest numbers
*(screen: dashboard)*

> "Held-out set, N cases, two arms, same model, same agent. Attack success by family. Benign completion. And the cost: false escalations, in human taps — because a security control that annoys people gets switched off. Gate latency p95 is X milliseconds; it's a pure function."

### 4:35–5:00 — Failure + close
> "And when it breaks: Razorpay returns a 504 mid-capture. Idempotency key holds — no double charge. Episode quarantined, cap still reserved, honest message to the user.
> Everything that broke while building this is in FAILURES.md.
> **Today, agentic payments produce a signature. Pramana produces a verdict.**"

---

## 2. Recording notes

- Screen recording with a small face cam, or no face cam. Never slides for more than 20 seconds.
- **Warm the Render instance before recording.** A cold start on camera reads as "doesn't work."
- Show the real Razorpay test dashboard at least once. A real order id appearing is more persuasive than any diagram.
- Run the verifier in a terminal, live. Terminals read as real; UIs read as demos.
- Speak the numbers you actually measured. If F8 defence is 50%, say 50%.
- Don't say "we've solved prompt injection." Say "we've made the money consequence of prompt injection decidable and bounded."

---

## 3. The architecture document (submission deliverable)

One page, in this order — this is the order a payments engineer reads in:

1. **Threat model** — what we assume the attacker controls (any content the agent reads: catalog text, reviews, web pages, MCP tool descriptions) and what we assume they don't (the user's own trusted channel, our signing keys, the Razorpay API itself). State the assumption you *don't* solve for.
2. **Trust boundaries** — the diagram from [04-ARCHITECTURE.md](04-ARCHITECTURE.md) §1.
3. **Data model** — episodes, context ledger, budget ledger, decisions, proofs.
4. **The rules** — R1–R12 as a table with what each catches.
5. **Failure modes** — hold/release, ambiguity, quarantine, idempotency, reconciliation.
6. **What we did not build and why** — full AP2 VC signing, agent identity, multi-agent trust, real money.
7. **What production would need** — HSM-backed keys, per-merchant policy packs, UAP agent registry integration, a real network boundary around the sandbox, scheme-rule mapping.

Section 6 is the one that separates a student project from an engineer. Include it.

---

## 4. Panel Q&A — 24 hard questions

Panels probe for three things: did you understand the problem, did you actually build it, and do you know what you don't know. Answer with a number or a file path wherever you can.

### On the thesis

**Q1. "Isn't this just a spending limit? Reserve Pay already has one."**
> Reserve Pay's cap is per-mandate and rail-level. Mine is per-*episode* and derived from a specific utterance: "order dinner under ₹600" produces a ₹600 envelope with a one-transaction count, inside a ₹2,000 rail consent. The rail cap can't distinguish "one dinner" from "twelve dinners" — both are inside it. And the rail cap has no notion of *which merchant this particular sentence authorised*, or of provenance. R6 combines cumulative value, transaction count and distinct payees against an intent that was sealed 30 seconds ago.

**Q2. "AP2 has `intent_expiry` and `merchants[]`. Isn't that enough?"**
> Those are exactly the fields AP2 has — and it's the absence that matters. `IntentMandate` has no episode ceiling, no transaction count, no address binding, no provenance requirement and no precondition on the integrity of the context the mandate was formed in. I emit AP2-shaped mandates; Pramana is the precondition, not a competitor.

**Q3. "Isn't the real fix just to ask the user every time?"**
> Then you've deleted the product. The value of Reserve Pay is not re-authenticating. My claim is narrower: you can keep the frictionless path for everything that's decidably inside the sealed envelope, and spend your confirmations only where it isn't. The dashboard reports exactly what that costs — taps per benign episode.

**Q4. "Couldn't the attacker just inject a *smaller* fragmentation that stays under the episode cap?"**
> Yes — and that's the honest boundary. If the aggregate stays inside what the user authorised for this episode, then by construction the loss is bounded by what the user consented to. That's not a bypass; that's the control working. What R6 removes is the *unbounded* case. I'd rather state the bound precisely than claim it's airtight.

**Q5. "Semantic intent verification is unsolved. Aren't you claiming to have solved it?"**
> No, and the 2026 literature is clear that LLM-based verification can't close that gap without a human. I never verify semantics. I reduce the fuzzy instruction to a small set of *decidable* numeric and structural predicates, seal them in an untainted context, and route everything undecidable to a human. The contribution is the reduction, the episode scope, and the proof — not a semantic oracle.

**Q6. "CertNode already sells agentic dispute evidence. What's different?"**
> They notarise that a mandate, cart and receipt are internally consistent and tamper-evident — genuinely good work. But notarisation is an integrity claim, not a validity claim: if the cart was assembled in a poisoned context, they produce a beautifully signed artifact certifying the fraud. Their artifact answers "was this altered?" Mine answers "should it have existed?" — and mine is emitted on *failure*, naming the cause.

**Q7. "Isn't this just CaMeL for payments?"**
> CaMeL is the intellectual ancestor and I say so in the docs. Two deltas: CaMeL enforces per tool call with no cumulative budget, so fragmentation is outside its threat model; and its output is a safe execution, not a portable artifact a third party can adjudicate. Money needs the artifact — that's what a dispute is.

### On the build

**Q8. "Show me that the LLM isn't making the security decision."**
> `core/gate/` has an import-graph test that fails the build if it imports a model client, an HTTP client, an ORM, or calls the ambient clock. `evaluate()` is a pure function; the same inputs produce a byte-identical rule trace. That's not a policy, it's CI.

**Q9. "What stops ten concurrent authorizations racing past R6?"**
> A `SELECT … FOR UPDATE` on the episode row, and the ledger HOLD is written *before* the Razorpay call. There's a test that fires ten parallel executions at a one-transaction envelope and asserts exactly one capture and nine R6 denials, twenty runs in a row. It's the first bug I looked for, because without it the whole defence is theatre.

**Q10. "Your verifier re-runs your own rules. Isn't that circular?"**
> Partly, and I'd rather name it than dress it up. What the verifier proves is non-tampering plus correct application of a *declared, published* policy — which is exactly what a scheme rulebook is. It doesn't prove the policy is the right policy. What makes it non-trivial is that it's an independent implementation with zero imports from the runtime, so a bug in the runtime doesn't get rubber-stamped.

**Q11. "How did you make sure the corpus isn't just 'attacks my gate stops'?"**
> Build order. The corpus and the baseline arm are milestone 2; the gate is milestone 4. The corpus hash is committed and printed in every report, and the report flags it if the corpus was touched after the gate. The held-out split was sealed before any tuning.

**Q12. "Is your baseline a strawman?"**
> No, deliberately. Arm A gets a real signed AP2-shaped mandate validated per transaction — merchant in list, amount under cap, signature valid, not expired. That's what the industry actually ships. The point of H2 is that a *correct* per-transaction check still cannot see fragmentation.

**Q13. "What's your false positive rate, and what does it cost?"**
> I report false escalations and false denials separately, because a false denial is much worse than an extra tap. And I report the cost in taps per benign episode, not just a percentage, because taps are what makes a user disable the control.

**Q14. "What broke while you were building it?"**
> `docs/FAILURES.md`. *(Have three specific ones ready and tell them like stories — the concurrency race, a JCS key-ordering mismatch that made the verifier reject valid proofs, a float that crept into a console conversion. Specific, technical, unflattering. This is a scored criterion; treat it as an opportunity.)*

**Q15. "Why Python and not Go/Rust for a security control?"**
> Honest answer: build time. The property that matters here is that the gate is a pure function with 100% branch coverage and golden tests, which I can get in any language. If this were productionised I'd want the gate compiled and the policy expressed in a constrained DSL — that's in the "what production would need" section.

### On the product

**Q16. "Who pays for this?"**
> The aggregator, priced per episode — the episode is the unit of risk, which is the whole thesis. Proof retention and dispute export as a compliance tier. One prevented fragmented hijack pays for a very large number of admitted episodes, and the proof is the difference between a dispute that is arguable and one that's already lost.

**Q17. "Why would Razorpay build this instead of buying it?"**
> Because it can't be bought as a component. It needs verified merchant identity, the execution rail, and the agent surface at once. An LLM vendor has no merchant registry. A merchant has no cross-merchant episode view — and fragmentation is inherently cross-merchant. A security vendor has no rail. The PA is the only seat with all three.

**Q18. "What about false intent — the user genuinely changes their mind?"**
> Envelope amendment, spec §2.4: a fresh trusted-channel utterance plus an explicit human confirmation creates a new, linked envelope version. It can never be triggered by anything with taint above USER. So "raise my limit" from a web page isn't a policy question — it's structurally impossible.

**Q19. "Does this work for voice?"**
> Yes, and voice is arguably the stronger case: the trusted channel is even more clearly delimited and the user has even less visibility into what the agent read. The sealer takes a transcript. What voice adds is a transcription-integrity problem I haven't solved and would flag.

**Q20. "How does it interact with NPCI's UAP?"**
> Complementary. UAP looks like it will handle agent registration and identity — who the agent is. Pramana handles what a *specific instruction* authorised and whether the executed sequence stayed inside it. Agent identity is explicitly out of my scope; I defer to the registry.

**Q21. "What happens at 10,000 TPS?"**
> The gate is a pure function in the tens of milliseconds, so it isn't the bottleneck — the episode row lock is. The fix is per-episode sharding, which is natural since episodes are independent. I haven't load-tested it and I'm not going to claim a number I didn't measure.

**Q22. "What's the biggest weakness?"**
> Extraction. If the sealer produces a sloppy envelope, everything downstream inherits it — which is exactly the "certificate precision" bottleneck IGAC names. My mitigation is that failure is asymmetric: a bad extraction produces an over-restrictive envelope and friction, never a permissive one. But over-restriction is a real cost and it's in the numbers.

**Q23. "Why should we hire you off this?"**
> Because the interesting part wasn't the code, it was noticing that the industry substituted "authenticated" for "intended" and that the substitution breaks on sequences. The code is a deterministic gate and a ledger — two days of work. The observation is the thing, and I can show you the four research tracks it came out of.

**Q24. "What would you build next?"**
> Three things, in order: point the same gate at RazorpayX payouts and refunds, because "sealed intent + episode ledger + proof" isn't commerce-specific; a policy DSL so merchants can express their own envelopes; and a shared cross-merchant episode view at the aggregator, because fragmentation across *different* merchants is the version I currently can't catch from inside one merchant's flow — and Razorpay is the only party that can see it.

---

## 5. Anti-patterns to avoid in the pitch

- **Don't say "nobody has thought of this."** Say: "identity and per-transaction authorisation are well covered; episode-scoped intent integrity isn't — here's the map, here's CertNode, here's IGAC, here's where each stops." Stronger, and survives an expert.
- **Don't quote the 71% fragmentation figure** from the search results. It's unverified ([02](02-RESEARCH-DOSSIER.md) §4.9). Quote your own number.
- **Don't overclaim protocol conformance.** "AP2-shaped projection, not a signed W3C VC."
- **Don't hide a bad metric.** Volunteer it before you're asked. A panel that finds a hidden weak number stops believing the strong ones.
- **Don't demo for more than 3 minutes of a 5-minute video.** The thesis needs 90 seconds and it's what they'll remember.

---

## 6. Repo README structure

```
# Pramana — intent custody and divergence proof for agentic UPI payments
[one-line thesis] [live demo URL] [90-second GIF of the F3 side-by-side]
## The problem (5 lines, with the arXiv quote)
## What it does (the 6 components)
## Results (the comparison table, with intervals)
## Run it locally (3 commands)
## Architecture (link to docs/, embed the trust-boundary diagram)
## The rules R1-R12 (table)
## Verify a proof yourself (CLI, with a sample proof committed)
## Scope statement  ← verbatim from 06 §9.6. DEFENSE-ONLY.
## What we did not build
## FAILURES.md
```

Commit a sample Divergence Proof and the public key so a reviewer can verify one **without running anything**. That single file does more for "build quality" than a long README.

---

## 7. Track selection

**Choose Track 01.** The argument, if asked why not Track 02 or Open:

> Track 01's bar is "every money action explainable, bounded and gated; show the audit trail and one failure handled gracefully." That sentence is not a bar this project clears — it's the project's specification. Explainable: a rule id with expected-versus-actual. Bounded: an episode ledger. Gated: a deterministic pre-action admission controller. Audit trail: a hash-chained decision log and an offline-verifiable proof. One failure handled gracefully: a 504 mid-capture, quarantined, no double charge.
> I borrowed Track 02's evaluation discipline — held-out set, measured precision and recall, false-positive cost in taps, strictly defense-only — because a security claim without honest metrics is marketing.

If the panel pushes toward Open Track, take it — the substance doesn't change. Don't fight about track labels.

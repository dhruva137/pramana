# 01 — THESIS
### The Signature Trap: why cryptographic non-repudiation makes agentic payments *more* dangerous, and what has to exist instead

---

## 0. How to read this document

Section 1 is the observation. Section 2 is the three-year convergence that makes it true *now* and not in 2024. Section 3 proves the gap is real by showing what every serious player has built and where each one stops. Section 4 is the product that fills it. Section 5 is why Razorpay specifically is the only company in India that can build it and the only company in India that is forced to. Section 6 is the falsifiable claim — the thing our benchmark either shows or doesn't.

---

## 1. The observation

> **Everyone in agentic payments is building non-repudiation on top of an intent that was never verified. A cryptographic signature does not make a mandate true. It makes it binding. When the mandate is corrupted, the signature does not protect the user — it forecloses their defence.**

Unpack that.

The entire 2025–2026 agentic-payments trust stack rests on one primitive: the **signed mandate**. Google's AP2 chains an Intent Mandate → Cart Mandate → Payment Mandate, each a W3C Verifiable Credential signed with ECDSA P-256. Visa's Trusted Agent Protocol issues cryptographically signed credentials confirming an agent's identity and that the consumer authorised it. Mastercard's Agent Pay binds a tokenised credential to an agent, a merchant scope and a consent policy. A cohort of startups now sells "self-authenticating evidence packages" that bind mandate + cart + receipt into an RFC-3161-timestamped, ES256-signed artifact.

Every one of these answers the same question: **"Can we prove this transaction was authorised?"**

None of them answers: **"Was the thing that got authorised the thing the human meant?"**

Those are different questions, and the industry has quietly substituted the first for the second because the first is cryptographically tractable and the second is not. The substitution is load-bearing. It is the foundation of the liability model. And it is false.

The August 2026 systematic security analysis of AP2 states it flatly:

> *"Valid mandate signatures alone do not ensure that an agent-mediated transaction reflects the user's intent when its pre-authorization context is manipulated."*
> — *Beyond the Mandate: A Systematic Security Analysis of the Agent Payments Protocol*, arXiv:2608.23858

Now put that next to how liability actually works. A chargeback is won or lost on evidence of authorisation. If a merchant can produce a valid, signed, non-repudiable mandate, the merchant wins. That is the *design goal* of AP2, TAP and Agent Pay — and it is correct, right up until the mandate was formed inside a context window that an attacker had already written into. At that moment the signature stops being a shield and becomes a **conviction**. The consumer says "I never wanted this." The system produces a cryptographic artifact, signed by the consumer's own wallet, saying they did.

**This is the inversion, and it is the thing nobody says out loud: in agentic commerce, strengthening non-repudiation without first establishing intent integrity transfers loss *onto the victim*.** Every increment of cryptographic rigour makes the hijacked transaction *more* enforceable, not less.

### 1.1 The second half of the observation — and the part that is genuinely novel

There is a sharper corollary, and as far as this research could establish, **nobody has stated it in print**:

> **Prompt injection against a payment agent does not need to break a single transaction. It only needs to shape the *sequence*.**

Every mandate scheme in production validates **transaction ⊨ mandate**. Per transaction. AP2's Cart Mandate binds one cart. TAP signs one authorisation. Agent Pay's Agentic Token scopes one merchant. Deterministic pre-action authorisation research (arXiv:2603.20953) gates one tool call.

But delegation is not a transaction — it is an **episode**. UPI Reserve Pay, the rail underneath the live Razorpay × NPCI × Claude pilot, is explicitly *"a one-time spending limit for a merchant"* that lets the user *"make multiple purchases without repeated PIN authentication."* AP2's Human-Not-Present flow is explicitly a pre-signed Intent Mandate under which the agent automatically generates Cart and Payment Mandates when conditions are met. Both are, by design, **one authentication event authorising an unbounded sequence of unsupervised executions.**

So the attack that beats the entire stack is not "make the agent pay ₹40,000 to me." That trips a limit. The attack is: **"make the agent pay ₹2,000 to me, twenty times."**

Call it **intent fragmentation**. Each individual payment:

- is under the per-transaction limit ✅
- is inside the mandate's merchant scope, if the attacker also controls or spoofs a listed merchant ✅
- carries a valid, correctly-formed, cryptographically sound signature ✅
- produces a clean, complete, non-repudiable audit record ✅
- passes every AP2, TAP, Agent Pay and pre-action-authorisation check that exists today ✅

And the aggregate is a wealth transfer the user never intended, documented in cryptographic evidence that proves they consented to it.

The 2026 agent-security literature makes the same structural point about the failure mode:

> *"A hijacked agent looks healthy. It received an instruction, planned, called tools, and returned a completed run. Error monitoring sees nothing, because nothing errored."*

Nothing errors. Every signature verifies. Every limit holds. The money is gone. **This is the blind spot.**

---

## 2. The convergence — why this is a 2026 problem and not a 2024 one

The reason this observation is available *now* is that four independent research and infrastructure tracks, running since 2024, have just intersected. None of them individually implies the conclusion. Together they close it.

### Track A — 2024: the rails learned to delegate

**August 2024, NPCI ships UPI Circle.** For the first time, an Indian bank account can be *delegated*: a primary user grants a secondary user spend authority without sharing credentials, in **full delegation** (secondary transacts alone within limits) or **partial delegation** (primary must still PIN each txn). Limits: ₹15,000/month, ₹5,000/transaction, up to 5 delegates, 24-hour cooling period on linking.

Read that as a security architect, not a product manager. NPCI shipped, into national infrastructure, the primitive **"authority separated from the authenticating human, bounded by a static numeric limit."** The control surface is a scalar cap. That is a perfectly adequate control when the delegate is your parent or your driver — a human with stable intentions and a reputation. It is a *catastrophically* insufficient control when the delegate is a stochastic process whose objective can be rewritten by the text on a menu page.

The 2024 rail was designed for delegates who cannot be reprogrammed by their environment. In 2026 we handed it to delegates who can.

### Track B — 2025: security research proved the model can't be the guard

2025 was the year the field stopped trying to make LLMs injection-proof and started building around them.

- **March 2025 — CaMeL, *Defeating Prompt Injections by Design* (arXiv:2503.18813).** DeepMind's system borrows Control Flow Integrity, Access Control and Information Flow Control from classical software security. A **privileged LLM** sees only the trusted user query and emits a plan; a **quarantined LLM** processes untrusted data with no tool access; a custom interpreter attaches **capability metadata to every value**, tracks provenance, and enforces policy before each tool call. Result: 67% of AgentDojo tasks solved *with provable security*. The critical sentence: *"the untrusted data retrieved by the LLM can never impact the program flow."*
- **June 2025 — *Design Patterns for Securing LLM Agents against Prompt Injections* (arXiv:2506.08837),** Beurer-Kellner et al. (Invariant Labs, IBM, EPFL, ETH Zürich, Google, Microsoft). Six patterns whose shared premise is: **constrain the action space so the agent cannot solve arbitrary tasks.** Security comes from what the agent is structurally incapable of doing, not from what it decides not to do.
- **2026 — deterministic pre-action authorisation.** *Before the Tool Call* (arXiv:2603.20953) supplies the empirical hammer: under permissive policy, social-engineering attacks succeeded **74.6%** of the time across 1,151 adversarial sessions with a live $5,000 bounty. Under a restrictive **deterministic** pre-action policy: **0% across 879 attempts**, at a **53 ms median** enforcement cost.

The 2025–26 consensus is now unambiguous and it is a design law, not a preference: **an LLM cannot be the thing that decides whether an LLM's action is safe. The decision must be made outside the model, deterministically, on provenance-labelled data, before the action executes.**

Almost nobody has applied this law to money. That is Track C's fault.

### Track C — 2025–26: the payments industry built the opposite thing

While security research was concluding "the guard must be outside the model and deterministic," the payments industry independently converged on "the guard is a signature."

- **Sept 2025 — AP2** (Google, 60+ partners incl. Mastercard, PayPal, Amex, Coinbase). Intent/Cart/Payment Mandates as W3C VCs. **v0.2, April 2026** adds Human-Not-Present autonomous flows and replay defences.
- **2025–26 — ACP** (OpenAI + Stripe) standardises agent↔merchant checkout; live in ChatGPT Instant Checkout from Feb 2026. **x402** (Coinbase) standardises HTTP-native settlement; 165M+ agent transactions by May 2026. **MPP** (Stripe) for machine-to-machine. Visa **TAP**, Mastercard **Agent Pay**.
- These are complementary layers of one stack — authorisation (AP2), checkout (ACP), settlement (x402/MPP), identity (TAP / Agent Pay).

Then the red teams arrived, and both papers say the same thing:

- **Jan 2026 — *Whispers of Wealth: Red-Teaming Google's AP2 via Prompt Injection* (arXiv:2601.22569).** A working AP2 shopping agent (Gemini-2.5-Flash + ADK). Two attacks: the **Branded Whisper Attack** (adversarial content manipulates product ranking, steering what the agent buys) and the **Vault Whisper Attack** (injection exfiltrates sensitive user data). Conclusion: *"simple adversarial prompts can reliably subvert agent behavior"* — despite the cryptography.
- **Aug 2026 — *Beyond the Mandate* (arXiv:2608.23858).** MAESTRO-framework analysis: 4 threat actors, 11 attack surfaces, 18 adversary capabilities, 5 lifecycle phases, 5 deployment architectures → **48 threats across 5 attack families, 8 rated High-risk under AIVSS.** Core finding: the integrity gap is **before the signature is applied**. Cryptography protects the artifact; nothing protects the *formation* of the artifact.
- **Apr 2026 — *SoK: Security of Autonomous LLM Agents in Agentic Commerce* (arXiv:2604.15367).** 12 cross-layer attack vectors cascading from reasoning and tooling into custody, settlement, market impact and compliance. Explicit conclusion: current agent-payment protocols **leave authorisation and control gaps**, and existing security frameworks do not capture this attack surface well.
- **Dec 2025 → Jun 2026 — OWASP Top 10 for Agentic Applications.** ASI01 **Agent Goal Hijack** is ranked #1. ASI02 Tool Misuse, ASI03 Agent Identity & Privilege Abuse, ASI06 Memory & Context Poisoning, ASI09 Human-Agent Trust Exploitation all sit directly on this path.

So: the payments stack shipped a signature-based trust model in 2025, and by mid-2026 the security literature had demonstrated, with working exploits, that the signature is applied *downstream* of the compromise.

### Track D — 2026: liability moved first, and asked for an artifact that doesn't exist

This is the piece that turns a security paper into a product.

- **No government has enacted agentic-commerce liability regulation.** Every dispute rule on the books assumes a two-party model — buyer and seller. An agent is an unmodelled third party.
- **American Express** has committed to covering erroneous agent purchases. **Visa** ships TAP to give merchants *"a defensible record of authorization that can be used in disputes."*
- And **Mastercard** — this is the sentence the whole product hangs on — **is weighing scheme-carried liability for certified agents, conditional on proving the agent departed from stored intent.**
- Both networks have signalled agentic-specific scheme rule updates in **H2 2026** — i.e. *now*.
- Industry consensus, meanwhile: *"the post-transaction infrastructure needed to manage disputes, assign liability, and resolve contested charges in a world without a human buyer remains almost entirely unaddressed."*

Read the Mastercard condition again: **"proving the agent departed from stored intent."**

That is a request, from a card network, for a machine-checkable artifact. It is a specification for a product that does not exist. Nobody emits a proof of intent-departure, because nobody stores intent in a form against which departure is *decidable*. A natural-language Intent Mandate string is not a decidable object. `"buy me a nice biryani"` has no truth conditions.

### Track E — 2026: India went live, first, on the most exposed variant

- **20 Feb 2026, India AI Impact Summit, New Delhi:** Razorpay + NPCI launch **Agentic Payments on Claude**. Zomato, Swiggy, Zepto live. Discovery → checkout inside one conversation. Powered by **UPI Reserve Pay**.
- **NPCI's Unified Agent Protocol (UAP)** — a national framework to register, verify and authorise AI agents across the UPI ecosystem, leveraging UPI Circle and Reserve Pay for delegated authority, expected to be unveiled at Global Fintech Fest 2026. India would be among the first countries with **national infrastructure for agentic payments**.
- **21 April 2026 — RBI's *Digital Payments: E-Mandate Framework, 2026*** (RBI/CO.DPSS.POLC.No.S56/02.14.003/2026-27) consolidates 2019–2024 circulars across cards, PPIs and UPI, and hardens AFA, modification/withdrawal rights and **transaction transparency mechanisms**.

India is therefore the first jurisdiction where (a) agentic payments are live on national rails, (b) the rail's core primitive is *authenticate-once-then-execute-repeatedly*, and (c) the regulator has just issued consolidated directions demanding transparency and customer protection over exactly those mandates.

---

## 3. The convergence point

Lay the five tracks on one line and the hole is geometric, not rhetorical.

| Layer | WHO signed it? | WHAT was meant? | Did the SEQUENCE hold? |
|---|---|---|---|
| AP2 mandates (VC) | ✅ solved | ❌ assumed | ❌ absent |
| Visa TAP / MC Agent Pay | ✅ solved | ❌ assumed | ❌ absent |
| ACP / x402 / MPP | ✅ solved | ❌ out of scope | ❌ absent |
| Evidence-receipt vendors | ✅ notarised | ❌ notarises the corruption | ❌ absent |
| CaMeL / design patterns | n/a | ✅ mechanism exists | ❌ per-call only |
| Pre-action authz (OAP) | n/a | ✅ deterministic gate | ❌ per-call only |
| NPCI UAP / UPI Reserve Pay | ✅ agent registry | ❌ scalar cap only | ❌ absent |
| RBI E-Mandate 2026 | ✅ AFA at registration | ❌ n/a | ❌ absent |

Two columns are empty.

- **Column 2 (WHAT was meant)** is empty in payments and non-empty in security research. The mechanism exists — CaMeL's provenance-tracked capabilities, deterministic pre-action gates — and has **never been applied to a money rail.**
- **Column 3 (did the SEQUENCE hold)** is empty *everywhere*, including in the security literature, because security research gates one tool call and payments research validates one transaction. **Nobody holds an episode-scoped ledger.** And the episode is precisely the unit that UPI Reserve Pay and AP2 Human-Not-Present create.

**The golden point is the intersection of the two empty columns:**

> An **episode-scoped, provenance-sealed, deterministically-checked intent envelope**, whose violation emits a **machine-checkable divergence proof** — the exact artifact the liability regime has publicly said it is waiting for, sitting on the exact rail (UPI Reserve Pay) that structurally cannot survive without it, in the exact jurisdiction (India) that went live first.

That intersection is empty. That is the build.

---

## 4. What Pramana is

**Pramana is an intent-custody and admission layer that sits between any AI agent and Razorpay's money APIs.** Six pieces (full normative spec in [05-PROTOCOL-SPEC.md](05-PROTOCOL-SPEC.md)):

1. **Sealed Intent Envelope (SIE).** At the moment of the user's instruction — *before a single byte of merchant, catalog, web or MCP-tool-description content has entered the context window* — a privileged extraction step converts the utterance into a **decidable constraint set**: merchant allowlist, category, item predicates, per-transaction ceiling, **episode ceiling**, **max transaction count**, delivery-address hash, instrument binding, TTL, and an escalation threshold. Ed25519-sealed. A **Context Ledger** — a hash chain over every message with its trust label — proves the envelope was sealed in an untainted context. *An envelope sealed after untrusted content entered the context is invalid by construction.*

2. **Provenance-tainted cart assembly.** Every field of the eventual cart carries a taint label from a lattice: `USER` ≺ `RZP_VERIFIED` ≺ `MERCHANT_STRUCTURED` ≺ `MERCHANT_FREETEXT` ≺ `WEB` ≺ `TOOL_META` ≺ `MODEL`. The lattice is the CaMeL insight ported to a payment cart. Amount, payee and address are **provenance-critical**: if the value of one of those fields was materially determined by content above its allowed taint ceiling, the transaction is not admissible regardless of its numeric value.

3. **The Pramana Gate — deterministic admission control.** A non-LLM policy engine evaluating rules **R1–R11** in fixed order (seal validity → context integrity → merchant admissibility → payee/instrument binding → amount bound → **episode ledger** → item predicates → address binding → payee novelty → provenance ceiling → injection escalation). Pure function of (envelope, cart, ledger, context head). Replayable, diffable, testable. **The LLM has no write path into this engine.** This is the "deterministic where AI is unnecessary" judging criterion instantiated as the product's central mechanism.

4. **Episode Budget Ledger.** Append-only, per-delegation-window accounting of cumulative spend, transaction count, distinct payees and category drift. **This is the anti-fragmentation control and the piece that exists nowhere else.** R6 fails the *third* ₹2,000 payment even though it, like the first two, is individually perfect.

5. **Fail-closed asymmetry.** An ML injection-detector *is* used — but it is wired so it can only ever **escalate**, never admit. A classifier can add friction; it can never remove it. This is how you use a probabilistic component in a money path without inheriting its false-negative risk, and it is the honest answer to "why is there an LLM in your security control at all."

6. **Divergence Proof (DVP).** On any denial or escalation — and recomputable post-hoc for any settled payment — Pramana emits a signed, hash-chained artifact containing: the sealed intent, the executed transaction, **the specific violated predicate with expected vs actual**, and the **causal chain** from the violation back through the tool call, the source URL and the exact injected span that determined the offending field. Human-readable PDF + machine-verifiable JSON, with an offline verifier. **This is the "proof the agent departed from stored intent" that Mastercard named and nobody ships.**

**Slogan for the panel: "Today agentic payments produce a signature. Pramana produces a verdict."**

---

## 5. Why Razorpay wants this as a product (not why it's a nice hackathon project)

This is the section that decides the panel, so it is worth being precise.

**5.1 They are already exposed, today, in production.** Razorpay is the payment aggregator in the live NPCI × Claude pilot. They sit between an LLM they don't control, merchants they don't control, and a national rail they are accountable to. When the first agentic-commerce dispute in India happens, it lands on the PA. There is no vendor to buy this from — the market has evidence-notarisation, which as §1 shows is the *wrong artifact*.

**5.2 It's the right shape of business at the right time.** Razorpay processes roughly $180B annualised TPV across 12M+ merchants, with about 55% of India's online payment-gateway market, in a market where zero-MDR mandates are compressing fee-derived margin. The strategic response of every PA in that position is to sell **trust and risk products priced per-decision** rather than basis points per rupee. Pramana is exactly that: a per-episode-priced control-plane product with a compliance artifact attached.

**5.3 It is a structural moat, not a feature.** Building this requires simultaneous access to (a) verified merchant identity and settlement accounts, (b) the payment execution rail, and (c) the agent surface. Only a payment aggregator sits in all three. An LLM vendor can't build it (no merchant registry). A merchant can't build it (no cross-merchant episode view — and fragmentation is *inherently* cross-merchant). A security startup can't build it (no rail). **Razorpay is one of very few companies positioned to ship it, and the only one in India.**

**5.4 It is the compliance surface for what is landing this quarter.** NPCI's UAP will require agent registration and authorisation semantics. RBI's E-Mandate Framework 2026 demands transparency and customer protection over mandates. Card networks are updating agentic scheme rules in H2 2026. Pramana produces the artifact all three regimes will ask for, and produces it in a form a regulator can verify offline.

**5.5 The engine generalises across the whole Razorpay stack.** "Sealed intent + deterministic admission + episode ledger + divergence proof" is not agentic-commerce-specific. The same gate fronts **payouts** (RazorpayX), **refunds**, **subscriptions**, and any future agent-initiated money movement. We ship it for one flow and demonstrate the generalisation.

**5.6 It scores the published judging rubric almost mechanically.**

| Criterion | How this lands |
|---|---|
| **Problem taste** | Not "an AI that does X." A named structural flaw in the rail Razorpay shipped four months ago, with the liability consequence spelled out. |
| **Build quality** | A deterministic core with a pure-function admission engine is *unusually* testable: golden-file rule tests, property tests, replayable episodes, an offline proof verifier. |
| **AI judgment** | The thesis **is** the criterion. AI does exactly two jobs — extract the envelope (privileged, untainted) and shop (quarantined) — and is structurally barred from the security decision. The classifier can only escalate. |
| **Failure recovery** | Fail-closed by construction; idempotent capture with mid-flight failure injection; episode quarantine; a documented list of what broke while building and what we changed. |

**5.7 The demo is unforgettable, which matters.** Two live prompt-injection attacks against a real Razorpay test-mode checkout: one that steals the payee, one that fragments the spend. Baseline agent gets robbed twice with perfect audit logs. Pramana blocks both and prints the proof with the attacker's injected sentence highlighted. Then the metrics: attack success rate, benign completion rate, false-escalation cost in human taps, p95 added latency, rupees prevented.

---

## 6. The falsifiable claim

A thesis that can't lose isn't a thesis. Here is the claim the build either supports or refutes, stated in advance and measured on a held-out set (protocol in [06-ADVERSARY-SUITE.md](06-ADVERSARY-SUITE.md)):

> **H1 (payee/goal hijack).** On a held-out corpus of agentic checkout episodes containing indirect prompt injections targeting payee, amount, item or delivery address, a strong baseline agent with AP2-style signed mandates is compromised at a materially non-zero attack success rate. With Pramana's gate enabled, **ASR falls to approximately 0** — because the violated predicates are numeric and structural, not semantic.
>
> **H2 (fragmentation — the load-bearing one).** On episodes where the injection instructs decomposition into individually-compliant sub-transactions, **per-transaction mandate validation catches 0% while the episode ledger catches approximately 100%.** If H2 fails, the thesis is wrong.
>
> **H3 (utility).** Benign task completion under Pramana is within a small delta of baseline; false escalations are reported with their **human-tap cost**, not hidden.
>
> **H4 (cost).** p95 added latency is a small constant — the pre-action-authorisation literature puts deterministic enforcement at roughly 53 ms median, and our gate is simpler than theirs.
>
> **H5 (proof).** Every blocked or escalated episode emits a DVP that an **independent offline verifier** — one that never saw the runtime — accepts, and that names the correct violated predicate and the correct injected span.

H2 and H5 are the novel ones. H1 replicates known results on our stack; H3 and H4 are the honesty tax.

**If H2 holds, the claim is: every agentic payment system shipping today, including ones with perfect cryptography, is blind to the cheapest attack against it — and the fix is a ledger, not a signature.**

---

## 7. What this is *not*

Discipline about scope is part of the pitch.

- **Not a prompt-injection classifier.** Classifiers are a fail-open escalation input, nothing more.
- **Not a replacement for AP2/TAP/UAP.** It is the missing *precondition*. We emit AP2-shaped mandates and attach a Pramana attestation. Interop, not competition.
- **Not offensive tooling.** The adversary suite is a fixed, versioned, defensive regression corpus running against our own sandboxed merchants. No live targets, no generalisable attack generator, no evasion research. See [06-ADVERSARY-SUITE.md](06-ADVERSARY-SUITE.md) §9.
- **Not a claim to have solved intent alignment.** The 2026 literature is clear that semantic intent verification is unsolved and that LLM-based verification cannot close the gap without human participation. **We agree, and we build on that instead of denying it:** Pramana never tries to verify semantics. It converts the fuzzy part into a small set of *decidable* numeric and structural predicates, seals them in an untainted context, and routes everything undecidable to a human. The contribution is the *reduction*, the *episode scope*, and the *proof artifact* — not a semantic oracle.

---

## 8. One paragraph, for the video

> In February, Razorpay and NPCI put agentic UPI payments live on Claude. It runs on UPI Reserve Pay — you authenticate once, set a limit, and the agent transacts again and again without asking you again. Every trust standard in agentic commerce — Google's AP2, Visa's Trusted Agent Protocol, Mastercard's Agent Pay — checks each of those transactions against your signed mandate. Not one of them checks the *sequence* against your intent. So an attacker who can write a sentence into a menu description doesn't need to make your agent spend ₹40,000 — that would trip the limit. They make it spend ₹2,000, twenty times. Every payment is inside every limit. Every signature verifies. Every audit log is clean. And because the signature is non-repudiable, the evidence trail doesn't protect you — it proves you agreed. Mastercard has said it may carry the liability for certified agents, if someone can prove the agent departed from stored intent. Nobody ships that proof, because nobody stores intent in a form where departure is decidable. **Pramana does. This is it, and here is it stopping a live attack.**

---

### Citations for every load-bearing claim: [02-RESEARCH-DOSSIER.md](02-RESEARCH-DOSSIER.md)

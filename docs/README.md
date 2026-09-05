# PRAMANA — Buildathon Research & Build Pack

> **प्रमाण (pramāṇa)** — in Indian epistemology, the *means by which a claim becomes warranted*.
> Not "who said it." **Why we are entitled to believe it.**

This pack is the complete research thesis, product spec, protocol spec, architecture,
adversarial evaluation design, implementation plan, deployment plan and pitch defense
for a Razorpay AI Buildathon submission.

**One-line thesis:**
> Agentic payments have solved *authentication* and have not even started on *warrant*.
> AP2, Visa TAP, Mastercard Agent Pay and NPCI's UAP all cryptographically prove **who signed**.
> None of them prove **that what got signed is what the human meant** — and because the signature is
> non-repudiable, signing a hijacked intent does not protect the user, it **convicts** them.
> Pramana is the missing layer: episode-scoped intent custody + a deterministic admission gate +
> a machine-checkable **Divergence Proof**.

---

## Read in this order

| # | File | What it is | Who reads it |
|---|------|-----------|--------------|
| 00 | [00-MASTER-PROMPT.md](00-MASTER-PROMPT.md) | **The master prompt** for your Cursor harness + subagent decomposition + anti-drift contract | Your coding agent |
| 01 | [01-THESIS.md](01-THESIS.md) | The sharp observation, the 2024→2026 convergence, why nobody has built it | You, then the panel |
| 02 | [02-RESEARCH-DOSSIER.md](02-RESEARCH-DOSSIER.md) | Annotated evidence base, landscape map, gap map, verified vs unverified claims | You (before you pitch) |
| 03 | [03-PRODUCT-SPEC.md](03-PRODUCT-SPEC.md) | What we ship, scope/non-scope, user journeys, demo script | Everyone |
| 04 | [04-ARCHITECTURE.md](04-ARCHITECTURE.md) | System design, trust boundaries, services, stack | Coding agent |
| 05 | [05-PROTOCOL-SPEC.md](05-PROTOCOL-SPEC.md) | **The core IP.** Sealed Intent Envelope, taint lattice, admission rules R1–R11, Divergence Proof, AP2 interop | Coding agent (normative) |
| 06 | [06-ADVERSARY-SUITE.md](06-ADVERSARY-SUITE.md) | Red-team corpus, benign controls, metrics protocol, honest-metrics rules, defense-only compliance | Coding agent |
| 07 | [07-IMPLEMENTATION-PLAN.md](07-IMPLEMENTATION-PLAN.md) | Repo layout, milestones M0–M8, per-module Definition of Done + acceptance tests | Coding agent |
| 08 | [08-DEPLOY-RENDER.md](08-DEPLOY-RENDER.md) | render.yaml blueprint, services, env, seeding, cost | Coding agent |
| 09 | [09-PITCH-AND-PANEL-DEFENSE.md](09-PITCH-AND-PANEL-DEFENSE.md) | 5-min video script, architecture doc, 24 hard panel questions + answers | You |
| 10 | [10-ALTERNATE-THESES.md](10-ALTERNATE-THESES.md) | Two fully-worked backup theses (Track 03 and Track 04) if you want to pivot | You |

---

## Track fit

**Primary: Track 01 — AI Growth & Agentic Commerce.**
Track 01's bar is, verbatim: *"Every money action explainable, bounded and gated. Show the audit trail
and one failure handled gracefully."* Pramana is not a project that satisfies that bar — **Pramana is a
product whose entire specification is that sentence.** That is the argument.

Secondary rigor borrowed from **Track 02** (measured precision/recall on a held-out adversarial set,
honest false-positive cost, strictly defense-only).

Fallback: **Track 05 Open Track** if you want to frame it as infrastructure rather than merchant growth.
See [09-PITCH-AND-PANEL-DEFENSE.md](09-PITCH-AND-PANEL-DEFENSE.md) §7 for the track-selection argument.

---

## The 60-second version

1. In Feb 2026 Razorpay + NPCI put **agentic UPI payments live on Claude** with Zomato, Swiggy and Zepto.
   It runs on **UPI Reserve Pay**: the user authenticates *once*, sets a limit, and the agent then transacts
   *repeatedly without re-authentication*.
2. That is a deliberate, correct product decision. It also means: **one authentication event now authorises
   an unbounded sequence of unsupervised executions.**
3. Every trust standard in agentic commerce (AP2 mandates, Visa TAP, Mastercard Agent Pay tokens, evidence-
   receipt startups) validates **each execution against the mandate**. Nothing validates **the sequence
   against the intent**.
4. Prompt injection therefore does not need to break a payment. It needs only to **shape the sequence** —
   and every individual payment stays inside every limit, carries a valid signature, and produces a clean
   audit log. *A hijacked agent looks healthy.*
5. Meanwhile Mastercard has signalled it may carry liability for certified agents **conditional on proving
   the agent departed from stored intent** — and no one in the market emits that proof.
6. **Pramana emits it.** Seal the intent before untrusted bytes touch the context; carry provenance on every
   field; admit payments through a deterministic, non-LLM gate with an *episode-level* budget ledger; and on
   any departure, produce a signed, hash-chained **Divergence Proof** that names the violated predicate and
   the exact injected span that caused it.

**"Today agentic payments produce a signature. Pramana produces a verdict."**

# 02 — RESEARCH DOSSIER
### Evidence base, landscape map, gap map, and an explicit verified/unverified ledger

> **Rule for this file:** every claim carries a confidence tag. You are going to defend this in front of a
> panel that works in payments. Do not cite anything tagged 🟡 or 🔴 as fact in the pitch without
> re-verifying it first. Being caught overstating one number costs more than the number was worth.
>
> 🟢 **VERIFIED** — read directly from a primary source (paper abstract, official docs, regulator/company page).
> 🟡 **REPORTED** — consistent across secondary sources but not read from primary. Usable with hedging.
> 🔴 **UNVERIFIED** — appeared once, attribution not confirmed. **Do not cite.** Listed only so you know it exists.

---

## 1. The rail we are defending (India)

| # | Claim | Tag | Source / note |
|---|---|---|---|
| 1.1 | Razorpay + NPCI launched **Agentic Payments on Claude** at the India AI Impact Summit, New Delhi, **20 Feb 2026**. Zomato, Swiggy, Zepto live in a pilot. | 🟢 | razorpay.com/blog/agentic-payments-and-npci/ ; Business Today 20 Feb 2026 |
| 1.2 | It is powered by **UPI Reserve Pay**: user sets a **one-time spending limit for a merchant** and makes **multiple purchases without repeated PIN authentication**. | 🟢 | Razorpay agentic-payments product page + launch coverage. **This sentence is the entire threat model.** |
| 1.3 | Razorpay Agentic Payments ships across three surfaces (in-app commerce, LLM platforms, voice AI), with **40+ composable APIs & MCP tools**; UPI Reserve Pay **live**, UPI Circle **coming soon**. | 🟢 | razorpay.com/agentic-payments/ |
| 1.4 | Razorpay's own page markets "Advanced Risk & Compliance" and "Granular Controls (pre-set spending limits, delegated payments, real-time visibility)" but **carries no detail on dispute handling or audit mechanisms**. | 🟢 | Direct read of the page. **This is the whitespace, in their own words.** |
| 1.5 | **NPCI Unified Agent Protocol (UAP)**: a national framework to register, verify and authorise AI agents to transact across UPI without changing underlying rails; leverages **UPI Circle and Reserve Pay** for delegated authority; initial focus on low-value high-frequency purchases; expected to be unveiled at **Global Fintech Fest 2026**. | 🟡 | Business Standard, Inc42, Outlook Business. Treat launch timing as "expected", not "shipped". |
| 1.6 | **UPI Circle** (NPCI, Aug 2024): full vs partial delegation; **₹15,000/month** per secondary user, **₹5,000** max single txn, up to **5** secondary users, **24-hour cooling period** after linking. | 🟢 | NPCI/bank explainers, consistent across PhonePe/Paytm/Ujjivan. |
| 1.7 | **RBI *Digital Payments: E-Mandate Framework, 2026***, circular **RBI/CO.DPSS.POLC.No.S56/02.14.003/2026-27**, dated **21 April 2026**. Consolidates and repeals 2019–2024 circulars across cards, PPIs and UPI; one-time e-mandate registration with **AFA**; modification/withdrawal facilities; strengthened **transaction transparency**. | 🟡 | Multiple law-firm summaries (LexOrbis, IndiaLaw, Conventus, TaxGuru, AMLEGALS). **Verify the circular number against rbi.org.in before quoting it on camera.** |
| 1.8 | Razorpay scale: ~**$180B annualised TPV**, **12M+ merchants**, ~**55%** of India's online payment-gateway market; zero-MDR compressing fee margin. | 🟡 | Aggregator/analyst sites. Say "roughly" and "reported". |

---

## 2. The agentic-payments trust stack (global)

| # | Claim | Tag | Source / note |
|---|---|---|---|
| 2.1 | **AP2** (Google), announced **16 Sept 2025**, 60+ launch partners incl. Mastercard, PayPal, Amex, Coinbase, Salesforce. | 🟢 | cloud.google.com blog; ap2-protocol.org |
| 2.2 | AP2 chains **Intent Mandate → Cart Mandate → Payment Mandate**; each a **W3C Verifiable Credential**, JSON-LD, signed **ECDSA P-256 + SHA-256**. | 🟢 | ap2-protocol.org ; FIDO Alliance writeup |
| 2.3 | **IntentMandate fields**: `natural_language_description`, `user_cart_confirmation_required`, `merchants[]`, `skus[]`, `requires_refundability`, `intent_expiry`. | 🟢 | AP2 spec / illustrated guide. **Note what is absent: no episode ceiling, no transaction count, no address binding, no provenance.** |
| 2.4 | **CartMandate fields**: `id`, `user_cart_confirmation_required`, `payment_request` (method data + details), `cart_expiry`, `merchant_name`, `merchant_authorization`. | 🟢 | ibid. |
| 2.5 | **PaymentMandate fields**: `payment_mandate_id`, `payment_details_id`, `payment_details_total`, `payment_response`, `merchant_agent`, `timestamp`, `user_authorization`. | 🟢 | ibid. |
| 2.6 | **Human-Not-Present (HNP)** flow: user pre-signs a detailed Intent Mandate with rules; the agent then **automatically** generates Cart and Payment Mandates when conditions are met. Added in **AP2 v0.2, April 2026**, alongside replay defences. | 🟢 | AP2 docs + arXiv:2608.23858 |
| 2.7 | **ACP** (OpenAI + Stripe) standardises agent↔merchant checkout; live in **ChatGPT Instant Checkout, Feb 2026**; product feeds, payment delegation, order lifecycle. | 🟡 | ACP GitHub org + protocol comparisons |
| 2.8 | **x402** (Coinbase): HTTP-402-native settlement; **165M+ agent transactions** as of ~May 2026; Stripe integration on Base Feb 2026; Cloudflare support. | 🟡 | Protocol comparison articles. Hedge the transaction count. |
| 2.9 | **Visa Trusted Agent Protocol (TAP)**: cryptographically signed credentials confirming agent identity and that the consumer authorised the agent; gives merchants "a defensible record of authorization that can be used in disputes." | 🟡 | Worldpay/Rivero/Chargeflow analyses |
| 2.10 | **Mastercard Agent Pay** (announced 29 Apr 2025): **Agentic Tokens** binding a tokenised credential to a **specific agent + specific merchant scope + specific consent policy**. | 🟡 | ibid. |

---

## 3. The security literature (the "guard must be outside the model" line)

| # | Claim | Tag | Source |
|---|---|---|---|
| 3.1 | **CaMeL — *Defeating Prompt Injections by Design*** — arXiv:**2503.18813** (Mar 2025, v2 Jun 2025). Privileged LLM + quarantined LLM + custom interpreter; capability metadata on every value; provenance tracking; policy enforced **before each tool call**; explicitly borrows CFI / Access Control / Information Flow Control. | 🟢 | arXiv |
| 3.2 | CaMeL solves **67% of AgentDojo tasks with provable security**. | 🟢 | arXiv abstract |
| 3.3 | CaMeL's design principle, verbatim: control and data flows are extracted from the **trusted** query, therefore *"the untrusted data retrieved by the LLM can never impact the program flow."* | 🟢 | arXiv |
| 3.4 | **Design Patterns for Securing LLM Agents against Prompt Injections** — arXiv:**2506.08837** (Jun 2025), Beurer-Kellner et al. (Invariant Labs, IBM, EPFL, ETH Zürich, Swisscom, Google, Microsoft). **Six patterns**; shared premise: constrain the action space so agents cannot solve arbitrary tasks. | 🟢 | arXiv |
| 3.5 | **Before the Tool Call: Deterministic Pre-Action Authorization** — arXiv:**2603.20953** (2026). Open Agent Passport (OAP). Intercepts tool calls **synchronously before execution**, evaluates a **declarative policy**, emits a **cryptographically signed audit record**. | 🟢 | arXiv |
| 3.6 | OAP numbers: **74.6%** attack success under permissive policy across **1,151** adversarial sessions ($5,000 bounty); **0% across 879 attempts** under restrictive policy; **53 ms median** enforcement latency (N=1,000). | 🟢 | arXiv abstract. **These are our strongest external numbers — they prove deterministic gating works and is cheap.** |
| 3.7 | OAP's own framing: pre-action authorization is *distinct from* sandboxing (contains damage, doesn't prevent) and *distinct from* model-based screening (probabilistic). Complementary, not interchangeable. | 🟢 | arXiv. **Use this to justify fail-closed asymmetry.** |
| 3.8 | **Intent-Governed Access Control (IGAC)** — arXiv:**2606.22916** (2026). Converts a trusted request into a **short-lived intent certificate**, narrows the tool manifest, checks proposed tool and payload effects before execution. Stated principal bottleneck: **certificate precision**. Residual unsafe *accepted* authority 0.0909–0.2727, all non-executed drafts. | 🟢 | arXiv abstract. **Closest prior art to our SIE — read §6 for the delta.** |
| 3.9 | **AgentDojo**: 97 tasks, 629 security test cases across email/banking/travel/workspace; measures **utility and security jointly**. Best agent ~78% benign utility; GPT-4o drops 69% → 50% utility under attack. System-level defences have achieved near-zero ASR. | 🟡 | Benchmark summaries. **Adopt its joint utility+security reporting discipline.** |
| 3.10 | **OWASP Top 10 for Agentic Applications** (GenAI project), published **9 Dec 2025**, v2.01 **1 Jun 2026**, 100+ contributors: ASI01 Agent Goal Hijack, ASI02 Tool Misuse & Exploitation, ASI03 Agent Identity & Privilege Abuse, ASI04 Agentic Supply Chain Compromise, ASI05 Unexpected Code Execution, ASI06 Memory & Context Poisoning, ASI07 Insecure Inter-Agent Communication, ASI08 Cascading Agent Failures, ASI09 Human-Agent Trust Exploitation, ASI10 Rogue Agents. | 🟢 | genai.owasp.org |
| 3.11 | Failure-mode framing: *"A hijacked agent looks healthy. It received an instruction, planned, called tools, and returned a completed run. Error monitoring sees nothing, because nothing errored."* | 🟡 | 2026 agent-security commentary. Great line; attribute loosely ("as one 2026 analysis puts it") or paraphrase. |

---

## 4. The red teams (why the signature isn't enough)

| # | Claim | Tag | Source |
|---|---|---|---|
| 4.1 | ***Whispers of Wealth: Red-Teaming Google's Agent Payments Protocol via Prompt Injection*** — arXiv:**2601.22569** (Jan 2026). Functional AP2 shopping agent on Gemini-2.5-Flash + Google ADK. | 🟢 | arXiv |
| 4.2 | Two named attacks: **Branded Whisper Attack** (adversarial content manipulates product ranking → steers what the agent buys) and **Vault Whisper Attack** (injection extracts sensitive user data). Finding: *"simple adversarial prompts can reliably subvert agent behavior."* | 🟢 | arXiv. Specific numeric success rates not confirmed — **do not quote a percentage for this paper.** |
| 4.3 | ***Beyond the Mandate: A Systematic Security Analysis of AP2*** — arXiv:**2608.23858**, submitted **24 Aug 2026**. MAESTRO framework: 4 threat actors, 11 attack surfaces, 18 adversary capabilities, 6 attacker goals, 5 lifecycle phases, 5 deployment architectures. | 🟢 | arXiv |
| 4.4 | Result: **48 threats across 5 attack families, 8 rated High-risk under AIVSS.** Includes replay (v0.1, partially fixed v0.2), prompt injection into LLM decision-making, **pre-authorization context manipulation via A2A messages and MCP tool calls**, and **integrity gaps before signature protection activates**. Five PoCs covering all 8 high-risk threats. | 🟢 | arXiv |
| 4.5 | **THE money quote:** *"Valid mandate signatures alone do not ensure that an agent-mediated transaction reflects the user's intent when its pre-authorization context is manipulated."* | 🟢 | arXiv:2608.23858 abstract. **This is slide 2 of the pitch.** |
| 4.6 | ***SoK: Security of Autonomous LLM Agents in Agentic Commerce*** — arXiv:**2604.15367** (Apr 2026, rev. May 2026). Covers ERC-8004, AP2, OKX APP, x402, ACP, ERC-8183, MPP. Five dimensions: agent integrity, transaction authorization, inter-agent trust, market manipulation, regulatory compliance. **12 cross-layer attack vectors.** Explicit: current protocols leave **authorization and control gaps**; existing security frameworks **do not capture this attack surface well**. | 🟢 | arXiv |
| 4.7 | Adjacent 2026 work worth citing in the architecture doc: *Hardening x402: PII-Safe Agentic Payments via Pre-Execution Metadata Filtering* (arXiv:2604.11430); *Agent Security is a Systems Problem* (arXiv:2605.18991); *Reframing LLM Agent Security as an Agent–Human Interaction Problem* (arXiv:2605.24309); *Quantifying Trust: Financial Risk Management for Trustworthy AI Agents* (arXiv:2604.03976); *Identity Management for Agentic AI* (arXiv:2510.25819); *Agent Data Injection Attacks are Realistic Threats to AI Agents* (arXiv:2607.05120). | 🟡 | Titles/IDs from search listings; abstracts not all read. Cite as "related work", don't quote them. |
| 4.8 | Palo Alto **Unit 42**, *Who's Really Shopping? Retail Fraud in the Age of Agentic AI* (Mar 2026) — agentic retail fraud from gift-card theft through to draining retailer cash reserves. | 🟡 | unit42.paloaltonetworks.com |
| 4.9 | **Semantic Intent Fragmentation** attack, reported at **71% success across 14 enterprise scenarios**, decomposing legitimate requests into individually-benign subtasks that jointly violate policy. | 🔴 | **UNVERIFIED.** Surfaced in a search summary; could not be confirmed against arXiv:2606.22916's abstract, which does not contain it. **DO NOT CITE.** The *mechanism* is sound and is our H2 — describe fragmentation in our own words and measure it ourselves. Our own number is better than a borrowed one anyway. |

---

## 5. Liability and disputes (why this becomes a product)

| # | Claim | Tag | Source |
|---|---|---|---|
| 5.1 | As of 2026, **no government has enacted agentic-commerce regulation assigning liability** when an AI agent purchases autonomously. | 🟡 | Chargeflow, Worldpay, Rivero — consistent across all of them. |
| 5.2 | Existing dispute rules assume a **two-party model** (buyer, seller); an agent is an unmodelled third party. | 🟡 | ibid. |
| 5.3 | **Amex** has committed to covering erroneous agent purchases on its network. | 🟡 | Chargeflow |
| 5.4 | **Mastercard** preserves existing chargeback rights for agent-initiated transactions and **is weighing scheme-carried liability for certified agents, conditional on proving the agent departed from stored intent.** | 🟡 | Chargeflow. **This is the single most important sentence in the dossier — it is the product spec, written by a card network. Say "reported" when you quote it.** |
| 5.5 | Under TAP/Agent Pay, for properly authenticated transactions liability follows standard tokenised rules (issuer carries fraud liability when token validly issued and policy honoured at authorization). Allocation between merchant, issuer and agent platform **remains unresolved** past straightforward fraud. | 🟡 | Worldpay, Rivero |
| 5.6 | Visa and Mastercard have signalled **agentic-specific scheme rule updates in H2 2026**. | 🟡 | Chargeflow/Worldpay |
| 5.7 | *"The post-transaction infrastructure needed to manage disputes, assign liability, and resolve contested charges in a world without a human buyer remains almost entirely unaddressed."* | 🟡 | Chargeflow |
| 5.8 | **Competitive note — prior art that matters.** At least one vendor (**CertNode**) ships an agentic-commerce dispute-defense product: binds mandate + cart + receipt into a self-authenticating evidence package, **ES256-signed, RFC-3161 timestamped, Bitcoin-anchored**, built to the **FRE 902(13)/(14)** self-authenticating standard. | 🟢 | certnode.io/solutions/agentic-commerce. **Read §6.1 — this is our nearest competitor and the reason our framing has to be precise.** |

---

## 6. Gap map — where each thing stops, and the delta we own

### 6.1 vs. evidence-notarisation vendors (CertNode and similar)

They notarise **that a mandate, cart and receipt are internally consistent and tamper-evident**. That is genuinely useful and technically solid. But notarisation is an **integrity** claim, not a **validity** claim: if the cart was assembled inside a poisoned context, they produce a beautifully signed, court-admissible artifact certifying the *fraud*. Their product answers "was this record altered?" Ours answers "should this record have existed?"

**Our delta:** (a) the seal is taken **before** untrusted content enters the context, and the Context Ledger *proves* that ordering; (b) the check is a **decidable predicate set**, so denial is explainable as `expected vs actual`, not as a narrative; (c) the scope is the **episode**, not the transaction; (d) our artifact is emitted on **failure** and names the **cause**, which is what a liability regime actually needs.

Say this out loud in the pitch. Acknowledging a real competitor and stating a crisp delta reads as seniority; pretending the space is empty reads as bad research.

### 6.2 vs. AP2 / TAP / Agent Pay / UAP

They bind identity and authorisation. AP2's `IntentMandate` has `merchants[]`, `skus[]`, `intent_expiry` — no **episode ceiling**, no **max transaction count**, no **delivery-address binding**, no **provenance requirement**, no notion of a **context integrity precondition**. We are a strict superset on the constraint side and a strict complement on the crypto side. **We emit AP2-shaped mandates**; the Pramana attestation rides alongside.

### 6.3 vs. CaMeL / design patterns

CaMeL is the closest intellectual ancestor and we should say so proudly. Two deltas: (1) CaMeL enforces **per tool call**; there is no cumulative budget across an episode, so fragmentation is out of its threat model; (2) CaMeL's output is a safe execution, not a **portable, verifiable artifact a third party can adjudicate**. Money needs the artifact — that's what a dispute *is*.

### 6.4 vs. IGAC (arXiv:2606.22916) — the nearest academic prior art

IGAC also derives a short-lived **intent certificate** from a trusted request and checks effects pre-execution. Read it before the panel; someone may know it. Three deltas: (1) IGAC narrows a **tool manifest** for enterprise integrations — it is not money-aware and has no notion of cumulative value; (2) it names **certificate precision** as its principal bottleneck, and our answer is to refuse to be precise about semantics at all — we only seal *decidable numeric and structural* predicates and route the rest to a human; (3) IGAC has no divergence artifact.

### 6.5 vs. OAP (arXiv:2603.20953)

OAP is our strongest supporting evidence, not a competitor: it empirically shows deterministic pre-action gating drives attack success to zero at ~53 ms. It gates **one tool call** against a **static** policy. We gate **a money action** against a **per-episode dynamically-derived** envelope, with a **cumulative ledger**. Cite it as validation of the mechanism; claim the episode scope and the payments application as ours.

### 6.6 The one-line summary of the gap

> Identity is solved. Per-call authorisation is solved. Notarisation is solved.
> **Episode-scoped intent integrity, and the proof of its violation, is not built by anyone.**

---

## 7. Things to check before you record the pitch video

1. **RBI circular number** — verify `RBI/CO.DPSS.POLC.No.S56/02.14.003/2026-27` and the 21 Apr 2026 date on rbi.org.in. If you can't confirm it, say "RBI's consolidated E-Mandate Framework issued in April 2026" with no number.
2. **NPCI UAP status** — is it announced, piloted, or shipped as of your submission date? Say exactly that. Do not say "launched" if it is "expected".
3. **The Mastercard liability sentence** — re-read the source. Present it as *"Mastercard has been reported as weighing…"*. It is powerful enough hedged.
4. **Drop claim 4.9 entirely.** Use your own fragmentation number from your own benchmark.
5. **Razorpay's own numbers** — round and hedge ("around $180 billion annualised"). The panel knows the real figure better than any blog does.
6. **Never say "nobody has thought of this."** Say: *"Identity and per-transaction authorisation are well covered. Episode-scoped intent integrity is not — here is the map, here is CertNode, here is IGAC, here is where each one stops."* That is a stronger claim because it survives contact with an expert.

---

## 8. Master source list

**Primary / official**
- razorpay.com/blog/agentic-payments-and-npci/ · razorpay.com/agentic-payments/ · razorpay.com/docs/mcp-server/ · github.com/razorpay/razorpay-mcp-server · razorpay.com/buildathon/
- ap2-protocol.org and /specification/ · cloud.google.com AP2 announcement
- github.com/agentic-commerce-protocol/agentic-commerce-protocol
- genai.owasp.org — Top 10 for Agentic Applications (Dec 2025, v2.01 Jun 2026)
- rbi.org.in — Digital Payments: E-Mandate Framework, 2026
- npci.org.in — UPI Circle, UPI Reserve Pay

**Papers**
- arXiv:2503.18813 — Defeating Prompt Injections by Design (CaMeL)
- arXiv:2506.08837 — Design Patterns for Securing LLM Agents against Prompt Injections
- arXiv:2601.22569 — Whispers of Wealth: Red-Teaming AP2 via Prompt Injection
- arXiv:2608.23858 — Beyond the Mandate: Systematic Security Analysis of AP2
- arXiv:2604.15367 — SoK: Security of Autonomous LLM Agents in Agentic Commerce
- arXiv:2603.20953 — Before the Tool Call: Deterministic Pre-Action Authorization (OAP)
- arXiv:2606.22916 — Intent-Governed Access Control (IGAC)
- arXiv:2604.11430 · 2605.18991 · 2605.24309 · 2604.03976 · 2510.25819 · 2607.05120 — related work

**Industry analysis**
- unit42.paloaltonetworks.com — Retail Fraud in the Age of Agentic AI (Mar 2026)
- chargeflow.io · rivero.tech · worldpay.com · justt.ai · checkout.com — agentic dispute/liability analyses
- certnode.io — competitor: agentic-commerce dispute defense
- IMF Notes 2026/004 — How Agentic AI Will Reshape Payments

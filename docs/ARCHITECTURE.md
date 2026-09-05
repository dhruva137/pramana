# Architecture (shipping pointer)

Normative design: [04-ARCHITECTURE.md](04-ARCHITECTURE.md) and [05-PROTOCOL-SPEC.md](05-PROTOCOL-SPEC.md).

Runtime path: **utterance → seal (Ed25519) → context ledger (taint) → gate R1–R12 (no LLM) → HOLD → Razorpay test → Divergence Proof on DENY**.

The console Command page is a live graph of that path (`GET /v1/graph/snapshot`). The gate never reads the prompt router.

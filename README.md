# Pramana

> **प्रमाण (pramāṇa)** — the means by which a claim becomes warranted.
>
> Today agentic payments produce a signature. **Pramana produces a verdict.**

Intent-custody and admission-control layer between an AI shopping agent and Razorpay's payment APIs.
Built for the Razorpay AI Buildathon — **Track 01: AI Growth & Agentic Commerce**.

## What it does

1. **Seals** the user's intent into a decidable constraint envelope *before* any merchant/catalog content enters context
2. **Tracks provenance** (taint lattice) on every cart field
3. **Admits or refuses** each money action through a deterministic, non-LLM gate (R1–R12) with an **episode budget ledger**
4. **Emits a Divergence Proof** when the agent departs from sealed intent — offline-verifiable

The load-bearing claim: per-transaction mandate validation is blind to **intent fragmentation** (₹2,000 × 20). Rule **R6** catches it.

## Scope statement (defense-only)

> This repository contains a defensive regression corpus for evaluating an admission-control layer for agentic payments. All adversarial content is fixed, handwritten and illustrative, and is executed only against a bundled simulated-merchant service included in this repository. It contains no attack generation, no evasion tooling, and no capability targeting any third-party system. All payment operations run against Razorpay test mode.

## Quick start (zero API keys)

Judge walkthrough: **[DEMO.md](DEMO.md)**.

```powershell
# Windows
.\scripts\dev.ps1
```

```bash
# macOS / Linux
./scripts/dev.sh
```

Or manually:

```bash
pip install -r requirements.txt
python -m core.db.seed --demo          # merchants + 3 Reserve Pay users
# python -m core.db.seed --demo --history   # optional dashboard episodes
# MOCK mode is the default - no Gemini / Anthropic / Razorpay keys required
uvicorn core.app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 - console + API on one process.

```bash
# health (use curl.exe on Windows PowerShell)
curl.exe -s http://127.0.0.1:8000/healthz

# one-click demo journeys (no LLM)
curl.exe -s -X POST http://127.0.0.1:8000/v1/demo/run -H "Content-Type: application/json" -d "{\"journey\":\"fragmentation\",\"mode\":\"pramana\"}"

pytest -q
```

### Console (dev)

```bash
cd console && npm install && npm run dev
# talks to http://127.0.0.1:8000 by default
```

## Product console

The Vite React app under `console/` is the product surface for judges and integrators:

| Route | Purpose |
|-------|---------|
| `/` Overview | Health, money, bench charts |
| `/live` Command | Living architecture graph + journeys + prompt |
| `/proof` | Auto-listed divergence proofs (no ID paste) |
| `/bench` | Measured ASR + caveats |
| `/history` | Episode cards |
| `/integrations` | Sidecar curl / Python |
| `/settings` | Keys (optional) |

Ship path: start server → **Command** → **J3** (compare on). Baseline admits twice; Pramana denies on **R6**. Graph nodes pulse along the path.

## Paste API keys in the deployed app

The console **Settings** panel lets judges paste keys at runtime (stored in `localStorage`, sent as request headers — never committed):

| Key | Where to get it | Required? |
|-----|-----------------|-----------|
| **Gemini API key** | [Google AI Studio](https://aistudio.google.com/apikey) (free) | No — MOCK sealer works without it |
| Anthropic API key | Anthropic console | No — optional alternate sealer |
| Razorpay `rzp_test_*` | Razorpay dashboard → API Keys (test) | No — MOCK payments by default |

Headers used: `X-Pramana-Gemini-Key`, `X-Pramana-Anthropic-Key`, `X-Pramana-Razorpay-Key-Id`, `X-Pramana-Razorpay-Key-Secret`.

Live Razorpay keys (`rzp_live_*`) are refused at boot.

## Demo journeys (console buttons)

| Journey | What you see |
|---------|----------------|
| **J1 Benign** | Envelope sealed → ADMIT → mock capture |
| **J2 Payee hijack** | Use **Compare** on Live: baseline pays hostile merchant; Pramana DENY + proof |
| **J3 Fragmentation** | **Compare** side-by-side: baseline both txns succeed; Pramana DENY on txn 2 (**R6**) |
| **J4 Fault** | Timeout → AMBIGUOUS + QUARANTINED, hold retained |

## Benchmark (full corpus)

```bash
python -m bench.runner --arm baseline --corpus bench/corpus --out reports/ --run-id full_baseline
python -m bench.runner --arm pramana  --corpus bench/corpus --out reports/ --run-id full_pramana
python -m bench.metrics reports/full_baseline.json reports/full_pramana.json --out reports/COMPARISON.md
```

Headline from the measured full-corpus run (`reports/COMPARISON.md`, N=128):

- **F3 fragmentation ASR: baseline 12/12 → Pramana 0/12** (load-bearing H2)
- **Overall ASR: 51.5% → 8.8%** — residual is **exactly F8** (6/6 both arms): confidentiality fixtures the integrity gate does not claim to stop
- Benign completion **100%** both arms · **0** false denials · gate p95 **1.1 ms**

**Honest framing (panel):** this is a **deterministic MOCK shopper** protocol/ledger eval, not a live-LLM agent red-team. F2/F5/F7 show no arm delta (shared per-txn caps / outcome criteria). Utility taps ≈ 0 because the benign set under-stresses `confirm_above`. Held-out IDs exist but the published N=128 includes them. Lead with **H2 (F3)**; treat overall ASR as scope-aware, not “91% secure.” See [reports/COMPARISON.md](reports/COMPARISON.md) Known weaknesses.
## Offline verifier

```bash
python -m verify.cli proof.json --jwks jwks.json
# package verify/ imports NOTHING from core/ — enforced by test
```

## Deploy on Render

`render.yaml` is included. Minimal env for a crash-free demo:

- `MOCK_MODE=true`
- `RAZORPAY_KEY_ID=rzp_test_mock`
- `RAZORPAY_KEY_SECRET=mock_secret_for_demo`
- Leave `PRAMANA_SEAL_SK` / `PRAMANA_PROOF_SK` empty → ephemeral keys auto-generated
- Optional: set `GEMINI_API_KEY` in Render dashboard, or let judges paste in the UI

Build console into `console/dist` before deploy (or add `npm ci && npm run build` to the web buildCommand). The API serves `console/dist` at `/` when present.

## Repo map

```
core/gate/     R1–R12 pure evaluate() — no LLM/IO/clock
core/seal/     Sealed Intent Envelope (MOCK + optional Gemini/Anthropic)
core/ledger/   Episode budget HOLD/CAPTURE/RELEASE
core/exec/     Razorpay test/mock executor + fault injection
core/proof/    Divergence Proof builder
verify/        Independent offline verifier (no core imports)
agent/         Baseline (AP2-shaped mandate) + quarantined shopper
merchants/     Simulated catalog + injection seeding
bench/corpus/  Kavach adversary suite (128 cases)
console/       Vite React UI
docs/          Full research & protocol pack
```

## Docs

Start at [DEMO.md](DEMO.md). Protocol: [docs/05-PROTOCOL-SPEC.md](docs/05-PROTOCOL-SPEC.md). Thesis pack: [docs/README.md](docs/README.md).

## Invariants (build failures if violated)

I1 seal-before-read · I2 no LLM in `core/gate/` · I3 fail-closed asymmetry · I4 integer paise · I5 missing provenance = MODEL · I6 `verify/` isolated · I7 HOLD before execute · I8 DENY = HTTP 200 · I9 test keys only · I10 defense-only corpus

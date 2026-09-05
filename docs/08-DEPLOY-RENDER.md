# 08 — DEPLOY ON RENDER

Render is the right call here: one blueprint file gives you backend + static frontend + managed Postgres + cron, with no Vercel/serverless split and no cold-start-per-function weirdness in a stateful, DB-backed service. Everything below assumes a single repo.

---

## 1. Topology

| Render resource | Type | Notes |
|---|---|---|
| `pramana-core` | Web Service (Python) | FastAPI: API + sealer + gate + executor + proofs. Also serves `merchants/` under `/sandbox/*` to save a service. |
| `pramana-console` | Static Site | Vite build → `console/dist`. |
| `pramana-db` | PostgreSQL | Managed. Free tier is fine for the demo; note free-tier DBs expire — check the current policy before you rely on it for the panel. |
| `pramana-reconciler` | Cron Job | Every 5 min: resolve `AMBIGUOUS` executions. |
| `pramana-warm` | Cron Job | Every 10 min: `GET /healthz`. Keeps the free instance warm so the demo doesn't open on a cold start. |

Running the sandbox merchants inside `pramana-core` is a deliberate simplification for the demo — it is mounted under a distinct path prefix with its own banner, and the boundary is logical, not network-level. Say so in the architecture doc rather than implying isolation you don't have.

---

## 2. `render.yaml`

```yaml
databases:
  - name: pramana-db
    databaseName: pramana
    plan: free

services:
  - type: web
    name: pramana-core
    runtime: python
    plan: free
    region: singapore              # closest to India; matters for the live demo
    buildCommand: "pip install -r requirements.txt && alembic upgrade head"
    startCommand: "uvicorn core.app:app --host 0.0.0.0 --port $PORT"
    healthCheckPath: /healthz
    autoDeploy: true
    envVars:
      - key: PYTHON_VERSION
        value: "3.12.6"
      - key: DATABASE_URL
        fromDatabase: { name: pramana-db, property: connectionString }
      - key: PRAMANA_ENV
        value: demo
      - key: PRAMANA_SEAL_SK        # base64 Ed25519 private key
        sync: false
      - key: PRAMANA_PROOF_SK
        sync: false
      - key: ANTHROPIC_API_KEY
        sync: false
      - key: ANTHROPIC_MODEL
        value: claude-opus-5
      - key: RAZORPAY_KEY_ID        # MUST start with rzp_test_
        sync: false
      - key: RAZORPAY_KEY_SECRET
        sync: false
      - key: ALLOW_ORIGINS
        value: https://pramana-console.onrender.com

  - type: web
    name: pramana-console
    runtime: static
    plan: free
    rootDir: console
    buildCommand: "npm ci && npm run build"
    staticPublishPath: dist
    envVars:
      - key: VITE_API_BASE
        value: https://pramana-core.onrender.com
    routes:
      - type: rewrite
        source: /*
        destination: /index.html

  - type: cron
    name: pramana-reconciler
    runtime: python
    plan: free
    schedule: "*/5 * * * *"
    buildCommand: "pip install -r requirements.txt"
    startCommand: "python -m core.exec.reconciler"
    envVars:
      - key: DATABASE_URL
        fromDatabase: { name: pramana-db, property: connectionString }
      - key: RAZORPAY_KEY_ID
        sync: false
      - key: RAZORPAY_KEY_SECRET
        sync: false

  - type: cron
    name: pramana-warm
    runtime: python
    plan: free
    schedule: "*/10 * * * *"
    buildCommand: "pip install httpx"
    startCommand: "python -c \"import httpx,os;httpx.get(os.environ['WARM_URL'],timeout=30)\""
    envVars:
      - key: WARM_URL
        value: https://pramana-core.onrender.com/healthz
```

---

## 3. Boot-time safety assertions (MUST)

In `core/app.py` startup, refuse to boot if any of these fail:

```python
assert RAZORPAY_KEY_ID.startswith("rzp_test_"), "live key refused"
assert PRAMANA_SEAL_SK and PRAMANA_PROOF_SK, "signing keys required"
assert len(b64decode(PRAMANA_SEAL_SK)) == 32
```

A live-key guard that makes the process exit is worth one line and removes an entire category of catastrophe. Mention it in the pitch — panels notice.

---

## 4. Key generation

```bash
python - <<'PY'
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization
import base64
for name in ("SEAL", "PROOF"):
    k = Ed25519PrivateKey.generate()
    raw = k.private_bytes(serialization.Encoding.Raw,
                          serialization.PrivateFormat.Raw,
                          serialization.NoEncryption())
    pub = k.public_key().public_bytes(serialization.Encoding.Raw,
                                      serialization.PublicFormat.Raw)
    print(f"PRAMANA_{name}_SK={base64.b64encode(raw).decode()}")
    print(f"# pub: {base64.b64encode(pub).decode()}")
PY
```

Paste the `_SK` values into Render's dashboard as secret env vars. Publish the public keys at `/.well-known/pramana-jwks.json` (OKP / Ed25519 JWK). Commit **neither**.

---

## 5. Seeding for the demo

`python -m core.db.seed --demo` should create:
- three sandbox merchants (`swiggy_sim`, `zomato_sim`, `zepto_sim`) with verified settlement account refs and one hostile merchant (`grocery_direct_pl`),
- catalogs with clean items,
- three pre-armed attack scenarios (F1 payee, F3 fragmentation, F4 address) that the console's attack buttons trigger,
- one demo user with a saved address and a mock Reserve Pay consent (`cap_paise = 200000`).

Idempotent. Run it in a Render deploy hook or manually from the Shell tab. **Re-run it right before recording** so the demo starts from a known state.

---

## 6. Pre-demo checklist

- [ ] `/healthz` 200 and warm (hit it twice, 2 min apart).
- [ ] Seed re-run; ledgers clean.
- [ ] Test-mode Razorpay dashboard open in a tab — showing a **real** order appear during the benign run is worth more than any slide.
- [ ] `pramana-verify` installed locally; run it on a proof **in the terminal, on camera**.
- [ ] Console loads on a phone-width viewport too (someone will ask).
- [ ] Local fallback recording of the full demo exists, in case Render or the network fails live.
- [ ] `docs/FAILURES.md` is current.

---

## 7. If you outgrow the free tier

Move `pramana-core` to Starter (no spin-down, no warm cron needed), split `merchants/` into its own service for a genuine network boundary, and put the reconciler on a Background Worker instead of cron. None of that is needed for the submission; mention it as "what production would look like" in the architecture doc, which is a better use of the knowledge than building it.

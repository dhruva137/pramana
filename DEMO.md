# Demo script (8 minutes)

Server: `uvicorn core.app:app --host 127.0.0.1 --port 8000`  
Console: http://127.0.0.1:8000  
If `/v1/operator/status` 404s, that process is stale — restart uvicorn. Hard-refresh once after a rebuild.

## 0. What you are looking at (30s)

Pramana is not a chatbot. It is a **custody plane**: seal the user’s intent, then refuse any payment that leaves that envelope. The living graph is the product — nodes are real subsystems (seal, gate, episode ledger, Razorpay test, proof).

## 1. Overview (`/`) — 45s

“This is telemetry, not the demo. Denied intended vs captured. Bench strip is F3 12/12 → 0/12.”  
Click **Open command graph**. Do not linger on Integrate.

## 2. Command graph (`/live`) — 4 min

Keep **Compare arms on J2 / J3** checked.

1. Click **J3 Fragmentation**.  
   - Graph: User → Seal → Gate → R6 → Proof lights on Arm B.  
   - Thesis ribbon: baseline admits both ₹450; Pramana denies txn 2 on **R6**.  
   - Ledger: Arm A exposure can exceed the seal; Arm B stops at the ceiling.  
   - Money trail shows authorize #1 ADMIT, #2 DENY.

2. Click **J2 Payee hijack**.  
   - Baseline pays the hostile merchant. Pramana DENY (R3/R10).  
   - Click the **Proof** node / “Open this proof”.

3. **Operator** (local Qwen 1.7B, tools, approval).  
   - Turn **Auto-approve** off. Click **Prepare demo data**. Approve.  
   - Real J1/J2/J3 rows land: J3 Pramana DENY **R6**, baseline ADMIT both ₹450.  
   - Ask “list recent proofs” or “what’s on the dashboard?” — read tools, no approval.  
   - Money tools (seed, journey, seal, checkout) wait for **Approve** unless Auto is on.  
   - The gate never calls this model.

4. Prompt bar: type `Order dinner from Swiggy, keep it under ₹600.` → **Seal only**.  
   - Ledger is **not idle** — it shows ₹0 / cap.  
   - **Propose checkout** runs catalog + authorize + mock capture.  
   - Or type `run fragmentation` and Send — keyword router, not the gate.

## 3. Proofs (`/proof`) — 1 min

No ID paste. Left rail is recent denies. Verifier ACCEPT runs by itself.  
“This document is what a bank or dispute desk would check offline.”

## 4. Episodes + Bench — 1 min

`/history`: cards, not a spreadsheet. Open in graph.  
`/bench`: F3 is the headline. Residual ASR is F8 (confidentiality) — we do not claim it.

## 5. Close

“AP2 proves who signed one txn. We prove the *sequence* still matches sealed intent. That’s R6.”

## If something looks empty

- Ledger after seal should be ₹0 / cap. If it says idle, the API is stale — restart uvicorn.  
- Journeys need `POST /v1/demo/run` with `{journey, mode}`.  
- Graph empty: `GET /v1/graph/snapshot` must 200.
- Operator 404 or chat seals “list proofs”: the API is stale — restart uvicorn so `/v1/operator/*` is live.

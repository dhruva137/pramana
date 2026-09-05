# Failures (scored deliverable)

| Symptom | Cause | Fix |
|---------|--------|-----|
| Bench skipped real R1 via `_test.seal_ok` | Test hook leaked into runner | Bench signs for real; numbers regenerated |
| Console demos 422 | Client sent `{scenario, arm}` | Map to `{journey, mode}` in `api.ts` |
| OpenAPI crash with SPA mounted | `FileResponse` in schema | `include_in_schema=False` |
| Empty authorize → 500 | `KeyError: amount_paise` | 422 validation |
| Mode typos silently ran Pramana | Default coerce | Strict 422 |
| Seal left ledger “idle” | Create episode returned no ledger; UI never authorized | Return genesis ledger; `POST .../checkout` |
| `/proof` was an ID form | No list endpoint | `GET /v1/proofs` + auto-verify |
| JCS / R1 false deny | Stored envelope ≠ signed bytes | Persist signed form only |
| R6 race | Concurrent authorize vs execute | Same episode lock |
| Gemini 2.0-flash 404 | Model shut down | Default `gemini-2.5-flash` |

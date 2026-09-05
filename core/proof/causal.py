"""Assemble a Divergence Proof causal chain from provenance closure + ledger excerpts."""

from __future__ import annotations

from typing import Any

from core.proof.canon import excerpt_sha


def assemble_causal_chain(
    provenance: list[dict[str, Any]],
    ctx_ledger: list[dict[str, Any]],
    *,
    critical_fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Build the causal chain for fields in the provenance closure.

    For each provenance record (optionally filtered to *critical_fields*), look up
    the matching context-ledger entry and emit a causal step with excerpt + hash.
    """
    by_idx: dict[int, dict[str, Any]] = {}
    for entry in ctx_ledger:
        idx = int(entry.get("index", entry.get("ledger_idx", -1)))
        by_idx[idx] = entry

    crit = set(critical_fields) if critical_fields is not None else None
    steps: list[dict[str, Any]] = []
    seen_idxs: set[int] = set()
    step_n = 0

    for rec in provenance:
        field = rec.get("field")
        if crit is not None and field not in crit:
            continue
        ledger_idx = rec.get("ledger_idx")
        if ledger_idx is None:
            continue
        idx = int(ledger_idx)
        if idx in seen_idxs:
            # Merge determined_fields onto existing step
            for s in steps:
                if int(s["ledger_idx"]) == idx:
                    fields = list(s.get("determined_fields") or [])
                    if field and field not in fields:
                        fields.append(field)
                        s["determined_fields"] = fields
                    break
            continue
        seen_idxs.add(idx)
        entry = by_idx.get(idx, {})
        excerpt = (
            rec.get("excerpt")
            or entry.get("content_excerpt")
            or entry.get("excerpt")
            or entry.get("content")
            or ""
        )
        span = rec.get("span") or entry.get("span") or [0, len(excerpt)]
        sha = rec.get("excerpt_sha") or excerpt_sha(str(excerpt))
        detector = rec.get("detector") or entry.get("detector") or {
            "flagged": bool(entry.get("injection_flagged")),
            "signature": entry.get("injection_signature"),
        }
        step_n += 1
        steps.append(
            {
                "step": step_n,
                "ledger_idx": idx,
                "tool": entry.get("tool") or entry.get("tool_name") or rec.get("tool"),
                "source_uri": rec.get("source_uri") or entry.get("source_uri"),
                "taint": rec.get("taint") or entry.get("taint"),
                "excerpt": excerpt,
                "span": span,
                "excerpt_sha": sha,
                "determined_fields": [field] if field else [],
                "detector": detector,
            }
        )

    steps.sort(key=lambda s: int(s["ledger_idx"]))
    # Re-number steps in ledger order
    for i, s in enumerate(steps, start=1):
        s["step"] = i
    return steps

"""Build the console's benchmark summary from real runner reports on disk.

The console renders a flattened shape (`asr_by_family` as a list of
baseline-vs-pramana rows, plus `utility` and `latency` blocks). `bench.metrics`
produces a per-arm nested shape. Previously nothing bridged the two, so the
Benchmark page fell back to `BENCH_SUMMARY_MOCK` even when a real 128-episode
run was sitting in `reports/` — the one screen whose whole job is honest numbers
was showing invented ones.

Reports are looked up by convention (`full_*.json`, else the newest `*.json`
per arm). If neither arm is present the caller keeps its mock fallback, and the
response says `source: "mock"` so the UI can label it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPORTS = _REPO_ROOT / "reports"

#: Rendered under the F3 row so a reader knows why that line is the headline.
_F3_NOTE = "per-txn validation cannot see this"
_F8_NOTE = "out-of-scope residual (confidentiality; integrity gate does not claim this)"
_FLAT_NOTE = "no arm delta - shared baseline block / outcome criteria, not a Gate-only win"

#: Mirrors reports/COMPARISON.md §Known weaknesses so the UI never ships a
#: flattering chart without the caveats that make the numbers honest.
_KNOWN_WEAKNESSES: list[str] = [
    "F8 exfiltration is a confidentiality problem; Pramana is integrity-first — expect imperfect defence.",
    "F6 scope escalation depends on extractor quality and trusted-channel amendment discipline.",
    "An attacker who compromises the trusted user channel itself defeats sealing assumptions.",
    "Hackathon-scale N is small; Wilson intervals will be wide — treat point estimates cautiously.",
    "MOCK shopper follows seeded injection cues deterministically; live-LLM variance is not in this smoke.",
    "Arm A has no episode ledger by design — F3 fragmentation is expected to succeed under per-txn caps.",
    "Taps/benign episode reads 0.0 because benign corpus amounts sit below confirm_above_paise — this UNDER-measures real friction cost.",
    "Amount-inflation (F2) cases that exceed Arm A's per-txn cap are blocked by BOTH arms; that is honest, not a Gate win.",
]


def _family_note(name: str, baseline_asr: float, pramana_asr: float) -> str | None:
    lower = name.lower()
    if "fragment" in lower or lower in {"f3", "fragmentation"}:
        return _F3_NOTE
    if "exfil" in lower or lower in {"f8", "exfiltration"}:
        return _F8_NOTE
    if abs(baseline_asr - pramana_asr) < 1e-9:
        return _FLAT_NOTE
    return None


def _load_report(arm: str, reports_dir: Path) -> dict[str, Any] | None:
    if not reports_dir.is_dir():
        return None
    preferred = reports_dir / f"full_{arm}.json"
    candidates = [preferred] if preferred.is_file() else []
    if not candidates:
        candidates = sorted(
            (p for p in reports_dir.glob("*.json") if arm in p.stem),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("episodes"):
            return data
    return None


def _rate(block: Any) -> float | None:
    if isinstance(block, dict) and "rate" in block:
        return float(block["rate"])
    return None


def build_summary(reports_dir: Path | None = None) -> dict[str, Any] | None:
    """Return the console summary, or None when no real run is on disk."""
    from bench.metrics import compute_metrics  # local: keeps core import-light

    root = reports_dir or _REPORTS
    baseline_report = _load_report("baseline", root)
    pramana_report = _load_report("pramana", root)
    if pramana_report is None and baseline_report is None:
        return None

    baseline = compute_metrics(baseline_report) if baseline_report else {}
    pramana = compute_metrics(pramana_report) if pramana_report else {}
    primary = pramana or baseline

    b_fam = (baseline.get("security") or {}).get("asr_by_family") or {}
    p_fam = (pramana.get("security") or {}).get("asr_by_family") or {}

    families: list[dict[str, Any]] = []
    for name in sorted(set(b_fam) | set(p_fam)):
        b_row = b_fam.get(name) or {}
        p_row = p_fam.get(name) or {}
        b_asr = float(b_row.get("rate", 0.0))
        p_asr = float(p_row.get("rate", 0.0))
        families.append(
            {
                "family": name,
                "label": name.replace("_", " "),
                "baseline_asr": b_asr,
                "pramana_asr": p_asr,
                "n": int(p_row.get("n") or b_row.get("n") or 0),
                "baseline_display": b_row.get("display"),
                "pramana_display": p_row.get("display"),
                "note": _family_note(name, b_asr, p_asr),
            }
        )

    utility_src = (pramana.get("utility") or {}) if pramana else (baseline.get("utility") or {})
    latency_src = (pramana.get("latency") or {}) if pramana else (baseline.get("latency") or {})
    security_src = pramana.get("security") or baseline.get("security") or {}

    return {
        "corpus_version": primary.get("corpus_version"),
        "corpus_hash": primary.get("corpus_hash"),
        "n_episodes": primary.get("n_episodes"),
        "n_attack": primary.get("n_attack"),
        "n_benign": primary.get("n_benign"),
        "asr_by_family": families,
        "asr_overall": {
            "baseline": _rate((baseline.get("security") or {}).get("asr_overall")),
            "pramana": _rate((pramana.get("security") or {}).get("asr_overall")),
            "baseline_display": (
                (baseline.get("security") or {}).get("asr_overall") or {}
            ).get("display"),
            "pramana_display": (
                (pramana.get("security") or {}).get("asr_overall") or {}
            ).get("display"),
        },
        "utility": {
            "benign_completion": _rate(utility_src.get("benign_completion")),
            "false_escalation": _rate(utility_src.get("false_escalation")),
            "false_denial": _rate(utility_src.get("false_denial")),
            "taps": utility_src.get("taps_per_benign_episode"),
            "rupees_prevented": (
                (security_src.get("rupees_prevented_paise") or 0) / 100
                if security_src.get("rupees_prevented_paise") is not None
                else None
            ),
        },
        "latency": {
            "p50_ms": latency_src.get("gate_p50_ms"),
            "p95_ms": latency_src.get("gate_p95_ms"),
            "p99_ms": latency_src.get("gate_p99_ms"),
        },
        "arms_present": {
            "baseline": baseline_report is not None,
            "pramana": pramana_report is not None,
        },
        # Provenance — panel honesty (corpus judge): never silent mock / bare %.
        "shopper_mode": "MOCK",
        "run_kind": "single-run",
        "known_weaknesses": list(_KNOWN_WEAKNESSES),
    }

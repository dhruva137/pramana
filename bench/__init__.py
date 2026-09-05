"""Benchmark runner and metrics for the Kavach adversary suite."""

from __future__ import annotations

from typing import Any

__all__ = [
    "RateCI",
    "compute_metrics",
    "load_corpus",
    "run_benchmark",
    "wilson_ci",
    "write_comparison_md",
]


def __getattr__(name: str) -> Any:
    # Lazy exports so ``python -m bench.runner`` does not double-import.
    if name in {"RateCI", "compute_metrics", "wilson_ci", "write_comparison_md"}:
        from bench import metrics as _metrics

        return getattr(_metrics, name)
    if name in {"load_corpus", "run_benchmark"}:
        from bench import runner as _runner

        return getattr(_runner, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

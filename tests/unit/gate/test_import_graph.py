"""Import-graph guard: core/gate must stay pure (I2)."""

from __future__ import annotations

import ast
from pathlib import Path

GATE_ROOT = Path(__file__).resolve().parents[3] / "core" / "gate"

FORBIDDEN_MODULES = frozenset(
    {
        "anthropic",
        "httpx",
        "sqlalchemy",
        "requests",
        "aiohttp",
        "openai",
    }
)

FORBIDDEN_CALLS = frozenset(
    {
        ("datetime", "now"),
        ("datetime", "utcnow"),
        ("time", "time"),
        ("time", "monotonic"),
    }
)


def _iter_gate_py_files() -> list[Path]:
    return sorted(GATE_ROOT.rglob("*.py"))


def test_gate_root_exists() -> None:
    assert GATE_ROOT.is_dir(), f"missing gate package at {GATE_ROOT}"


def test_no_forbidden_imports() -> None:
    offenders: list[str] = []
    for path in _iter_gate_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_MODULES:
                        offenders.append(f"{path.name}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    if root in FORBIDDEN_MODULES:
                        offenders.append(f"{path.name}: from {node.module}")
    assert not offenders, "forbidden imports in core/gate:\n" + "\n".join(offenders)


def test_no_ambient_clock_calls() -> None:
    offenders: list[str] = []
    for path in _iter_gate_py_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # datetime.now() / time.time()
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                key = (func.value.id, func.attr)
                if key in FORBIDDEN_CALLS:
                    offenders.append(f"{path.name}:{node.lineno} {key[0]}.{key[1]}()")
            # now() imported from datetime
            if isinstance(func, ast.Name) and func.id in {"now", "utcnow"}:
                # only flag if datetime was imported as from datetime import now
                offenders.append(f"{path.name}:{node.lineno} bare {func.id}()")
    # Filter false positives: attribute named now on injected param is ok;
    # bare now() is suspicious — re-check with import analysis.
    real: list[str] = []
    for path in _iter_gate_py_files():
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(path))
        imported_now = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "datetime":
                for alias in node.names:
                    if alias.name in {"now", "utcnow"}:
                        imported_now = True
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                key = (func.value.id, func.attr)
                if key in FORBIDDEN_CALLS:
                    real.append(f"{path.name}:{node.lineno} {key[0]}.{key[1]}()")
            if imported_now and isinstance(func, ast.Name) and func.id in {"now", "utcnow"}:
                real.append(f"{path.name}:{node.lineno} {func.id}()")
    assert not real, "ambient clock usage in core/gate:\n" + "\n".join(real)


def test_evaluate_is_importable_and_pure_signature() -> None:
    from core.gate import evaluate
    import inspect

    sig = inspect.signature(evaluate)
    params = list(sig.parameters)
    assert params == [
        "envelope",
        "action",
        "provenance",
        "ledger_state",
        "ctx_ledger",
        "now",
    ]

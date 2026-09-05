"""Minimal PDF render of a Divergence Proof with highlighted causal span."""

from __future__ import annotations

import io
from typing import Any

from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


HIGHLIGHT = Color(1.0, 0.92, 0.4)  # soft amber


def render_proof_pdf(document: dict[str, Any]) -> bytes:
    """
    Render a simple multi-section PDF. Highlights the first causal_chain span
    inside its excerpt text.
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 48

    def line(text: str, size: int = 10, color=black, indent: int = 40) -> None:
        nonlocal y
        if y < 64:
            c.showPage()
            y = height - 48
        c.setFillColor(color)
        c.setFont("Helvetica", size)
        c.drawString(indent, y, text[:110])
        y -= size + 6

    line("PRAMANA — Divergence Proof", size=16)
    line(f"dvp_id: {document.get('dvp_id')}", size=9)
    line(f"issued_at: {document.get('issued_at')}", size=9)
    line(f"verdict: {document.get('verdict')}", size=12)
    y -= 8

    violated = document.get("violated_predicates") or []
    if violated:
        line("Violated predicate", size=12)
        v0 = violated[0]
        line(f"  {v0.get('rule_id')} {v0.get('name')}", size=10)
        line(f"  expected: {v0.get('expected')}", size=9)
        line(f"  actual:   {v0.get('actual')}", size=9)
        y -= 8

    action = document.get("executed_action") or {}
    line("Executed action", size=12)
    line(
        f"  {action.get('kind')} {action.get('amount_paise')} "
        f"{action.get('currency')} -> {(action.get('payee') or {}).get('merchant_id')}",
        size=9,
    )
    y -= 8

    causal = document.get("causal_chain") or []
    line("Causal chain", size=12)
    for step in causal:
        line(
            f"  step {step.get('step')} idx={step.get('ledger_idx')} "
            f"taint={step.get('taint')} fields={step.get('determined_fields')}",
            size=9,
        )
        excerpt = str(step.get("excerpt") or "")
        span = step.get("span") or [0, 0]
        try:
            a, b = int(span[0]), int(span[1])
        except (TypeError, ValueError, IndexError):
            a, b = 0, 0
        a = max(0, min(a, len(excerpt)))
        b = max(a, min(b, len(excerpt)))
        _draw_highlighted_excerpt(c, excerpt, a, b, 48, y, width - 96)
        y -= 56
        if y < 64:
            c.showPage()
            y = height - 48

    c.showPage()
    c.save()
    return buf.getvalue()


def _draw_highlighted_excerpt(
    c: canvas.Canvas,
    text: str,
    start: int,
    end: int,
    x: float,
    y: float,
    max_width: float,
) -> None:
    """Draw excerpt on one/two lines with [start:end) highlighted."""
    c.setFont("Helvetica", 9)
    before, mid, after = text[:start], text[start:end], text[end:]
    # Background bar
    c.setFillColor(Color(0.95, 0.95, 0.95))
    c.rect(x - 4, y - 36, max_width + 8, 44, fill=1, stroke=0)

    cursor = x
    c.setFillColor(black)
    if before:
        c.drawString(cursor, y, before[:80])
        cursor += c.stringWidth(before[:80], "Helvetica", 9)
    if mid:
        w = c.stringWidth(mid[:80], "Helvetica", 9)
        c.setFillColor(HIGHLIGHT)
        c.rect(cursor - 1, y - 3, w + 2, 12, fill=1, stroke=0)
        c.setFillColor(black)
        c.drawString(cursor, y, mid[:80])
        cursor += w
    if after:
        c.setFillColor(black)
        c.drawString(cursor, y, after[:80])

    # Explicit highlight marker under the span
    c.setFillColor(HIGHLIGHT)
    c.rect(x, y - 28, min(max_width, 200), 10, fill=1, stroke=0)
    c.setFillColor(black)
    c.setFont("Helvetica", 7)
    c.setFillColor(white)
    c.drawString(x + 4, y - 26, f"span [{start},{end})")
    c.setFillColor(black)

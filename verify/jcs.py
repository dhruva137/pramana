"""RFC 8785 JSON Canonicalization Scheme (independent copy for verify/)."""

from __future__ import annotations

import math
import re
from typing import Any


def canonicalize(value: Any) -> bytes:
    """Return UTF-8 JCS bytes for *value*."""
    return _serialize(value).encode("utf-8")


def canonicalize_hex(value: Any) -> str:
    return canonicalize(value).hex()


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _serialize_string(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _serialize_number(value)
    if isinstance(value, list):
        return "[" + ",".join(_serialize(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = sorted(value.keys(), key=_utf16_key)
        parts = [
            _serialize_string(str(k)) + ":" + _serialize(value[k])
            for k in keys
            if value[k] is not _OMIT
        ]
        return "{" + ",".join(parts) + "}"
    raise TypeError(f"JCS cannot serialize type {type(value)!r}")


_OMIT = object()


def _utf16_key(key: str) -> list[int]:
    """Sort key per RFC 8785 (UTF-16 code unit order)."""
    s = str(key)
    units: list[int] = []
    for ch in s:
        cp = ord(ch)
        if cp <= 0xFFFF:
            units.append(cp)
        else:
            cp -= 0x10000
            units.append(0xD800 + (cp >> 10))
            units.append(0xDC00 + (cp & 0x3FF))
    return units


def _serialize_string(s: str) -> str:
    out: list[str] = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20:
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _serialize_number(n: float) -> str:
    if not math.isfinite(n):
        raise ValueError("JCS rejects non-finite numbers")
    # ECMAScript NumberToString (approx via format then normalize)
    if n == 0:
        return "0"
    s = format(n, ".15g")
    # Prefer integer form when exact
    if float(int(n)) == n and abs(n) < 1e21:
        return str(int(n))
    # Normalize exponent form
    if "e" in s or "E" in s:
        s = s.replace("E", "e")
        m = re.match(r"^(-?)(\d+)(?:\.(\d+))?e([+-]?\d+)$", s)
        if m:
            sign, intp, frac, exp = m.group(1), m.group(2), m.group(3) or "", m.group(4)
            frac = frac.rstrip("0")
            if frac:
                return f"{sign}{intp}.{frac}e{int(exp)}"
            return f"{sign}{intp}e{int(exp)}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s

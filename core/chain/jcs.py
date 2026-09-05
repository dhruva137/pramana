"""RFC 8785 JSON Canonicalization Scheme (JCS).

Number serialization follows ECMAScript Number.toString (ECMA-262 7.1.12.1)
as required by RFC 8785 3.2.2.3. Object keys are sorted by UTF-16 code units
(3.2.3). Output is UTF-8 with no insignificant whitespace (3.2.4).

Number-to-JSON formatting is adapted from Anders Rundgren reference
implementation (Apache-2.0) and the Trail of Bits rfc8785.py port.
"""

from __future__ import annotations

import math
import re
from io import BytesIO
from typing import IO, Any, Mapping, Sequence

# Interoperability range recommended by RFC 8785 Appendix B, Note 1.
_INT_MAX = 2**53 - 1
_INT_MIN = -(2**53) + 1

_ESCAPE = re.compile(r'[\x00-\x1f\\"\b\f\n\r\t]')
_ESCAPE_DCT = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
for _i in range(0x20):
    _ESCAPE_DCT.setdefault(chr(_i), f"\\u{_i:04x}")


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented under RFC 8785 JCS."""


def canonicalize(obj: Any) -> bytes:
    """Return the RFC 8785 JCS encoding of ``obj`` as UTF-8 bytes."""
    sink = BytesIO()
    _dump(obj, sink)
    return sink.getvalue()


def canonicalize_str(obj: Any) -> str:
    """Return JCS as a Unicode string (decoded UTF-8)."""
    return canonicalize(obj).decode("utf-8")


def _serialize_str(s: str, sink: IO[bytes]) -> None:
    def _replace(match: re.Match[str]) -> str:
        return _ESCAPE_DCT[match.group(0)]

    sink.write(b'"')
    try:
        sink.write(_ESCAPE.sub(_replace, s).encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise CanonicalizationError("input contains non-UTF-8 codepoints") from exc
    sink.write(b'"')


def _serialize_float(f: float, sink: IO[bytes]) -> None:
    if math.isnan(f) or math.isinf(f):
        raise CanonicalizationError(f"{f} is not representable in JCS")

    if f == 0:
        sink.write(b"0")
        return

    if f < 0:
        sink.write(b"-")
        _serialize_float(-f, sink)
        return

    stringified = str(f)

    exponent_str = ""
    exponent_value = 0
    q = stringified.find("e")
    if q > 0:
        exponent_str = stringified[q:]
        if exponent_str[2:3] == "0":
            exponent_str = exponent_str[:2] + exponent_str[3:]
        stringified = stringified[0:q]
        exponent_value = int(exponent_str[1:])

    first = stringified
    dot = ""
    last = ""
    q = stringified.find(".")
    if q > 0:
        dot = "."
        first = stringified[:q]
        last = stringified[q + 1 :]

    if last == "0":
        dot = ""
        last = ""

    if 0 < exponent_value < 21:
        first += last
        last = ""
        dot = ""
        exponent_str = ""
        q = exponent_value - len(first)
        while q >= 0:
            q -= 1
            first += "0"
    elif -7 < exponent_value < 0:
        last = first + last
        first = "0"
        dot = "."
        exponent_str = ""
        q = exponent_value
        while q < -1:
            q += 1
            last = "0" + last

    sink.write(f"{first}{dot}{last}{exponent_str}".encode("ascii"))


def _dump(obj: Any, sink: IO[bytes]) -> None:
    if obj is None:
        sink.write(b"null")
        return

    if isinstance(obj, bool):
        sink.write(b"true" if obj else b"false")
        return

    if isinstance(obj, int):
        if obj < _INT_MIN or obj > _INT_MAX:
            raise CanonicalizationError(
                f"{obj} exceeds safe integer domain for JSON floats"
            )
        sink.write(str(obj).encode("ascii"))
        return

    if isinstance(obj, str):
        _serialize_str(obj, sink)
        return

    if isinstance(obj, float):
        _serialize_float(obj, sink)
        return

    if isinstance(obj, (list, tuple)):
        if not obj:
            sink.write(b"[]")
            return
        sink.write(b"[")
        for idx, elem in enumerate(obj):
            if idx > 0:
                sink.write(b",")
            _dump(elem, sink)
        sink.write(b"]")
        return

    if isinstance(obj, Mapping):
        if not obj:
            sink.write(b"{}")
            return
        try:
            items = sorted(obj.items(), key=lambda kv: kv[0].encode("utf-16be"))
        except AttributeError as exc:
            raise CanonicalizationError("object keys must be strings") from exc

        sink.write(b"{")
        for idx, (key, value) in enumerate(items):
            if idx > 0:
                sink.write(b",")
            _serialize_str(key, sink)
            sink.write(b":")
            _dump(value, sink)
        sink.write(b"}")
        return

    if isinstance(obj, Sequence) and not isinstance(obj, (bytes, bytearray)):
        _dump(list(obj), sink)
        return

    raise CanonicalizationError(f"unsupported type: {type(obj)!r}")
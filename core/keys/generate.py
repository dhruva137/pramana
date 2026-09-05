"""CLI: generate Ed25519 seal/proof keypairs.

Usage:
  python -m core.keys.generate
  python -m core.keys.generate --write .env.keys
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def generate() -> dict[str, str]:
    """Return env-ready seal + proof key material (private + public comments)."""
    out: dict[str, str] = {}
    for name in ("SEAL", "PROOF"):
        key = Ed25519PrivateKey.generate()
        sk = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        pk = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        out[f"PRAMANA_{name}_SK"] = _b64(sk)
        out[f"PRAMANA_{name}_PK"] = _b64(pk)
        out[f"PRAMANA_{name}_KID"] = f"{name.lower()}-2026-09"
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate Pramana Ed25519 seal/proof keys (raw 32-byte base64)."
    )
    parser.add_argument(
        "--write",
        metavar="PATH",
        help="Optional path to write KEY=value lines (never commit secrets).",
    )
    parser.add_argument(
        "--print-public",
        action="store_true",
        help="Also print public keys (safe to publish via JWKS).",
    )
    args = parser.parse_args(argv)
    keys = generate()

    lines = [
        f"PRAMANA_SEAL_SK={keys['PRAMANA_SEAL_SK']}",
        f"PRAMANA_PROOF_SK={keys['PRAMANA_PROOF_SK']}",
        f"PRAMANA_SEAL_KID={keys['PRAMANA_SEAL_KID']}",
        f"PRAMANA_PROOF_KID={keys['PRAMANA_PROOF_KID']}",
    ]
    if args.print_public:
        lines.extend(
            [
                f"# PRAMANA_SEAL_PK={keys['PRAMANA_SEAL_PK']}",
                f"# PRAMANA_PROOF_PK={keys['PRAMANA_PROOF_PK']}",
            ]
        )

    text = "\n".join(lines) + "\n"
    sys.stdout.write(text)

    if args.write:
        path = Path(args.write)
        path.write_text(text, encoding="utf-8")
        print(f"# wrote {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

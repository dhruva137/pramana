"""CLI: ``pramana-verify proof.json --jwks jwks.json`` — exit 0 accept, nonzero reject."""

from __future__ import annotations

import argparse
import json
import sys

from verify.verifier import VerifyError, verify_proof


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pramana-verify", description="Offline DVP verifier")
    parser.add_argument("proof", help="Path to Divergence Proof JSON")
    parser.add_argument("--jwks", required=True, help="Path to JWKS JSON")
    args = parser.parse_args(argv)

    try:
        with open(args.proof, encoding="utf-8") as f:
            document = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read proof: {exc}", file=sys.stderr)
        return 2

    try:
        verify_proof(document, args.jwks)
    except VerifyError as exc:
        print(f"REJECT ({exc.check}): {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print("ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

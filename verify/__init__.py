"""Standalone offline Divergence Proof verifier.

MUST NOT import anything from ``core``. Cryptography, JCS, hashing, and
admission rules R1–R12 are re-implemented here deliberately so agreement
with the gate is evidence of independent consistency, not shared code.
"""

from verify.verifier import VerifyError, verify_proof

__all__ = ["VerifyError", "verify_proof"]

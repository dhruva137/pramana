"""Envelope glue between the sealer, the gate and the proof builder.

Historically this module monkeypatched ``core.seal.sealer._crypto`` at boot and
forced ``seal_ok=True`` so R1 would not DENY the demo. Both hacks are gone:

* the sealer now canonicalises with ``core.chain.jcs`` directly, so there is one
  dialect and nothing to patch;
* R1 verifies the real Ed25519 signature. The only thing this module still does
  to an envelope is (a) strip null predicate bounds that Pydantic emits and
  (b) attach ``merchant_records`` for R3/R4 — and ``merchant_records`` is
  excluded from the signed bytes by ``core.gate.rules._UNSEALED_KEYS``.

``_seal_pub`` is attached so the gate can verify without a key registry; it is
also excluded from the signed bytes.
"""

from __future__ import annotations

import base64
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def sanitize_envelope_for_gate(envelope: dict[str, Any]) -> dict[str, Any]:
    """Drop null predicate bounds — gate ``int(None)`` crashes on R7.

    Applied BEFORE sealing so the sanitised form is what gets signed. Applying it
    after would change the bytes and break R1.
    """
    env = dict(envelope)
    constraints = dict(env.get("constraints") or {})
    preds = []
    for p in constraints.get("item_predicates") or []:
        if not isinstance(p, dict):
            preds.append(p)
            continue
        preds.append({k: v for k, v in p.items() if v is not None})
    constraints["item_predicates"] = preds
    env["constraints"] = constraints
    return env


def attach_seal_pubkey(envelope: dict[str, Any], *, seal_sk_raw: bytes) -> dict[str, Any]:
    """Attach the raw Ed25519 public key so R1 can verify without a registry.

    Does NOT re-sign and does NOT set ``seal_ok``. If the signature does not
    verify after this, the envelope is genuinely invalid and R1 must say so.
    """
    out = dict(envelope)
    pub = Ed25519PrivateKey.from_private_bytes(seal_sk_raw).public_key().public_bytes_raw()
    out["_seal_pub"] = base64.urlsafe_b64encode(pub).rstrip(b"=").decode("ascii")
    return out


def envelope_for_gate(
    envelope: dict[str, Any],
    merchant_records: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Envelope copy with RZP_VERIFIED merchant records attached for R3/R4."""
    env = dict(envelope)
    if merchant_records is not None:
        env["merchant_records"] = merchant_records
    return env

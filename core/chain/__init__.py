"""Pramana chain primitives: JCS, hashing, Ed25519, hash-chain builder."""

from core.chain.builder import (
    GENESIS,
    build_chain,
    chain_hash,
    genesis_hash,
    recompute_head,
    verify_chain,
)
from core.chain.hash import sha256_hex
from core.chain.jcs import CanonicalizationError, canonicalize, canonicalize_str
from core.chain.sign import (
    generate_keypair,
    public_key_from_private,
    sign,
    verify,
)

__all__ = [
    "GENESIS",
    "CanonicalizationError",
    "build_chain",
    "canonicalize",
    "canonicalize_str",
    "chain_hash",
    "generate_keypair",
    "genesis_hash",
    "public_key_from_private",
    "recompute_head",
    "sha256_hex",
    "sign",
    "verify",
    "verify_chain",
]
"""Hash-chain builder acceptance tests (M1)."""

from __future__ import annotations

from core.chain.builder import (
    GENESIS,
    build_chain,
    chain_hash,
    genesis_hash,
    recompute_head,
    verify_chain,
)
from core.chain.hash import sha256_hex


def _entry(idx: int) -> dict:
    return {
        "idx": idx,
        "role": "user" if idx == 0 else "tool_result",
        "taint": "USER" if idx == 0 else "MERCHANT_FREETEXT",
        "content_sha": sha256_hex(f"payload-{idx}"),
        "amount_paise": 100 * idx,  # integer paise — never float
    }


def test_genesis_hash_domain_separated() -> None:
    episode_id = "ep_01JBTEST"
    assert genesis_hash(episode_id) == sha256_hex(GENESIS + episode_id.encode("utf-8"))


def test_fifty_entry_recompute_matches_and_mutation_breaks() -> None:
    episode_id = "ep_01JCHAIN50"
    entries = [_entry(i) for i in range(50)]
    hashes = build_chain(episode_id, entries)
    assert len(hashes) == 51  # h0 .. h50
    head = recompute_head(episode_id, entries)
    assert head == hashes[-1]
    assert verify_chain(episode_id, entries, head) is True

    # Mutating entry 17 must break the head / verification.
    tampered = [dict(e) for e in entries]
    tampered[17]["content_sha"] = sha256_hex("tampered-17")
    assert recompute_head(episode_id, tampered) != head
    assert verify_chain(episode_id, tampered, head) is False


def test_chain_hash_uses_jcs_not_json_dumps_key_order() -> None:
    prev = genesis_hash("ep_order")
    a = chain_hash(prev, {"b": 1, "a": 2})
    b = chain_hash(prev, {"a": 2, "b": 1})
    assert a == b

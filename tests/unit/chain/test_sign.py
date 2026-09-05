"""Ed25519 sign/verify property tests (M1 acceptance)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from core.chain.jcs import canonicalize
from core.chain.sign import generate_keypair, public_key_from_private, sign, verify

# One keypair for the property suite — generation is relatively expensive.
_SK, _PK = generate_keypair()

_json_scalar = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**53) + 1, max_value=2**53 - 1),
    st.text(max_size=40),
)

_json_value = st.recursive(
    _json_scalar,
    lambda children: st.lists(children, max_size=6)
    | st.dictionaries(st.text(min_size=1, max_size=12), children, max_size=6),
    max_leaves=40,
)


@given(doc=_json_value)
@settings(max_examples=1000, deadline=None)
def test_verify_sign_roundtrip_and_single_byte_mutation(doc: object) -> None:
    message = canonicalize(doc)
    signature = sign(message, _SK)
    assert verify(message, signature, _PK) is True

    mutated = bytearray(message)
    if not mutated:
        mutated = bytearray(b"x")
    else:
        mutated[0] ^= 0x01
    assert verify(bytes(mutated), signature, _PK) is False


def test_public_key_from_private_matches_generated() -> None:
    sk, pk = generate_keypair()
    assert public_key_from_private(sk) == pk


def test_wrong_key_fails() -> None:
    sk, pk = generate_keypair()
    _, other_pk = generate_keypair()
    msg = canonicalize({"amount_paise": 60000})
    sig = sign(msg, sk)
    assert verify(msg, sig, pk) is True
    assert verify(msg, sig, other_pk) is False

"""Pramana settings — env-driven, demo-safe defaults for Render."""

from __future__ import annotations

import base64
import os
from functools import lru_cache
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _generate_ed25519_sk_b64() -> str:
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    return _b64(raw)


def _sk_raw(b64: str) -> bytes:
    raw = base64.b64decode(b64.encode("ascii"), validate=False)
    if len(raw) != 32:
        raise ValueError(f"Ed25519 private key must be 32 bytes, got {len(raw)}")
    return raw


def _pk_raw_from_sk_b64(sk_b64: str) -> bytes:
    sk = Ed25519PrivateKey.from_private_bytes(_sk_raw(sk_b64))
    return sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    mock_mode: bool = Field(default=True, alias="MOCK_MODE")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./pramana.db",
        alias="DATABASE_URL",
    )
    pramana_env: str = Field(default="demo", alias="PRAMANA_ENV")

    pramana_seal_sk: str = Field(default="", alias="PRAMANA_SEAL_SK")
    pramana_proof_sk: str = Field(default="", alias="PRAMANA_PROOF_SK")
    pramana_seal_kid: str = Field(default="seal-2026-09", alias="PRAMANA_SEAL_KID")
    pramana_proof_kid: str = Field(default="proof-2026-09", alias="PRAMANA_PROOF_KID")

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514", alias="ANTHROPIC_MODEL"
    )

    razorpay_key_id: str = Field(default="rzp_test_mock", alias="RAZORPAY_KEY_ID")
    razorpay_key_secret: str = Field(default="mock_secret_for_demo", alias="RAZORPAY_KEY_SECRET")

    allow_origins: str = Field(default="*", alias="ALLOW_ORIGINS")
    seed_demo_on_boot: bool = Field(default=True, alias="SEED_DEMO_ON_BOOT")

    ollama_host: str = Field(default="http://127.0.0.1:11434", alias="OLLAMA_HOST")
    ollama_model: str = Field(default="qwen3:1.7b", alias="OLLAMA_MODEL")

    # Set when keys were auto-generated for this process (not from env).
    ephemeral_keys: bool = False

    @field_validator("mock_mode", mode="before")
    @classmethod
    def _parse_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return True
        return str(v).strip().lower() in ("1", "true", "yes", "on")

    @model_validator(mode="after")
    def _autogen_keys_and_assert(self) -> Settings:
        ephemeral = False
        if not (self.pramana_seal_sk or "").strip():
            self.pramana_seal_sk = _generate_ed25519_sk_b64()
            ephemeral = True
            os.environ["PRAMANA_SEAL_SK"] = self.pramana_seal_sk
        if not (self.pramana_proof_sk or "").strip():
            self.pramana_proof_sk = _generate_ed25519_sk_b64()
            ephemeral = True
            os.environ["PRAMANA_PROOF_SK"] = self.pramana_proof_sk
        self.ephemeral_keys = ephemeral

        # Validate key length (raises if corrupt)
        _sk_raw(self.pramana_seal_sk)
        _sk_raw(self.pramana_proof_sk)

        kid = (self.razorpay_key_id or "").strip()
        if kid.startswith("rzp_live_"):
            raise RuntimeError(
                "Refusing to boot with Razorpay live keys (rzp_live_*). Test mode only."
            )
        if kid and not kid.startswith("rzp_test_"):
            raise RuntimeError(
                f"RAZORPAY_KEY_ID must start with rzp_test_ (got {kid!r})"
            )
        return self

    @property
    def cors_origins(self) -> list[str]:
        raw = (self.allow_origins or "*").strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def effective_mock(self) -> bool:
        if self.mock_mode:
            return True
        kid = self.razorpay_key_id or ""
        if not kid or kid == "rzp_test_mock" or kid.endswith("_mock"):
            return True
        if not (self.gemini_api_key or self.anthropic_api_key):
            # Sealer falls back to mock without LLM keys
            return True
        return False

    def seal_sk_raw(self) -> bytes:
        return _sk_raw(self.pramana_seal_sk)

    def proof_sk_raw(self) -> bytes:
        return _sk_raw(self.pramana_proof_sk)

    def seal_private_key(self) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(self.seal_sk_raw())

    def proof_private_key(self) -> Ed25519PrivateKey:
        return Ed25519PrivateKey.from_private_bytes(self.proof_sk_raw())

    def seal_public_raw(self) -> bytes:
        return _pk_raw_from_sk_b64(self.pramana_seal_sk)

    def proof_public_raw(self) -> bytes:
        return _pk_raw_from_sk_b64(self.pramana_proof_sk)

    def jwks(self) -> dict[str, Any]:
        """OKP / Ed25519 JWKS for /.well-known/pramana-jwks.json."""
        keys = []
        for kid, pk in (
            (self.pramana_seal_kid, self.seal_public_raw()),
            (self.pramana_proof_kid, self.proof_public_raw()),
        ):
            keys.append(
                {
                    "kty": "OKP",
                    "crv": "Ed25519",
                    "x": _b64url(pk),
                    "kid": kid,
                    "alg": "EdDSA",
                    "use": "sig",
                }
            )
        return {"keys": keys}

    def mode_label(self) -> str:
        return "mock" if self.effective_mock else "live-test"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()

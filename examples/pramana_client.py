"""Minimal Pramana HTTP client for integrators (clone-local)."""

from __future__ import annotations

from typing import Any

import httpx


class PramanaClient:
    """Sidecar client: seal → authorize → execute. DENY is HTTP 200."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        *,
        gemini_key: str | None = None,
        razorpay_key_id: str | None = None,
        razorpay_key_secret: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers: dict[str, str] = {"Accept": "application/json"}
        if gemini_key:
            self._headers["X-Pramana-Gemini-Key"] = gemini_key
        if razorpay_key_id:
            self._headers["X-Pramana-Razorpay-Key-Id"] = razorpay_key_id
        if razorpay_key_secret:
            self._headers["X-Pramana-Razorpay-Key-Secret"] = razorpay_key_secret
        self._timeout = timeout

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with httpx.Client(timeout=self._timeout, headers=self._headers) as client:
            resp = client.request(method, f"{self.base_url}{path}", **kwargs)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {"data": data}

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/healthz")

    def create_episode(self, utterance: str, *, mode: str = "PRAMANA_ON") -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/episodes",
            json={"utterance": utterance, "mode": mode, "force_mock": True},
        )

    def append_context(
        self,
        episode_id: str,
        *,
        content: str,
        taint: str = "MERCHANT_STRUCTURED",
        source_uri: str | None = None,
        role: str = "tool_result",
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "role": role,
            "taint": taint,
            "content": content,
        }
        if source_uri:
            body["source_uri"] = source_uri
        return self._request("POST", f"/v1/episodes/{episode_id}/context", json=body)

    def authorize(
        self,
        episode_id: str,
        action: dict[str, Any],
        provenance: dict[str, Any] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/actions/authorize",
            json={
                "episode_id": episode_id,
                "action": action,
                "provenance": provenance or {},
            },
        )

    def execute(self, decision_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/actions/execute",
            json={"decision_id": decision_id},
        )

    def get_proof(self, proof_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/proofs/{proof_id}")

    def verify(self, document: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/verify", json={"document": document})

    def dashboard(self) -> dict[str, Any]:
        return self._request("GET", "/v1/dashboard/summary")

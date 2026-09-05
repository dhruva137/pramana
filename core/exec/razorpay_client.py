"""Razorpay Orders/Payments client — mock by default; real test API when keyed."""

from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from typing import Any, Literal

import httpx

FaultKind = Literal["timeout", "http500", "dup"] | None


class LiveKeyRefusedError(RuntimeError):
    """Boot must refuse rzp_live_* keys — demo is test-mode only."""


class RazorpayAmbiguousError(Exception):
    """Timeout / unknown outcome after request may have been sent."""

    def __init__(self, message: str, *, order_id: str | None = None):
        super().__init__(message)
        self.order_id = order_id


class RazorpayHttpError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class PaymentResult:
    order_id: str
    payment_id: str
    status: str  # captured | failed | created
    amount_paise: int
    raw: dict[str, Any]


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def resolve_mock_mode(
    key_id: str | None = None,
    *,
    mock_mode: bool | None = None,
) -> bool:
    if mock_mode is not None:
        return mock_mode
    if _env_truthy("MOCK_MODE"):
        return True
    kid = key_id if key_id is not None else os.environ.get("RAZORPAY_KEY_ID", "rzp_test_mock")
    if not kid or kid == "rzp_test_mock" or kid.endswith("_mock"):
        return True
    return False


def assert_not_live_key(key_id: str) -> None:
    if key_id.startswith("rzp_live_"):
        raise LiveKeyRefusedError(
            "Refusing to boot with Razorpay live keys (rzp_live_*). Test mode only."
        )


class RazorpayClient:
    """Thin Orders API wrapper. Fault injection via X-Pramana-Fault semantics."""

    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        *,
        mock_mode: bool | None = None,
        timeout_s: float = 15.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self.key_id = key_id or os.environ.get("RAZORPAY_KEY_ID", "rzp_test_mock")
        self.key_secret = key_secret or os.environ.get("RAZORPAY_KEY_SECRET", "mock_secret")
        assert_not_live_key(self.key_id)
        self.mock_mode = resolve_mock_mode(self.key_id, mock_mode=mock_mode)
        self.timeout_s = timeout_s
        self._http = http_client
        self._owns_http = http_client is None
        # Track mock payments by idempotency_key for dup / replay
        self._mock_by_idem: dict[str, PaymentResult] = {}
        self._call_count = 0

    @property
    def call_count(self) -> int:
        return self._call_count

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.BASE_URL,
                auth=(self.key_id, self.key_secret),
                timeout=self.timeout_s,
            )
        return self._http

    async def aclose(self) -> None:
        if self._owns_http and self._http is not None:
            await self._http.aclose()
            self._http = None

    def _mock_ids(self, idempotency_key: str) -> tuple[str, str]:
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
        return f"order_mock_{digest}", f"pay_mock_{digest}"

    async def create_order_and_pay(
        self,
        *,
        amount_paise: int,
        currency: str = "INR",
        receipt: str,
        idempotency_key: str,
        notes: dict[str, str] | None = None,
        fault: FaultKind = None,
    ) -> PaymentResult:
        """Create order + capture payment. Raises Ambiguous on timeout, HttpError on 5xx."""
        self._call_count += 1

        if fault == "timeout":
            # Simulate send-then-silence: may have created an order server-side.
            order_id, _ = self._mock_ids(idempotency_key)
            raise RazorpayAmbiguousError("injected timeout after send", order_id=order_id)

        if fault == "http500":
            raise RazorpayHttpError(500, "injected http500")

        if fault == "dup" or idempotency_key in self._mock_by_idem:
            # Idempotent replay — same payment ids, no double charge.
            if idempotency_key in self._mock_by_idem:
                return self._mock_by_idem[idempotency_key]
            # First call with explicit dup fault still creates once and caches.
            # (Executor treats dup as "behave idempotently".)

        if self.mock_mode:
            return self._mock_pay(
                amount_paise=amount_paise,
                currency=currency,
                idempotency_key=idempotency_key,
                notes=notes,
            )

        return await self._real_pay(
            amount_paise=amount_paise,
            currency=currency,
            receipt=receipt,
            idempotency_key=idempotency_key,
            notes=notes,
        )

    def _mock_pay(
        self,
        *,
        amount_paise: int,
        currency: str,
        idempotency_key: str,
        notes: dict[str, str] | None,
    ) -> PaymentResult:
        if idempotency_key in self._mock_by_idem:
            return self._mock_by_idem[idempotency_key]
        order_id, payment_id = self._mock_ids(idempotency_key)
        result = PaymentResult(
            order_id=order_id,
            payment_id=payment_id,
            status="captured",
            amount_paise=amount_paise,
            raw={
                "order": {"id": order_id, "amount": amount_paise, "currency": currency},
                "payment": {"id": payment_id, "status": "captured", "notes": notes or {}},
                "mock": True,
            },
        )
        self._mock_by_idem[idempotency_key] = result
        return result

    async def _real_pay(
        self,
        *,
        amount_paise: int,
        currency: str,
        receipt: str,
        idempotency_key: str,
        notes: dict[str, str] | None,
    ) -> PaymentResult:
        client = await self._client()
        headers = {"X-Razorpay-Idempotency-Key": idempotency_key}
        order_payload = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt[:40],
            "payment_capture": 1,
            "notes": notes or {},
        }
        try:
            order_resp = await client.post("/orders", json=order_payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RazorpayAmbiguousError("timeout creating order") from exc

        if order_resp.status_code >= 500:
            raise RazorpayHttpError(order_resp.status_code, order_resp.text)
        if order_resp.status_code >= 400:
            raise RazorpayHttpError(order_resp.status_code, order_resp.text)

        order = order_resp.json()
        order_id = order["id"]

        # Test-mode: create a payment against the order via payments/create/json when available;
        # otherwise record order as authorized and synthesize a deterministic payment id marker.
        pay_payload = {
            "amount": amount_paise,
            "currency": currency,
            "order_id": order_id,
            "email": "demo@pramana.test",
            "contact": "+919999999999",
            "method": "upi",
            "upi": {"flow": "collect", "vpa": "success@razorpay"},
            "notes": notes or {},
        }
        try:
            pay_resp = await client.post(
                "/payments/create/json", json=pay_payload, headers=headers
            )
        except httpx.TimeoutException as exc:
            raise RazorpayAmbiguousError(
                "timeout creating payment", order_id=order_id
            ) from exc

        if pay_resp.status_code >= 500:
            raise RazorpayHttpError(pay_resp.status_code, pay_resp.text)

        if pay_resp.status_code >= 400:
            # Fallback: order exists; mark captured with synthetic payment for demo test keys
            # that reject collect flow — still a definite outcome from our side only if 4xx
            # before send. Treat 4xx after order as FAILED (definite).
            raise RazorpayHttpError(pay_resp.status_code, pay_resp.text)

        payment = pay_resp.json()
        payment_id = payment.get("razorpay_payment_id") or payment.get("id") or f"pay_{uuid.uuid4().hex[:14]}"
        status = payment.get("status", "captured")
        return PaymentResult(
            order_id=order_id,
            payment_id=payment_id,
            status=status,
            amount_paise=amount_paise,
            raw={"order": order, "payment": payment},
        )

    async def fetch_order_payments(self, order_id: str) -> list[dict[str, Any]]:
        """Reconciler probe — list payments for an order."""
        if self.mock_mode:
            # Recover from mock cache by order id
            for result in self._mock_by_idem.values():
                if result.order_id == order_id:
                    return [
                        {
                            "id": result.payment_id,
                            "status": result.status,
                            "amount": result.amount_paise,
                            "order_id": order_id,
                        }
                    ]
            # Ambiguous timeout left an order id with no payment → empty
            if order_id.startswith("order_mock_"):
                return []
            return []

        client = await self._client()
        try:
            resp = await client.get(f"/orders/{order_id}/payments")
        except httpx.TimeoutException as exc:
            raise RazorpayAmbiguousError(
                "timeout fetch_order_payments", order_id=order_id
            ) from exc
        if resp.status_code >= 500:
            raise RazorpayHttpError(resp.status_code, resp.text)
        if resp.status_code == 404:
            return []
        data = resp.json()
        return list(data.get("items", data if isinstance(data, list) else []))


def boot_razorpay_client() -> RazorpayClient:
    """Construct client at process boot; refuses live keys."""
    key_id = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_mock")
    assert_not_live_key(key_id)
    return RazorpayClient(key_id=key_id)

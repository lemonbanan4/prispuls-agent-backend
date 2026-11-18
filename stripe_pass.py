"""Black Friday Pass — Stripe checkout.session.completed + issued pass tokens."""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

import stripe

paid_checkout_sessions: set[str] = set()
pass_tokens: dict[str, dict[str, Any]] = {}


def stripe_secret_key() -> str | None:
    key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    return key or None


def webhook_secret() -> str | None:
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    return secret or None


def vip_access_code() -> str | None:
    code = os.getenv("VIP_ACCESS_CODE", "").strip()
    return code or None


def configure_stripe() -> None:
    key = stripe_secret_key()
    if key:
        stripe.api_key = key


def register_paid_session(session_id: str) -> None:
    paid_checkout_sessions.add(session_id)


def issue_pass_token(source: str) -> str:
    token = secrets.token_urlsafe(32)
    pass_tokens[token] = {"source": source, "issued_at": time.time()}
    return token


def pass_token_valid(token: str | None) -> bool:
    return bool(token and token in pass_tokens)


def token_for_session(session_id: str) -> str | None:
    for token, meta in pass_tokens.items():
        if meta.get("source") == f"stripe:{session_id}":
            return token
    return None


def confirm_session_paid(session_id: str) -> bool:
    if session_id in paid_checkout_sessions:
        return True
    key = stripe_secret_key()
    if not key:
        return False
    configure_stripe()
    try:
        session = stripe.checkout.Session.retrieve(session_id)
    except stripe.error.StripeError:
        return False
    if session.get("payment_status") == "paid":
        register_paid_session(session_id)
        return True
    return False


def grant_pass_for_session(session_id: str) -> str | None:
    if not confirm_session_paid(session_id):
        return None
    existing = token_for_session(session_id)
    if existing:
        return existing
    return issue_pass_token(f"stripe:{session_id}")


def verify_webhook(payload: bytes, sig_header: str | None) -> stripe.Event:
    secret = webhook_secret()
    if not secret:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not set")
    if not sig_header:
        raise ValueError("Missing Stripe-Signature header")
    try:
        return stripe.Webhook.construct_event(payload, sig_header, secret)
    except stripe.error.SignatureVerificationError as exc:
        raise ValueError("Invalid Stripe signature") from exc
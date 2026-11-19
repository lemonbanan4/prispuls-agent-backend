"""One free agent run per client IP every 24 hours (in-memory)."""

from __future__ import annotations

import time

DEMO_TTL_SECONDS = 24 * 60 * 60
DEMO_EXHAUSTED_MESSAGE = (
    "Du har redan använt din gratis testkörning. "
    "Lås upp obegränsade körningar med Black Friday-passet (79 kr)."
)

# ip -> unix timestamp when the free demo slot expires (demo was consumed)
demo_slots: dict[str, float] = {}


def client_ip_from_headers(x_forwarded_for: str | None, fallback_host: str | None) -> str:
    if x_forwarded_for:
        # Railway / proxies: client is the left-most address
        first = x_forwarded_for.split(",")[0].strip()
        if first:
            return first
    if fallback_host:
        return fallback_host
    return "unknown"


def _purge_expired(now: float) -> None:
    expired = [ip for ip, until in demo_slots.items() if until <= now]
    for ip in expired:
        del demo_slots[ip]


def free_demo_available(ip: str) -> bool:
    now = time.time()
    _purge_expired(now)
    until = demo_slots.get(ip)
    if until is None:
        return True
    return until <= now


def consume_free_demo(ip: str) -> None:
    demo_slots[ip] = time.time() + DEMO_TTL_SECONDS
"""Deterministic hashing helpers.

Hashes are the backbone of Groundrail's stale detection: a file hash, a snippet
hash, and a prompt hash let us prove whether evidence still matches the source.
"""

from __future__ import annotations

import hashlib


def sha256_text(text: str) -> str:
    """Return ``sha256:<hex>`` for the UTF-8 encoding of ``text``."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def sha256_bytes(data: bytes) -> str:
    """Return ``sha256:<hex>`` for raw ``data``."""
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def short(hash_value: str, length: int = 12) -> str:
    """Return a short, display-friendly form of a ``sha256:`` hash."""
    body = hash_value.split(":", 1)[-1]
    return body[:length]

"""Non-secret identifiers for configured access tokens."""

from __future__ import annotations

from hashlib import sha256


def token_unique_id(token: str) -> str:
    """Identify a token without exposing the credential as config-entry metadata."""
    return sha256(token.encode()).hexdigest()

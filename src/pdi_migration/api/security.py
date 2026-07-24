"""Shared API auth dependency (split from main.py so routers can import it
without a circular import)."""

import os

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional shared-secret auth: set PDI_MIGRATION_API_KEY to enforce it on
    mutating endpoints. Unset (the default) keeps local single-user use frictionless."""
    expected = os.environ.get("PDI_MIGRATION_API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid or missing X-API-Key header")

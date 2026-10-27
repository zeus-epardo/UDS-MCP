"""Structured, JSON-friendly results returned by :class:`uds_mcp.core.client.UdsClient`."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from udsoncan import Response


class UdsResult(BaseModel):
    """Outcome of one UDS request.

    ``ok`` is true for a positive response. A negative response carries ``nrc`` and
    ``nrc_name``; a transport problem (timeout, invalid response) carries ``error``.
    """

    service: str
    ok: bool
    request: str | None = None
    response: str | None = None
    nrc: int | None = None
    nrc_name: str | None = None
    error: str | None = None
    data: dict[str, Any] = {}


def nrc_name(code: int) -> str:
    return Response.Code.get_name(code)

"""Ticketing adapters: an explicit local mock and a configurable HTTP integration."""
from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from trackobit_assistant.config.settings import Settings
from trackobit_assistant.schemas.models import TicketResult

logger = logging.getLogger(__name__)


class LoggingTicketClient:
    """Safe local mock. It logs tickets but does not create them in Jira/HubSpot."""

    def create(self, summary: str, reason: str, metadata: dict[str, Any]) -> TicketResult:
        ticket_id = f"TRK-{uuid.uuid4().hex[:8].upper()}"
        logger.warning(
            "MOCK TICKET CREATED id=%s reason=%s summary=%s metadata_keys=%s",
            ticket_id, reason, summary, list(metadata),
        )
        return TicketResult(ticket_id=ticket_id, assigned_to=metadata.get("assigned_to"), summary=summary)


def _retryable_ticket_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    return isinstance(exc, (httpx.TimeoutException, httpx.NetworkError))


class HttpTicketClient:
    """Generic authorised ticket endpoint adapter; configure the contract to match your service."""

    def __init__(self, settings: Settings) -> None:
        if not settings.ticket_api_url:
            raise ValueError("TICKET_API_URL must be configured for HttpTicketClient")
        self.url = settings.ticket_api_url
        self.api_key = settings.ticket_api_key
        self.timeout = settings.ticket_api_timeout_seconds

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.2, min=0.2, max=1.0),
           retry=retry_if_exception(_retryable_ticket_error), reraise=True)
    def create(self, summary: str, reason: str, metadata: dict[str, Any]) -> TicketResult:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        response = httpx.post(
            self.url,
            json={"summary": summary, "reason": reason, "metadata": metadata},
            headers=headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json() if response.content else {}
        ticket_id = payload.get("ticket_id") or payload.get("id")
        if not ticket_id:
            raise ValueError("Ticket API response must include 'ticket_id' or 'id'")
        return TicketResult(
            ticket_id=str(ticket_id), status=str(payload.get("status", "created")),
            assigned_to=payload.get("assigned_to") or metadata.get("assigned_to"),
            summary=str(payload.get("summary") or summary),
        )

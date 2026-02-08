"""Webhook notification system for contradiction/supersession events.

Sends HTTP POST to registered webhook URLs when facts are superseded.
Webhook configs stored in a JSON file for persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_WEBHOOKS_FILE = Path(__file__).resolve().parent.parent / "data" / "webhooks.json"
WEBHOOK_TIMEOUT = 10.0


class WebhookManager:
    """Manages webhook registrations and sends notifications."""

    def __init__(self, storage_path: Path | None = None) -> None:
        self._path = storage_path or DEFAULT_WEBHOOKS_FILE
        self._webhooks: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._webhooks = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                self._webhooks = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._webhooks, indent=2))

    def list_webhooks(self) -> list[dict[str, Any]]:
        return list(self._webhooks)

    def add_webhook(self, url: str, events: list[str] | None = None, name: str = "") -> dict:
        """Register a webhook URL."""
        webhook = {
            "url": url,
            "name": name or url,
            "events": events or ["supersession"],
            "created_at": datetime.now(UTC).isoformat(),
            "active": True,
        }
        # Avoid duplicates by URL
        self._webhooks = [w for w in self._webhooks if w["url"] != url]
        self._webhooks.append(webhook)
        self._save()
        return webhook

    def remove_webhook(self, url: str) -> bool:
        before = len(self._webhooks)
        self._webhooks = [w for w in self._webhooks if w["url"] != url]
        if len(self._webhooks) < before:
            self._save()
            return True
        return False

    async def notify_supersession(
        self,
        old_id: str,
        old_statement: str,
        new_id: str,
        new_statement: str,
    ) -> list[dict[str, Any]]:
        """Send webhook notification for a supersession event."""
        payload = {
            "event": "supersession",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "old_event_id": old_id,
                "old_statement": old_statement,
                "new_event_id": new_id,
                "new_statement": new_statement,
            },
        }
        return await self._dispatch(payload, event_type="supersession")

    async def _dispatch(self, payload: dict, event_type: str) -> list[dict[str, Any]]:
        """Send payload to all active webhooks matching the event type."""
        results: list[dict[str, Any]] = []
        active = [
            w for w in self._webhooks if w.get("active") and event_type in w.get("events", [])
        ]

        if not active:
            return results

        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            for wh in active:
                try:
                    resp = await client.post(wh["url"], json=payload)
                    results.append(
                        {"url": wh["url"], "status": resp.status_code, "ok": resp.is_success}
                    )
                    logger.info("Webhook %s: %d", wh["url"], resp.status_code)
                except Exception as e:
                    results.append({"url": wh["url"], "status": 0, "ok": False, "error": str(e)})
                    logger.warning("Webhook %s failed: %s", wh["url"], e)

        return results

"""The few Gmail REST calls sync needs."""

from typing import Any

import httpx

from app.integrations.google import oauth

BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
METADATA_HEADERS = ["From", "To", "Cc", "Subject", "Date", "Message-ID"]


class HistoryExpired(Exception):
    """Gmail no longer has changes that far back; fall back to a recent re-scan."""


class GmailClient:
    def __init__(self, access_token: str):
        self._headers = {"Authorization": f"Bearer {access_token}"}

    async def _get(self, path: str, params: Any = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30, transport=oauth.transport) as client:
            resp = await client.get(f"{BASE}{path}", params=params, headers=self._headers)
        if resp.status_code == 404 and path == "/history":
            raise HistoryExpired()
        resp.raise_for_status()
        return resp.json()

    async def profile(self) -> dict[str, Any]:
        return await self._get("/profile")

    async def list_message_ids(self, query: str, limit: int) -> list[str]:
        ids: list[str] = []
        token = None
        while len(ids) < limit:
            params = {"q": query, "maxResults": min(100, limit - len(ids))}
            if token:
                params["pageToken"] = token
            page = await self._get("/messages", params)
            ids += [m["id"] for m in page.get("messages", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        return ids

    async def added_since(self, history_id: str) -> list[str]:
        """Message ids added after `history_id`, oldest first."""
        ids: list[str] = []
        token = None
        while True:
            params: list[tuple[str, str]] = [("startHistoryId", history_id), ("historyTypes", "messageAdded")]
            if token:
                params.append(("pageToken", token))
            page = await self._get("/history", params)
            for h in page.get("history", []):
                ids += [m["message"]["id"] for m in h.get("messagesAdded", [])]
            token = page.get("nextPageToken")
            if not token:
                return list(dict.fromkeys(ids))

    async def message(self, message_id: str, *, full: bool) -> dict[str, Any]:
        if full:
            return await self._get(f"/messages/{message_id}", {"format": "full"})
        params = [("format", "metadata")] + [("metadataHeaders", h) for h in METADATA_HEADERS]
        return await self._get(f"/messages/{message_id}", params)

"""Tavily search. Tavily fetches the pages, so Meyora never requests arbitrary URLs itself."""

import httpx

from app.integrations.web.base import TimeRange, Topic, WebResult, WebSearchError

URL = "https://api.tavily.com/search"

# Tests swap this for httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


class TavilyProvider:
    id = "tavily"

    def __init__(self, api_key: str):
        self._key = api_key

    async def search(
        self,
        query: str,
        *,
        topic: Topic = "general",
        time_range: TimeRange | None = None,
        max_results: int = 6,
        country: str | None = None,
        include_domains: list[str] | None = None,
    ) -> list[WebResult]:
        body = {
            "query": query[:400],
            "search_depth": "basic",  # 1 credit; "advanced" costs 2
            "topic": topic,
            "max_results": max(1, min(max_results, 10)),
            "include_answer": False,
            "include_raw_content": False,
        }
        if time_range:
            body["time_range"] = time_range
        if include_domains:
            body["include_domains"] = include_domains
        if country and topic == "general":  # Tavily only supports country boosting for general search
            body["country"] = country.lower()
        try:
            async with httpx.AsyncClient(timeout=25, transport=transport) as client:
                resp = await client.post(URL, json=body, headers={"Authorization": f"Bearer {self._key}"})
        except httpx.HTTPError as exc:
            raise WebSearchError("Web search couldn't be reached.") from exc
        if resp.status_code == 429 or resp.status_code == 432:
            raise WebSearchError("The web search allowance is used up for now.")
        if resp.status_code in (401, 403):
            raise WebSearchError("The web search key was rejected. Check TAVILY_API_KEY.")
        if resp.status_code >= 400:
            raise WebSearchError(f"Web search failed ({resp.status_code}).")
        return [
            WebResult(
                title=(r.get("title") or r.get("url") or "")[:300],
                url=r["url"],
                content=" ".join((r.get("content") or "").split())[:1200],
                score=float(r.get("score") or 0),
                published=r.get("published_date"),
            )
            for r in resp.json().get("results", [])
            if r.get("url", "").startswith(("http://", "https://"))
        ]

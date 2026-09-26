from dataclasses import dataclass
from typing import Literal, Protocol

Topic = Literal["general", "news"]
TimeRange = Literal["day", "week", "month", "year"]


@dataclass
class WebResult:
    title: str
    url: str
    content: str
    score: float = 0.0
    published: str | None = None

    @property
    def domain(self) -> str:
        from urllib.parse import urlparse

        return (urlparse(self.url).hostname or "").removeprefix("www.")


class WebSearchError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class WebSearchProvider(Protocol):
    id: str

    async def search(
        self, query: str, *, topic: Topic = "general", time_range: TimeRange | None = None, max_results: int = 6
    ) -> list[WebResult]: ...

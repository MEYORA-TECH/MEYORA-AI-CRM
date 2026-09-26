"""Turn Gmail's message JSON into plain fields. Attachments are noted, never stored."""

import base64
import html as html_lib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import getaddresses
from html.parser import HTMLParser
from typing import Any

MAX_BODY = 20_000
# Cut quoted history so we store (and embed) what this message actually says.
_QUOTE = re.compile(r"^(On .{5,200} wrote:|-{2,} ?Original Message ?-{2,}|From: .+ Sent: .+)$", re.M | re.I)


@dataclass
class Address:
    email: str
    name: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {"email": self.email, "name": self.name}


@dataclass
class Parsed:
    id: str
    thread_id: str
    subject: str
    from_: Address
    to: list[Address]
    cc: list[Address]
    sent_at: datetime
    snippet: str
    labels: list[str]
    rfc_message_id: str | None
    body_text: str = ""
    has_attachments: bool = False
    participants: list[Address] = field(default_factory=list)


def headers(msg: dict[str, Any]) -> dict[str, str]:
    return {h["name"].lower(): h["value"] for h in (msg.get("payload") or {}).get("headers", [])}


def addresses(value: str | None) -> list[Address]:
    out = []
    for name, email in getaddresses([value or ""]):
        email = email.strip().lower()
        if "@" in email:
            out.append(Address(email=email, name=name.strip() or None))
    return out


def parse(msg: dict[str, Any]) -> Parsed:
    h = headers(msg)
    sender = (addresses(h.get("from")) or [Address(email="unknown@unknown")])[0]
    to, cc = addresses(h.get("to")), addresses(h.get("cc"))
    seen: dict[str, Address] = {}
    for a in [sender, *to, *cc]:
        seen.setdefault(a.email, a)
    return Parsed(
        id=msg["id"],
        thread_id=msg.get("threadId", msg["id"]),
        subject=(h.get("subject") or "(no subject)")[:500],
        from_=sender,
        to=to,
        cc=cc,
        sent_at=datetime.fromtimestamp(int(msg.get("internalDate", "0")) / 1000, UTC),
        snippet=_unescape(msg.get("snippet", ""))[:500],
        labels=list(msg.get("labelIds", [])),
        rfc_message_id=h.get("message-id"),
        participants=list(seen.values()),
    )


def add_body(parsed: Parsed, full_msg: dict[str, Any]) -> Parsed:
    plain, html, attachments = [], [], False
    for part in _walk(full_msg.get("payload") or {}):
        if part.get("filename"):
            attachments = True
            continue
        data = (part.get("body") or {}).get("data")
        if not data:
            continue
        text = _decode(data)
        if part.get("mimeType") == "text/plain":
            plain.append(text)
        elif part.get("mimeType") == "text/html":
            html.append(text)
    body = "\n".join(plain) if plain else _html_to_text("\n".join(html))
    parsed.body_text = _trim_quotes(body)[:MAX_BODY]
    parsed.has_attachments = attachments
    return parsed


def _walk(part: dict[str, Any]):
    yield part
    for child in part.get("parts") or []:
        yield from _walk(child)


def _decode(data: str) -> str:
    raw = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
    return raw.decode("utf-8", errors="replace")


def _trim_quotes(text: str) -> str:
    text = text.replace("\r\n", "\n")
    match = _QUOTE.search(text)
    if match and match.start() > 0:
        text = text[: match.start()]
    lines = [ln for ln in text.split("\n") if not ln.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("br", "p", "div", "tr", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html)
    return re.sub(r"[ \t]+", " ", "".join(p.parts))


def _unescape(text: str) -> str:
    return html_lib.unescape(text)

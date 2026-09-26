"""A fake Google (OAuth, ID tokens, Gmail) for tests. No network."""

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.integrations.google import oauth

CLIENT_ID = "test-client.apps.googleusercontent.com"


def b64(text_: str) -> str:
    return base64.urlsafe_b64encode(text_.encode()).decode().rstrip("=")


class FakeGoogle:
    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.identity = {"sub": "google-sub-1", "email": "olivia@acme.test", "email_verified": True,
                         "name": "Olivia Google", "given_name": "Olivia"}
        self.nonces: dict[str, str] = {}  # code -> nonce
        self.scope = "openid email https://www.googleapis.com/auth/gmail.readonly"
        self.messages: dict[str, dict] = {}
        self.history: list[str] = []
        self.history_id = 100
        self.history_expired = False
        self.refresh_ok = True
        self.calls: list[str] = []
        self.revoked: list[str] = []

    def authorize(self, auth_url: str, code: str = "code-1") -> dict:
        """What Google's consent screen would do: remember the nonce, return code + state."""
        params = {k: v[0] for k, v in parse_qs(urlparse(auth_url).query).items()}
        self.nonces[code] = params["nonce"]
        return {"code": code, "state": params["state"]}

    def id_token(self, nonce: str) -> str:
        now = int(time.time())
        claims = {**self.identity, "iss": "https://accounts.google.com", "aud": CLIENT_ID, "iat": now, "exp": now + 600,
                  "nonce": nonce}
        return jwt.encode(claims, self.key, algorithm="RS256", headers={"kid": "k1"})

    def add_message(self, mid: str, *, sender: str, to: str, subject: str, body: str, thread: str | None = None,
                    ts: int | None = None):
        self.messages[mid] = {
            "id": mid, "threadId": thread or f"t-{mid}", "labelIds": ["INBOX"], "snippet": body[:60],
            "internalDate": str(ts or int(time.time() * 1000)),
            "payload": {"mimeType": "multipart/alternative", "headers": [
                {"name": "From", "value": sender}, {"name": "To", "value": to},
                {"name": "Subject", "value": subject}, {"name": "Message-ID", "value": f"<{mid}@mail>"}],
                "parts": [{"mimeType": "text/plain", "body": {"data": b64(body)}},
                          {"mimeType": "text/html", "body": {"data": b64(f"<p>{body}</p>")}}]},
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        path = request.url.path
        self.calls.append(f"{request.method} {path}")
        if url.startswith(oauth.CERTS_URL):
            jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key()))
            return httpx.Response(200, json={"keys": [{**jwk, "kid": "k1", "alg": "RS256", "use": "sig"}]})
        if url.startswith(oauth.TOKEN_URL):
            form = parse_qs(request.content.decode())
            if form["grant_type"][0] == "refresh_token":
                return httpx.Response(200, json={"access_token": "at-2"}) if self.refresh_ok else httpx.Response(400, json={"error": "invalid_grant"})
            code = form["code"][0]
            assert form["code_verifier"][0], "PKCE verifier must be sent"
            return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-secret",
                                             "scope": self.scope, "id_token": self.id_token(self.nonces[code])})
        if url.startswith(oauth.REVOKE_URL):
            self.revoked.append(parse_qs(request.content.decode())["token"][0])
            return httpx.Response(200)
        if path.endswith("/users/me/profile"):
            return httpx.Response(200, json={"emailAddress": "olivia@acme.test", "historyId": str(self.history_id)})
        if path.endswith("/users/me/messages"):
            return httpx.Response(200, json={"messages": [{"id": m} for m in self.messages]})
        if path.endswith("/users/me/history"):
            if self.history_expired:
                return httpx.Response(404, json={"error": "not found"})
            return httpx.Response(200, json={"history": [{"messagesAdded": [{"message": {"id": m}}]} for m in self.history]})
        if "/users/me/messages/" in path:
            msg = self.messages[path.rsplit("/", 1)[-1]]
            if request.url.params.get("format") == "metadata":
                return httpx.Response(200, json={**msg, "payload": {"headers": msg["payload"]["headers"]}})
            return httpx.Response(200, json=msg)
        return httpx.Response(404)

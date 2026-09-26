# Phase 4 — Google sign-in & Gmail

Date: 2026-09-26 · Decisions from chat:

1. **Toggle layers.** `GOOGLE_AUTH_ENABLED` adds "Continue with Google" next
   to email/password; `GMAIL_ENABLED` adds mailbox connection. Both off by
   default; with them off the app behaves exactly as before.
2. **The database is the source of truth for email.** Only CRM-related
   messages (a participant is a CRM contact, or is at a CRM company's domain)
   are stored, inbound and sent. Screens and the AI read from Postgres. Gmail
   is only asked "what changed since history id X?" and only new messages are
   downloaded.
3. **Visibility:** synced emails are visible to everyone in the organization.

Constraint recorded: Gmail read access is a Google *restricted* scope. Until
the app is verified, use an Internal (Workspace) app, or External/Testing
where connections expire after 7 days.

## Units

| Unit | Responsibility |
|---|---|
| `core/crypto.py` | AES-GCM encryption for stored OAuth tokens (`ENCRYPTION_KEY`) |
| `integrations/google/oauth.py` | Authorization URLs with state + PKCE + nonce, code exchange, ID-token verification against Google's JWKS |
| `integrations/gmail/client.py` | Minimal Gmail REST client (profile, list, get, history), token refresh |
| `integrations/gmail/parse.py` | Headers, addresses, plain-text body from MIME (HTML fallback), no attachments stored |
| `integrations/gmail/sync.py` | Initial sync (last N days, capped) and incremental sync via `history.list`; metadata first, full message only when CRM-related; history-expired fallback |
| `services/email_matching.py` | Participant → contacts by email, companies by domain (free-mail domains ignored) |
| Worker scheduler | Every minute, queue `gmail_sync` for accounts due (interval 5 min) |

Mail provider logic stays out of the AI service (Rule 8); the AI reads
stored emails through tools like any other CRM data.

## Data

- `users.google_sub` (unique).
- `oauth_states` (global): hashed state, purpose (login / gmail), PKCE
  verifier, nonce, user/org for gmail, expiry 10 min, single use.
- `mail_accounts` (RLS): user, provider, address, encrypted refresh token,
  scopes, history id, status, last sync/error, sync window.
- `email_threads` (RLS): account, provider thread id, subject, snippet,
  participants, company_ids[], contact_ids[], last_message_at, count.
- `email_messages` (RLS): thread, account, provider message id (unique per
  account), RFC Message-ID, direction, from, to/cc, subject, sent_at,
  snippet, body_text (≤ 20k chars), labels, has_attachments,
  contact_ids[], company_ids[].

## Flows

- **Google sign-in:** `/api/auth/google/start` → Google → `/callback`:
  verify ID token (iss, aud, exp, nonce, `email_verified`), then match by
  `google_sub`, else link to the existing user with that verified email,
  else create the user and a workspace named after them. A refresh cookie
  is set and the browser returns to `/auth/google` which calls `/refresh`.
  No token ever appears in a URL.
- **Connect Gmail:** authenticated `POST /api/integrations/gmail/connect`
  returns the Google URL; callback stores the encrypted refresh token and
  queues the first sync. Disconnect revokes the token at Google and deletes
  it; stored emails stay.

## API

`GET /api/auth/providers`, `GET /api/auth/google/start`,
`GET /api/auth/google/callback`, `GET|POST|DELETE /api/integrations/gmail…`,
`POST /api/integrations/gmail/sync`, `GET /api/emails/threads` (filters:
q, contact, company), `GET /api/emails/threads/{id}`. Timeline includes
emails.

## AI

Tools `search_emails` and `get_email_thread` (CRM data class → trusted
providers only; content wrapped as untrusted data). Thread view offers
"Summarise" and "Draft a reply" that open the assistant with that thread in
context. Sending stays in Phase 6 with confirmation.

## Testing

All Google endpoints mocked with `httpx.MockTransport`; a test RSA key signs
ID tokens served from a mocked JWKS. Covers state/CSRF, ID-token checks,
account linking, token encryption, CRM-only filtering, matching, incremental
sync and history expiry, dedupe, email tenancy, and the email tools.

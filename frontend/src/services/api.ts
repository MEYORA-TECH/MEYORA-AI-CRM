/**
 * Fetch wrapper for the Meyora API.
 *
 * The access token lives only in memory. The refresh token is an httpOnly
 * cookie the browser sends to /api/auth/refresh; a 401 triggers one silent
 * refresh (shared between concurrent requests), then the request is retried.
 */

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

type Query = Record<string, string | number | boolean | string[] | null | undefined>;

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
let onSessionExpired: (() => void) | null = null;
let onTokenRefreshed: ((body: unknown) => void) | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

export const getAccessToken = () => accessToken;

export function configureSession(opts: {
  onExpired: () => void;
  onRefreshed: (body: unknown) => void;
}) {
  onSessionExpired = opts.onExpired;
  onTokenRefreshed = opts.onRefreshed;
}

function buildUrl(path: string, query?: Query) {
  const url = new URL(`/api${path}`, window.location.origin);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => url.searchParams.append(key, v));
    else url.searchParams.set(key, String(value));
  }
  return url.toString();
}

async function parseError(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const err = body?.error ?? {};
    return new ApiError(res.status, err.code ?? "error", err.message ?? res.statusText, err.details);
  } catch {
    return new ApiError(res.status, "error", res.statusText || "Request failed");
  }
}

export async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const res = await fetch("/api/auth/refresh", {
          method: "POST",
          credentials: "include",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        if (!res.ok) return false;
        const body = await res.json();
        accessToken = body.access_token;
        onTokenRefreshed?.(body);
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => (refreshing = null), 0);
      }
    })();
  }
  return refreshing;
}

export async function request<T>(
  method: "GET" | "POST" | "PATCH" | "DELETE",
  path: string,
  opts: { body?: unknown; query?: Query; retry?: boolean } = {},
): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "XMLHttpRequest" };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  const res = await fetch(buildUrl(path, opts.query), {
    method,
    headers,
    credentials: "include",
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
  });

  if (res.status === 401 && opts.retry !== false && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(method, path, { ...opts, retry: false });
    onSessionExpired?.();
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body: body ?? {} }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  delete: (path: string) => request<void>("DELETE", path),
};

/** Turns an API validation error into a short human message. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    if (Array.isArray(err.details) && err.details.length) {
      const first = err.details[0] as { msg?: string; message?: string; loc?: string[]; field?: string };
      const field = first.field ?? first.loc?.[first.loc.length - 1];
      const msg = first.message ?? first.msg;
      if (msg) return field ? `${humanize(String(field))}: ${msg}` : msg;
    }
    return err.message;
  }
  return "Couldn't reach Meyora. Check your connection and try again.";
}

function humanize(field: string) {
  return field.replace(/_id$/, "").replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

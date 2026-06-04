// Fetch helper for the REAL parent + child auth backend (signup, login, COPPA consent at child
// creation, child sessions). Unlike the legacy demo client (`parent.ts`, parentDemo.ts), these
// endpoints are LIVE and session-cookie based:
//
//   • Every request sends `credentials: 'include'` so the HttpOnly session cookie flows.
//   • Every mutating request (POST/DELETE) carries the double-submit CSRF token: the backend sets a
//     readable `wm_csrf` cookie, and we echo it back in the `X-CSRF-Token` header.
//
// All paths are same-origin (`/parent/*`, `/child/*`): in production CloudFront routes `/parent/*`
// and `/child/*` to the ALB → Fargate (the bare `/parent` SPA route stays on S3); in LOCAL dev
// vite.config.ts proxies `/parent/` and `/child` to the FastAPI server. Both are wired.
//
// On a non-2xx response this throws the shared `ApiError` carrying the status (and, when the body
// carries a `detail`/`message`, that text) so callers can branch on 400/401/409/423 etc.

import { ApiError } from './index';

/** Read a readable (non-HttpOnly) cookie by name from `document.cookie`, or null if absent. */
function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  const parts = document.cookie ? document.cookie.split('; ') : [];
  for (const part of parts) {
    if (part.startsWith(prefix)) {
      return decodeURIComponent(part.slice(prefix.length));
    }
  }
  return null;
}

/** The CSRF cookie the backend sets; echoed as `X-CSRF-Token` on mutating requests. */
const CSRF_COOKIE = 'wm_csrf';
const CSRF_HEADER = 'X-CSRF-Token';

/** Pull the human-readable error text out of a parsed JSON error body, if any. */
function messageFromBody(body: unknown, fallback: string): string {
  if (body !== null && typeof body === 'object') {
    const rec = body as Record<string, unknown>;
    // FastAPI puts validation/HTTP-exception text in `detail`; some handlers use `message`.
    const detail = rec['detail'] ?? rec['message'];
    if (typeof detail === 'string' && detail.trim() !== '') return detail;
  }
  return fallback;
}

/** Parse a response body as JSON, tolerating an empty body (204) by returning null. */
async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (text.trim() === '') return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

async function request<T>(
  method: 'GET' | 'POST' | 'DELETE',
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['content-type'] = 'application/json';
  // CSRF on any state-changing verb (the GET endpoints don't need it).
  if (method !== 'GET') {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf !== null) headers[CSRF_HEADER] = csrf;
  }
  const response = await fetch(path, {
    method,
    credentials: 'include',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const parsed = await parseBody(response);
    throw new ApiError(
      response.status,
      messageFromBody(parsed, `${method} ${path} failed (${String(response.status)})`),
    );
  }
  // 204 / empty bodies parse to null; callers that expect a body type cast through unknown.
  return (await parseBody(response)) as T;
}

/* ── Verbs (credentials always included; CSRF injected on mutations) ── */

export function getJson<T>(path: string): Promise<T> {
  return request<T>('GET', path);
}

export function postJson<T>(path: string, body?: unknown): Promise<T> {
  return request<T>('POST', path, body ?? {});
}

export function deleteJson<T>(path: string): Promise<T> {
  return request<T>('DELETE', path);
}

/* ──────────────────────────────────────────────────────────────────────────
   Typed endpoint wrappers for the parent + child auth surface.
   ────────────────────────────────────────────────────────────────────────── */

/** The signed-in parent (returned by signup / login / google / me). */
export interface ParentAccount {
  email: string;
  email_verified: boolean;
}

/** A child as listed under the parent's household. */
export interface ChildAccount {
  public_id: string;
  display_name: string;
  grade_level: number;
  locale: 'en' | 'es-MX';
}

/** The created-child receipt (the login to share). */
export interface CreatedChild {
  public_id: string;
  username: string;
}

/** The active child after start-session / child login (the cookie is now a CHILD session). */
export interface ChildSession {
  public_id: string;
  display_name: string;
}

export interface SignupInput {
  email: string;
  password: string;
}

export interface CreateChildInput {
  display_name: string;
  grade_level: number;
  locale: 'en' | 'es-MX';
  username: string;
  pin: string;
}

export interface ChildLoginInput {
  username: string;
  pin: string;
}

/** POST /parent/signup — 201 (sets cookies). 400 weak password, 409 account exists. */
export function parentSignup(input: SignupInput): Promise<ParentAccount> {
  return postJson<ParentAccount>('/parent/signup', input);
}

/** POST /parent/login — 200. 401 invalid credentials. */
export function parentLogin(input: SignupInput): Promise<ParentAccount> {
  return postJson<ParentAccount>('/parent/login', input);
}

/** POST /parent/google — 200. Exchanges a Google ID token for a parent session. */
export function parentGoogle(idToken: string): Promise<ParentAccount> {
  return postJson<ParentAccount>('/parent/google', { id_token: idToken });
}

/** GET /parent/me — 200 (signed in) or 401 (not). */
export function parentMe(): Promise<ParentAccount> {
  return getJson<ParentAccount>('/parent/me');
}

/** POST /parent/logout — 204 (needs CSRF). */
export function parentLogout(): Promise<null> {
  return postJson<null>('/parent/logout');
}

/** POST /parent/children — 201 {public_id, username}. 400 bad pin, 409 username in use. */
export function createChild(input: CreateChildInput): Promise<CreatedChild> {
  return postJson<CreatedChild>('/parent/children', input);
}

/** GET /parent/children — the household's children. */
export function listChildren(): Promise<ChildAccount[]> {
  return getJson<ChildAccount[]>('/parent/children');
}

/** POST /parent/children/{public_id}/reset-pin — 204. */
export function resetChildPin(publicId: string, pin: string): Promise<null> {
  return postJson<null>(`/parent/children/${encodeURIComponent(publicId)}/reset-pin`, { pin });
}

/** DELETE /parent/children/{public_id} — 204. */
export function deleteChild(publicId: string): Promise<null> {
  return deleteJson<null>(`/parent/children/${encodeURIComponent(publicId)}`);
}

/** POST /parent/children/{public_id}/start-session — switch the cookie to a CHILD session. */
export function startChildSession(publicId: string): Promise<ChildSession> {
  return postJson<ChildSession>(`/parent/children/${encodeURIComponent(publicId)}/start-session`);
}

/** POST /parent/children/{public_id}/sign-out-everywhere — 204. */
export function signOutChildEverywhere(publicId: string): Promise<null> {
  return postJson<null>(`/parent/children/${encodeURIComponent(publicId)}/sign-out-everywhere`);
}

/** POST /child/login — 200 (cookie now a child session). 401 invalid, 423 locked. */
export function childLogin(input: ChildLoginInput): Promise<ChildSession> {
  return postJson<ChildSession>('/child/login', input);
}

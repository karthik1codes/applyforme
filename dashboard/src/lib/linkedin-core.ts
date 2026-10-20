import crypto from "node:crypto";
import type Database from "better-sqlite3";

/**
 * Pure OAuth/SQLite core for the LinkedIn connector.  No Next.js imports, so
 * the behaviour can be tested with an in-memory SQLite database and a mocked
 * fetch.  The dashboard wrapper (linkedin.ts) supplies the real DB/session.
 *
 * Official capabilities only: LinkedIn's confidential-client OAuth 2.0
 * authorization-code flow, OpenID Connect scopes `openid profile email`, and
 * GET /v2/userinfo.  LinkedIn has no public job-search, saved-job, Easy Apply,
 * or application-submit API.
 */

export const LINKEDIN_SCOPES = "openid profile email";
export const LINKEDIN_AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization";
export const LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken";
export const LINKEDIN_USERINFO_URL = "https://api.linkedin.com/v2/userinfo";

const STATE_TTL_MS = 10 * 60 * 1000;

export type LinkedInToken = {
  access_token?: string;
  expires_in?: number;
  refresh_token?: string;
  refresh_token_expires_in?: number;
  scope?: string;
  token_type?: string;
  error?: string;
  error_description?: string;
};

export type LinkedInUserInfo = {
  sub?: string;
  name?: string;
  given_name?: string;
  family_name?: string;
  picture?: string;
  email?: string;
  email_verified?: boolean;
};

export type LinkedInConnection = {
  userId: string;
  memberId: string | null;
  displayName: string | null;
  email: string | null;
  picture: string | null;
  scope: string | null;
  connectedAt: string | null;
  expiresAt: string | null;
  expired: boolean;
  lastError: string;
};

export type LinkedInConfig = {
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  tokenKey: Buffer;
};

export type ResolvedLinkedInConfig = {
  config: LinkedInConfig | null;
  error: string | null;
};

type FetchImpl = typeof fetch;

function keyFromBase64(raw: string | undefined): Buffer {
  if (!raw?.trim()) throw new Error("LINKEDIN_TOKEN_KEY is not set");
  const key = Buffer.from(raw.trim(), "base64");
  if (key.length !== 32) throw new Error("LINKEDIN_TOKEN_KEY must be base64 for exactly 32 bytes");
  return key;
}

export function linkedinRedirectUri(env: NodeJS.ProcessEnv = process.env): string {
  const explicit = env.LINKEDIN_REDIRECT_URI?.trim();
  if (explicit) return explicit;
  const base = (env.APP_URL || env.AUTH_URL || "http://localhost:3000").replace(/\/$/, "");
  return `${base}/api/linkedin/callback`;
}

export function resolveLinkedInConfig(env: NodeJS.ProcessEnv = process.env): ResolvedLinkedInConfig {
  const clientId = env.LINKEDIN_CLIENT_ID?.trim() || "";
  const clientSecret = env.LINKEDIN_CLIENT_SECRET?.trim() || "";
  if (!clientId) return { config: null, error: "LINKEDIN_CLIENT_ID is not set" };
  if (!clientSecret) return { config: null, error: "LINKEDIN_CLIENT_SECRET is not set" };
  let tokenKey: Buffer;
  try {
    tokenKey = keyFromBase64(env.LINKEDIN_TOKEN_KEY);
  } catch (e) {
    return { config: null, error: e instanceof Error ? e.message : "LINKEDIN_TOKEN_KEY is invalid" };
  }
  return {
    config: { clientId, clientSecret, redirectUri: linkedinRedirectUri(env), tokenKey },
    error: null,
  };
}

/** AES-256-GCM. The database only ever stores this envelope, never a raw token. */
export function encryptToken(plain: string, tokenKey: Buffer): string {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv("aes-256-gcm", tokenKey, iv);
  const body = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  return [
    "v1",
    iv.toString("base64url"),
    cipher.getAuthTag().toString("base64url"),
    body.toString("base64url"),
  ].join(".");
}

export function decryptToken(payload: string | null | undefined, tokenKey: Buffer): string {
  if (!payload) throw new Error("No token is stored");
  const [version, ivB64, tagB64, bodyB64] = payload.split(".");
  if (version !== "v1" || !ivB64 || !tagB64 || !bodyB64) throw new Error("Stored token envelope is invalid");
  const decipher = crypto.createDecipheriv("aes-256-gcm", tokenKey, Buffer.from(ivB64, "base64url"));
  decipher.setAuthTag(Buffer.from(tagB64, "base64url"));
  return Buffer.concat([decipher.update(Buffer.from(bodyB64, "base64url")), decipher.final()]).toString("utf8");
}

const sha256 = (value: string) => crypto.createHash("sha256").update(value).digest("hex");

export function buildAuthorizeUrl(args: {
  clientId: string;
  redirectUri: string;
  state: string;
  scope?: string;
}): string {
  const url = new URL(LINKEDIN_AUTHORIZE_URL);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("client_id", args.clientId);
  url.searchParams.set("redirect_uri", args.redirectUri);
  url.searchParams.set("state", args.state);
  url.searchParams.set("scope", args.scope ?? LINKEDIN_SCOPES);
  // LinkedIn's web authorization-code flow is a confidential-client flow.
  // PKCE is reserved for the separate native/loopback endpoint and LinkedIn
  // rejects PKCE with OpenID scopes.  CSRF protection is the per-user state.
  return url.toString();
}

/** Create a single-use, per-user OAuth state. */
export function createStateRecord(
  d: Database.Database,
  userId: string,
  opts: { now?: Date; ttlMs?: number } = {},
): { state: string } {
  const state = crypto.randomBytes(32).toString("base64url");
  const now = opts.now ?? new Date();
  const expires = new Date(now.getTime() + (opts.ttlMs ?? STATE_TTL_MS));
  // Opportunistic cleanup only; other unexpired states are untouched.
  d.prepare("DELETE FROM linkedin_oauth_states WHERE expires_at < ?").run(
    new Date(now.getTime() - 864e5).toISOString(),
  );
  d.prepare(
    "INSERT INTO linkedin_oauth_states (state_hash, user_id, created_at, expires_at) VALUES (?,?,?,?)",
  ).run(sha256(state), userId, now.toISOString(), expires.toISOString());
  return { state };
}

/**
 * Atomically consume a state for this exact user. Returns false for unknown,
 * expired, reused, or cross-user states.
 */
export function consumeStateRecord(
  d: Database.Database,
  state: string,
  userId: string,
  now: Date = new Date(),
): boolean {
  if (!state || state.length > 300) return false;
  const hash = sha256(state);
  const row = d
    .prepare("SELECT expires_at, consumed_at FROM linkedin_oauth_states WHERE state_hash=? AND user_id=?")
    .get(hash, userId) as { expires_at: string; consumed_at: string | null } | undefined;
  if (!row || row.consumed_at) return false;
  if (new Date(row.expires_at).getTime() < now.getTime()) return false;
  const upd = d
    .prepare("UPDATE linkedin_oauth_states SET consumed_at=? WHERE state_hash=? AND consumed_at IS NULL")
    .run(now.toISOString(), hash);
  return upd.changes === 1;
}

export function expiresAtFrom(seconds: number | undefined, nowMs = Date.now()): string | null {
  if (!seconds || seconds <= 0) return null;
  return new Date(nowMs + seconds * 1000).toISOString();
}

export async function tokenRequest(
  config: LinkedInConfig,
  params: Record<string, string>,
  fetchImpl: FetchImpl = fetch,
): Promise<LinkedInToken> {
  const body = new URLSearchParams({
    client_id: config.clientId,
    client_secret: config.clientSecret,
    ...params,
  });
  const r = await fetchImpl(LINKEDIN_TOKEN_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });
  const json = (await r.json().catch(() => ({}))) as LinkedInToken;
  if (!r.ok || !json.access_token) {
    const reason = json.error_description || json.error || `LinkedIn token endpoint returned ${r.status}`;
    throw new Error(reason.slice(0, 240));
  }
  return json;
}

export async function exchangeCode(
  config: LinkedInConfig,
  code: string,
  fetchImpl: FetchImpl = fetch,
): Promise<LinkedInToken> {
  return tokenRequest(
    config,
    {
      grant_type: "authorization_code",
      code,
      redirect_uri: config.redirectUri,
    },
    fetchImpl,
  );
}

export async function fetchUserInfo(
  accessToken: string,
  fetchImpl: FetchImpl = fetch,
): Promise<{ status: number; info: LinkedInUserInfo }> {
  const r = await fetchImpl(LINKEDIN_USERINFO_URL, {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
    signal: AbortSignal.timeout(20_000),
  });
  const info = (await r.json().catch(() => ({}))) as LinkedInUserInfo;
  return { status: r.status, info };
}

function displayNameFrom(info: LinkedInUserInfo): string | null {
  if (info.name) return info.name;
  return [info.given_name, info.family_name].filter(Boolean).join(" ") || null;
}

export function getConnectionRecord(d: Database.Database, userId: string): LinkedInConnection | null {
  const r = d.prepare("SELECT * FROM linkedin_connections WHERE user_id=?").get(userId) as
    | {
        user_id: string;
        member_id: string | null;
        display_name: string | null;
        email: string | null;
        picture: string | null;
        scope: string | null;
        expires_at: string | null;
        connected_at: string | null;
        last_error: string | null;
      }
    | undefined;
  if (!r) return null;
  return {
    userId: r.user_id,
    memberId: r.member_id,
    displayName: r.display_name,
    email: r.email,
    picture: r.picture,
    scope: r.scope,
    connectedAt: r.connected_at,
    expiresAt: r.expires_at,
    expired: !!r.expires_at && new Date(r.expires_at).getTime() <= Date.now(),
    lastError: r.last_error ?? "",
  };
}

export function saveConnectionRecord(
  d: Database.Database,
  userId: string,
  token: LinkedInToken,
  info: LinkedInUserInfo,
  refreshToken: string | null,
  tokenKey: Buffer,
  now: Date = new Date(),
): LinkedInConnection {
  const nowIso = now.toISOString();
  d.prepare(
    `INSERT INTO linkedin_connections
      (user_id, member_id, display_name, email, picture, scope, token_type,
       access_token_enc, refresh_token_enc, expires_at, connected_at, updated_at, last_error)
     VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL)
     ON CONFLICT(user_id) DO UPDATE SET
       member_id=excluded.member_id, display_name=excluded.display_name, email=excluded.email,
       picture=excluded.picture, scope=excluded.scope, token_type=excluded.token_type,
       access_token_enc=excluded.access_token_enc, refresh_token_enc=excluded.refresh_token_enc,
       expires_at=excluded.expires_at, updated_at=excluded.updated_at, last_error=NULL`,
  ).run(
    userId,
    info.sub ?? null,
    displayNameFrom(info),
    info.email ?? null,
    info.picture ?? null,
    token.scope ?? LINKEDIN_SCOPES,
    token.token_type ?? "Bearer",
    encryptToken(token.access_token!, tokenKey),
    refreshToken ? encryptToken(refreshToken, tokenKey) : null,
    expiresAtFrom(token.expires_in, now.getTime()),
    nowIso,
    nowIso,
  );
  const connection = getConnectionRecord(d, userId);
  if (!connection) throw new Error("LinkedIn connection could not be saved");
  return connection;
}

export function setConnectionErrorRecord(d: Database.Database, userId: string, message: string): void {
  d.prepare("UPDATE linkedin_connections SET last_error=?, updated_at=? WHERE user_id=?").run(
    message.slice(0, 500),
    new Date().toISOString(),
    userId,
  );
}

export async function connectFromCode(
  d: Database.Database,
  userId: string,
  config: LinkedInConfig,
  code: string,
  fetchImpl: FetchImpl = fetch,
): Promise<LinkedInConnection> {
  const token = await exchangeCode(config, code, fetchImpl);
  const { status, info } = await fetchUserInfo(token.access_token!, fetchImpl);
  if (status !== 200 || !info.sub) {
    throw new Error(`LinkedIn userinfo returned ${status}; the token may not include openid profile email`);
  }
  return saveConnectionRecord(d, userId, token, info, token.refresh_token ?? null, config.tokenKey);
}

/**
 * Re-read /v2/userinfo. If the access token is rejected and LinkedIn issued a
 * refresh token (approved apps only), refresh once and retry.
 */
export async function refreshConnectionRecord(
  d: Database.Database,
  userId: string,
  config: LinkedInConfig,
  fetchImpl: FetchImpl = fetch,
): Promise<LinkedInConnection> {
  const raw = d
    .prepare("SELECT access_token_enc, refresh_token_enc FROM linkedin_connections WHERE user_id=?")
    .get(userId) as { access_token_enc: string | null; refresh_token_enc: string | null } | undefined;
  if (!raw) throw new Error("LinkedIn is not connected");

  let accessToken: string;
  try {
    accessToken = decryptToken(raw.access_token_enc, config.tokenKey);
  } catch {
    setConnectionErrorRecord(d, userId, "Stored LinkedIn token cannot be decrypted; reconnect.");
    throw new Error("Stored LinkedIn token cannot be decrypted; reconnect LinkedIn");
  }

  const result = await fetchUserInfo(accessToken, fetchImpl);
  if (result.status === 401 && raw.refresh_token_enc) {
    try {
      const refreshToken = decryptToken(raw.refresh_token_enc, config.tokenKey);
      const token = await tokenRequest(config, { grant_type: "refresh_token", refresh_token: refreshToken }, fetchImpl);
      const info = await fetchUserInfo(token.access_token!, fetchImpl);
      if (info.status !== 200 || !info.info.sub) throw new Error(`LinkedIn userinfo returned ${info.status}`);
      return saveConnectionRecord(d, userId, token, info.info, token.refresh_token ?? refreshToken, config.tokenKey);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "LinkedIn token refresh failed";
      setConnectionErrorRecord(d, userId, `${msg} — reconnect LinkedIn`);
      throw new Error(`${msg} — reconnect LinkedIn`);
    }
  }
  if (result.status !== 200 || !result.info.sub) {
    const msg = `LinkedIn userinfo returned ${result.status}; reconnect LinkedIn`;
    setConnectionErrorRecord(d, userId, msg);
    throw new Error(msg);
  }

  const now = new Date().toISOString();
  d.prepare(
    `UPDATE linkedin_connections SET member_id=?, display_name=?, email=?, picture=?, updated_at=?, last_error=NULL
     WHERE user_id=?`,
  ).run(
    result.info.sub,
    displayNameFrom(result.info),
    result.info.email ?? null,
    result.info.picture ?? null,
    now,
    userId,
  );
  const connection = getConnectionRecord(d, userId);
  if (!connection) throw new Error("LinkedIn connection disappeared during refresh");
  return connection;
}

export function deleteConnectionRecord(d: Database.Database, userId: string): void {
  d.prepare("DELETE FROM linkedin_connections WHERE user_id=?").run(userId);
  d.prepare("DELETE FROM linkedin_oauth_states WHERE user_id=?").run(userId);
}

import assert from "node:assert/strict";
import crypto from "node:crypto";
import test from "node:test";
import Database from "better-sqlite3";
import { SCHEMA } from "../src/lib/db.ts";
import {
  LINKEDIN_SCOPES,
  LINKEDIN_TOKEN_URL,
  LINKEDIN_USERINFO_URL,
  buildAuthorizeUrl,
  connectFromCode,
  consumeStateRecord,
  createStateRecord,
  decryptToken,
  deleteConnectionRecord,
  encryptToken,
  getConnectionRecord,
  refreshConnectionRecord,
  resolveLinkedInConfig,
} from "../src/lib/linkedin-core.ts";

const key = crypto.randomBytes(32);
const config = {
  clientId: "client-id",
  clientSecret: "client-secret",
  redirectUri: "http://localhost:3000/api/linkedin/callback",
  tokenKey: key,
};

function freshDb() {
  const d = new Database(":memory:");
  d.exec(SCHEMA);
  return d;
}

function tokenResponse(overrides = {}) {
  return new Response(
    JSON.stringify({
      access_token: "secret-access-token",
      expires_in: 3600,
      refresh_token: "secret-refresh-token",
      scope: LINKEDIN_SCOPES,
      token_type: "Bearer",
      ...overrides,
    }),
    { status: 200, headers: { "content-type": "application/json" } },
  );
}

function userInfo(status = 200, overrides = {}) {
  return new Response(
    JSON.stringify({
      sub: "member-1",
      name: "Ada Lovelace",
      email: "ada@example.com",
      picture: "https://example.com/ada.png",
      ...overrides,
    }),
    { status, headers: { "content-type": "application/json" } },
  );
}

test("token envelopes round-trip and never contain the plaintext", () => {
  const encrypted = encryptToken("super-secret", key);
  assert.equal(encrypted.startsWith("v1."), true);
  assert.equal(encrypted.includes("super-secret"), false);
  assert.equal(decryptToken(encrypted, key), "super-secret");
  assert.throws(() => decryptToken(encrypted, crypto.randomBytes(32)));
});

test("authorize URL uses official web OAuth + OpenID scopes without unsupported PKCE", () => {
  const url = new URL(
    buildAuthorizeUrl({
      clientId: "cid",
      redirectUri: "http://localhost/cb",
      state: "state",
    }),
  );
  assert.equal(url.origin + url.pathname, "https://www.linkedin.com/oauth/v2/authorization");
  assert.equal(url.searchParams.get("scope"), "openid profile email");
  assert.equal(url.searchParams.get("response_type"), "code");
  assert.equal(url.searchParams.get("code_challenge"), null);
  assert.equal(url.searchParams.get("client_secret"), null);
});

test("OAuth state is single-use, per-user, and expires", () => {
  const d = freshDb();
  const now = new Date("2026-01-01T00:00:00Z");
  const { state } = createStateRecord(d, "user-a", { now, ttlMs: 60_000 });
  assert.ok(state.length > 20);

  assert.equal(consumeStateRecord(d, state, "user-b", new Date("2026-01-01T00:00:30Z")), false);
  assert.equal(consumeStateRecord(d, state, "user-a", new Date("2026-01-01T00:00:30Z")), true);
  assert.equal(consumeStateRecord(d, state, "user-a", new Date("2026-01-01T00:00:31Z")), false);
});

test("expired OAuth state is rejected before it can be consumed", () => {
  const d = freshDb();
  const created = new Date("2026-01-01T00:00:00Z");
  const { state } = createStateRecord(d, "user-a", { now: created, ttlMs: 1_000 });
  assert.equal(consumeStateRecord(d, state, "user-a", new Date("2026-01-01T00:00:02Z")), false);
});

test("successful OAuth stores encrypted tokens and profile fields", async () => {
  const d = freshDb();
  const seen = [];
  const fetchMock = async (url, init) => {
    seen.push(String(url));
    if (String(url) === LINKEDIN_TOKEN_URL) {
      const body = String(init.body);
      assert.match(body, /grant_type=authorization_code/);
      assert.equal(body.includes("code_verifier"), false);
      assert.match(body, /client_secret=client-secret/);
      return tokenResponse();
    }
    if (String(url) === LINKEDIN_USERINFO_URL) {
      assert.equal(init.headers.Authorization, "Bearer secret-access-token");
      return userInfo();
    }
    throw new Error(`unexpected URL ${url}`);
  };

  const connection = await connectFromCode(d, "user-a", config, "code-123", fetchMock);
  assert.equal(connection.displayName, "Ada Lovelace");
  assert.equal(connection.email, "ada@example.com");
  assert.equal(connection.memberId, "member-1");
  assert.equal(connection.scope, LINKEDIN_SCOPES);
  assert.equal(seen.length, 2);

  const raw = d
    .prepare("SELECT access_token_enc, refresh_token_enc FROM linkedin_connections WHERE user_id=?")
    .get("user-a");
  assert.equal(raw.access_token_enc.includes("secret-access-token"), false);
  assert.equal(decryptToken(raw.access_token_enc, key), "secret-access-token");
  assert.equal(decryptToken(raw.refresh_token_enc, key), "secret-refresh-token");
});

test("denied token exchange stores nothing", async () => {
  const d = freshDb();
  const fetchMock = async () =>
    new Response(JSON.stringify({ error: "invalid_grant", error_description: "authorization code expired" }), {
      status: 400,
      headers: { "content-type": "application/json" },
    });

  await assert.rejects(
    connectFromCode(d, "user-a", config, "bad-code", fetchMock),
    /authorization code expired/,
  );
  assert.equal(getConnectionRecord(d, "user-a"), null);
});

test("userinfo denial rejects the connection", async () => {
  const d = freshDb();
  const fetchMock = async (url) =>
    String(url) === LINKEDIN_TOKEN_URL
      ? tokenResponse()
      : new Response(JSON.stringify({ error: "invalid_token" }), { status: 401 });
  await assert.rejects(connectFromCode(d, "user-a", config, "code", fetchMock), /userinfo returned 401/);
  assert.equal(getConnectionRecord(d, "user-a"), null);
});

test("expired access token without refresh token requires reconnect", async () => {
  const d = freshDb();
  const connection = await connectFromCode(d, "user-a", config, "code", async (url) =>
    String(url) === LINKEDIN_TOKEN_URL ? tokenResponse({ refresh_token: undefined }) : userInfo(),
  );
  assert.ok(connection);
  d.prepare("UPDATE linkedin_connections SET expires_at=? WHERE user_id=?").run(
    new Date(Date.now() - 60_000).toISOString(),
    "user-a",
  );

  const fetchMock = async () => new Response(JSON.stringify({ error: "invalid_token" }), { status: 401 });
  await assert.rejects(refreshConnectionRecord(d, "user-a", config, fetchMock), /reconnect LinkedIn/);
  assert.match(getConnectionRecord(d, "user-a").lastError, /reconnect LinkedIn/);
});

test("expired access token refreshes once when LinkedIn issued a refresh token", async () => {
  const d = freshDb();
  await connectFromCode(d, "user-a", config, "code", async (url) =>
    String(url) === LINKEDIN_TOKEN_URL ? tokenResponse() : userInfo(),
  );
  d.prepare("UPDATE linkedin_connections SET expires_at=? WHERE user_id=?").run(
    new Date(Date.now() - 60_000).toISOString(),
    "user-a",
  );

  let userinfoCalls = 0;
  const fetchMock = async (url, init) => {
    if (String(url) === LINKEDIN_TOKEN_URL) {
      assert.match(String(init.body), /grant_type=refresh_token/);
      return tokenResponse({ access_token: "new-access-token", refresh_token: "new-refresh-token" });
    }
    userinfoCalls += 1;
    if (userinfoCalls === 1) return new Response(JSON.stringify({ error: "invalid_token" }), { status: 401 });
    assert.equal(init.headers.Authorization, "Bearer new-access-token");
    return userInfo();
  };

  const refreshed = await refreshConnectionRecord(d, "user-a", config, fetchMock);
  assert.equal(refreshed.displayName, "Ada Lovelace");
  const raw = d.prepare("SELECT access_token_enc FROM linkedin_connections WHERE user_id=?").get("user-a");
  assert.equal(decryptToken(raw.access_token_enc, key), "new-access-token");
});

test("connections and OAuth states are isolated per user and disconnect is scoped", async () => {
  const d = freshDb();
  await connectFromCode(d, "user-a", config, "code", async (url) =>
    String(url) === LINKEDIN_TOKEN_URL ? tokenResponse() : userInfo(),
  );
  createStateRecord(d, "user-a");

  assert.ok(getConnectionRecord(d, "user-a"));
  assert.equal(getConnectionRecord(d, "user-b"), null);

  deleteConnectionRecord(d, "user-a");
  assert.equal(getConnectionRecord(d, "user-a"), null);
  const states = d.prepare("SELECT COUNT(*) AS n FROM linkedin_oauth_states WHERE user_id=?").get("user-a");
  assert.equal(states.n, 0);
});

test("missing or invalid encryption key disables the connector", () => {
  assert.match(resolveLinkedInConfig({ LINKEDIN_CLIENT_ID: "id", LINKEDIN_CLIENT_SECRET: "secret" }).error, /TOKEN_KEY/);
  const shortKey = Buffer.from("short").toString("base64");
  assert.match(
    resolveLinkedInConfig({
      LINKEDIN_CLIENT_ID: "id",
      LINKEDIN_CLIENT_SECRET: "secret",
      LINKEDIN_TOKEN_KEY: shortKey,
    }).error,
    /32 bytes/,
  );
});

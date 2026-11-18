/**
 * mcp/oauth/server.cjs
 *
 * OAuth 2.1 authorization server for the Ramble On connector, with Notion as
 * the sign-in. Claude (the OAuth client) sends the user here; we send them on
 * to Notion's consent page, where they pick which pages Ramble On may use;
 * Notion sends them back with a code; we hand Claude our own code, and later
 * our own access and refresh tokens.
 *
 * Nothing is stored. The Notion tokens travel inside our codes and tokens,
 * sealed with AES-256-GCM (see seal.cjs), so only this server can read them,
 * and Claude keeps them like any other OAuth token.
 *
 * Enabled only when RAMBLE_PUBLIC_URL, NOTION_OAUTH_CLIENT_ID,
 * NOTION_OAUTH_CLIENT_SECRET and RAMBLE_TOKEN_KEY are all set.
 *
 * Endpoints:
 *   GET  /.well-known/oauth-protected-resource[/mcp]  RFC 9728 metadata
 *   GET  /.well-known/oauth-authorization-server      RFC 8414 metadata
 *   POST /oauth/register                              RFC 7591 DCR (stateless)
 *   GET  /oauth/authorize                             consent page
 *   POST /oauth/authorize                             consent → Notion
 *   GET  /oauth/notion/callback                       Notion → Claude
 *   POST /oauth/token                                 code and refresh grants
 */

'use strict';

const crypto = require('node:crypto');
const { seal, open, hasKey } = require('./seal.cjs');

const NOTION_AUTHORIZE_URL = 'https://api.notion.com/v1/oauth/authorize';
const NOTION_TOKEN_URL = 'https://api.notion.com/v1/oauth/token';
const NOTION_OAUTH_VERSION = '2026-03-11';

const ACCESS_TTL = 60 * 60; // 1 hour
const REFRESH_TTL = 90 * 24 * 60 * 60; // 90 days
const CODE_TTL = 5 * 60;
const FLOW_TTL = 10 * 60;
const MAX_BODY = 16 * 1024;

// Redirect URIs Claude uses: the hosted apps' fixed callback, and Claude
// Code's loopback callback on any port.
const HOSTED_CALLBACK = 'https://claude.ai/api/mcp/auth_callback';
// Hosts whose Client ID Metadata Documents we will fetch.
const CIMD_HOSTS = new Set(['claude.ai', 'claude.com', 'anthropic.com']);

const now = () => Math.floor(Date.now() / 1000);

const publicUrl = () => (process.env.RAMBLE_PUBLIC_URL || '').replace(/\/+$/, '');

/** @returns {boolean} True when the connector's sign-in is configured. */
const isOAuthEnabled = () =>
  Boolean(
    publicUrl() &&
      process.env.NOTION_OAUTH_CLIENT_ID &&
      process.env.NOTION_OAUTH_CLIENT_SECRET &&
      hasKey(),
  );

const resourceUrl = () => `${publicUrl()}/mcp`;
const resourceMetadataUrl = () =>
  `${publicUrl()}/.well-known/oauth-protected-resource/mcp`;
const notionCallbackUrl = () => `${publicUrl()}/oauth/notion/callback`;

// ── Small HTTP helpers ──────────────────────────────────────────────────────

const send = (res, status, headers, body) => {
  res.writeHead(status, { 'Cache-Control': 'no-store', ...headers });
  res.end(body);
};

const sendJson = (res, status, payload, headers = {}) =>
  send(res, status, { 'Content-Type': 'application/json', ...headers }, JSON.stringify(payload));

const oauthError = (res, status, error, description) =>
  sendJson(res, status, description ? { error, error_description: description } : { error });

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const sendHtml = (res, status, title, inner) =>
  send(
    res,
    status,
    {
      'Content-Type': 'text/html; charset=utf-8',
      'X-Frame-Options': 'DENY',
      'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'",
      'Referrer-Policy': 'no-referrer',
    },
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escapeHtml(title)}</title>
<style>body{font-family:system-ui,sans-serif;max-width:32rem;margin:4rem auto;padding:0 1rem;line-height:1.5;color:#1a1a1a}button,a.button{display:inline-block;font:inherit;padding:.6rem 1.2rem;border-radius:.4rem;border:0;background:#1a1a1a;color:#fff;cursor:pointer;text-decoration:none}.warn{background:#fff4d6;padding:.6rem .8rem;border-radius:.4rem}</style>
</head><body>${inner}</body></html>`,
  );

const readBody = (req) =>
  new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY) {
        reject(new Error('body too large'));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });

const readForm = async (req) => Object.fromEntries(new URLSearchParams(await readBody(req)));

// ── Redirect URIs and clients ───────────────────────────────────────────────

const isLoopback = (u) =>
  u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1');

/** Is this a redirect URI Claude uses? */
const isAllowedRedirect = (uri) => {
  if (uri === HOSTED_CALLBACK) return true;
  try {
    const u = new URL(uri);
    return isLoopback(u) && u.pathname === '/callback' && !u.search && !u.hash;
  } catch {
    return false;
  }
};

/** Does `uri` match a registered redirect URI (loopback ports ignored)? */
const redirectMatches = (uri, registered) =>
  registered.some((r) => {
    if (r === uri) return true;
    try {
      const a = new URL(uri);
      const b = new URL(r);
      return isLoopback(a) && isLoopback(b) && a.hostname === b.hostname && a.pathname === b.pathname;
    } catch {
      return false;
    }
  });

/** Fetches a Client ID Metadata Document from an allowed Claude host. */
const fetchClientMetadata = async (clientId) => {
  let u;
  try {
    u = new URL(clientId);
  } catch {
    return null;
  }
  if (u.protocol !== 'https:' || !CIMD_HOSTS.has(u.hostname)) return null;
  try {
    const r = await fetch(u, { signal: AbortSignal.timeout(5000), redirect: 'error' });
    if (!r.ok) return null;
    const doc = await r.json();
    if (doc.client_id !== clientId || !Array.isArray(doc.redirect_uris)) return null;
    return { redirect_uris: doc.redirect_uris.filter((x) => typeof x === 'string') };
  } catch {
    return null;
  }
};

/**
 * Resolves a client_id (sealed DCR registration, or a CIMD URL) and checks
 * that `redirectUri` belongs to it and is one Claude uses.
 */
const checkClient = async (clientId, redirectUri) => {
  if (!clientId || !redirectUri || !isAllowedRedirect(redirectUri)) return false;
  const registered = clientId.startsWith('https://')
    ? await fetchClientMetadata(clientId)
    : open('client', clientId);
  return Boolean(registered && redirectMatches(redirectUri, registered.redirect_uris || []));
};

// ── Notion ──────────────────────────────────────────────────────────────────

const notionToken = async (body) => {
  const basic = Buffer.from(
    `${process.env.NOTION_OAUTH_CLIENT_ID}:${process.env.NOTION_OAUTH_CLIENT_SECRET}`,
  ).toString('base64');
  const r = await fetch(NOTION_TOKEN_URL, {
    method: 'POST',
    headers: {
      Authorization: `Basic ${basic}`,
      'Content-Type': 'application/json',
      'Notion-Version': NOTION_OAUTH_VERSION,
    },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(8000),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || !data.access_token) {
    const err = new Error(`Notion token request failed (${r.status} ${data.error || ''})`.trim());
    err.notionError = data.error;
    throw err;
  }
  return { nt: data.access_token, nrt: data.refresh_token || null };
};

// ── Endpoint handlers ───────────────────────────────────────────────────────

const protectedResourceMetadata = (res) =>
  sendJson(res, 200, {
    resource: resourceUrl(),
    authorization_servers: [publicUrl()],
    bearer_methods_supported: ['header'],
    scopes_supported: ['notion'],
    resource_name: 'Ramble On',
  });

const authorizationServerMetadata = (res) =>
  sendJson(res, 200, {
    issuer: publicUrl(),
    authorization_endpoint: `${publicUrl()}/oauth/authorize`,
    token_endpoint: `${publicUrl()}/oauth/token`,
    registration_endpoint: `${publicUrl()}/oauth/register`,
    response_types_supported: ['code'],
    grant_types_supported: ['authorization_code', 'refresh_token'],
    code_challenge_methods_supported: ['S256'],
    token_endpoint_auth_methods_supported: ['none'],
    scopes_supported: ['notion'],
    client_id_metadata_document_supported: true,
  });

const register = async (req, res) => {
  let meta;
  try {
    meta = JSON.parse(await readBody(req));
  } catch {
    return oauthError(res, 400, 'invalid_client_metadata', 'Body must be JSON.');
  }
  const uris = Array.isArray(meta.redirect_uris) ? meta.redirect_uris : [];
  if (!uris.length || !uris.every((u) => typeof u === 'string' && isAllowedRedirect(u))) {
    return oauthError(res, 400, 'invalid_redirect_uri', 'Only Claude redirect URIs are accepted.');
  }
  const clientId = seal('client', { redirect_uris: uris });
  return sendJson(res, 201, {
    client_id: clientId,
    client_id_issued_at: now(),
    client_name: typeof meta.client_name === 'string' ? meta.client_name.slice(0, 100) : undefined,
    redirect_uris: uris,
    token_endpoint_auth_method: 'none',
    grant_types: ['authorization_code', 'refresh_token'],
    response_types: ['code'],
  });
};

/**
 * Notion's authorize URL for one sign-in. The sign-in's details travel
 * sealed in `state`, so nothing is stored.
 *
 * @param {object} flow Client id, redirect URI, PKCE challenge and state.
 * @returns {string}
 */
const notionAuthorizeUrl = (flow) => {
  const u = new URL(NOTION_AUTHORIZE_URL);
  u.searchParams.set('client_id', process.env.NOTION_OAUTH_CLIENT_ID);
  u.searchParams.set('response_type', 'code');
  u.searchParams.set('owner', 'user');
  u.searchParams.set('redirect_uri', notionCallbackUrl());
  const { exp: _exp, ...rest } = flow;
  u.searchParams.set('state', seal('state', { ...rest, exp: now() + FLOW_TTL }));
  return u.toString();
};

/** GET /oauth/authorize: validate, then show the consent page. */
const authorizePage = async (req, res, url) => {
  const p = url.searchParams;
  const clientId = p.get('client_id');
  const redirectUri = p.get('redirect_uri');
  if (!(await checkClient(clientId, redirectUri))) {
    return sendHtml(res, 400, 'Ramble On', '<h1>Sign-in link not recognised</h1><p>This sign-in link isn\'t from a Claude app that Ramble On knows. Start again from Claude.</p>');
  }
  const back = (error) => {
    const u = new URL(redirectUri);
    u.searchParams.set('error', error);
    if (p.get('state')) u.searchParams.set('state', p.get('state'));
    return send(res, 302, { Location: u.toString() }, '');
  };
  if (p.get('response_type') !== 'code') return back('unsupported_response_type');
  if (!p.get('code_challenge') || p.get('code_challenge_method') !== 'S256') return back('invalid_request');

  const flowPayload = {
    cid: clientId,
    ru: redirectUri,
    cc: p.get('code_challenge'),
    st: p.get('state') || null,
  };
  const host = new URL(redirectUri).host;
  const loopback = isLoopback(new URL(redirectUri));
  return sendHtml(
    res,
    200,
    'Connect Ramble On',
    `<h1>Connect Ramble On to Claude</h1>
<p>Ramble On will let Claude read your voice model and search, read and write the Notion pages you choose on the next screen. You'll be sent back to <strong>${escapeHtml(host)}</strong>.</p>
${loopback ? '<p class="warn">This sign-in returns to a program on your own computer. Continue only if you started it from Claude Code.</p>' : ''}
<p>Ramble On stores nothing. Your Notion access is sealed inside the sign-in that Claude keeps.</p>
<p><a class="button" href="${escapeHtml(notionAuthorizeUrl(flowPayload))}">Continue to Notion</a></p>`,
  );
};

/**
 * POST /oauth/authorize: kept for consent pages served before the link
 * change. The page now links straight to Notion, because browsers block a
 * form post that redirects to another site under `form-action 'self'`.
 */
const authorizeContinue = async (req, res) => {
  const form = await readForm(req);
  const flow = open('flow', form.flow);
  if (!flow) {
    return sendHtml(res, 400, 'Ramble On', '<h1>This sign-in has expired</h1><p>Start again from Claude.</p>');
  }
  return send(res, 302, { Location: notionAuthorizeUrl(flow) }, '');
};

/** GET /oauth/notion/callback: Notion said yes or no; answer Claude. */
const notionCallback = async (req, res, url) => {
  const p = url.searchParams;
  const flow = open('state', p.get('state'));
  if (!flow) {
    return sendHtml(res, 400, 'Ramble On', '<h1>This sign-in has expired</h1><p>Start again from Claude.</p>');
  }
  const back = (params) => {
    const u = new URL(flow.ru);
    for (const [k, v] of Object.entries(params)) u.searchParams.set(k, v);
    if (flow.st) u.searchParams.set('state', flow.st);
    return send(res, 302, { Location: u.toString() }, '');
  };
  if (p.get('error') || !p.get('code')) return back({ error: 'access_denied' });

  let tokens;
  try {
    tokens = await notionToken({
      grant_type: 'authorization_code',
      code: p.get('code'),
      redirect_uri: notionCallbackUrl(),
    });
  } catch (err) {
    console.error('[ramble-on OAuth]', err.message);
    return back({ error: 'server_error' });
  }
  const code = seal('code', { cid: flow.cid, ru: flow.ru, cc: flow.cc, ...tokens, exp: now() + CODE_TTL });
  return back({ code });
};

const issueTokens = (res, cid, nt, nrt) =>
  sendJson(res, 200, {
    access_token: seal('access', { nt, exp: now() + ACCESS_TTL }),
    token_type: 'Bearer',
    expires_in: ACCESS_TTL,
    refresh_token: seal('refresh', { cid, nt, nrt, exp: now() + REFRESH_TTL }),
    scope: 'notion',
  });

const pkceMatches = (verifier, challenge) =>
  typeof verifier === 'string' &&
  verifier.length >= 43 &&
  verifier.length <= 128 &&
  crypto.createHash('sha256').update(verifier).digest('base64url') === challenge;

/** POST /oauth/token */
const token = async (req, res) => {
  const ct = String(req.headers['content-type'] || '');
  if (!ct.startsWith('application/x-www-form-urlencoded')) {
    return oauthError(res, 400, 'invalid_request', 'Use application/x-www-form-urlencoded.');
  }
  const f = await readForm(req);

  if (f.grant_type === 'authorization_code') {
    const c = open('code', f.code);
    if (!c) return oauthError(res, 400, 'invalid_grant');
    if ((f.client_id && f.client_id !== c.cid) || f.redirect_uri !== c.ru) {
      return oauthError(res, 400, 'invalid_grant');
    }
    if (!pkceMatches(f.code_verifier, c.cc)) return oauthError(res, 400, 'invalid_grant');
    return issueTokens(res, c.cid, c.nt, c.nrt);
  }

  if (f.grant_type === 'refresh_token') {
    const r = open('refresh', f.refresh_token);
    if (!r || (f.client_id && f.client_id !== r.cid)) return oauthError(res, 400, 'invalid_grant');
    let nt = r.nt;
    let nrt = r.nrt;
    if (nrt) {
      try {
        ({ nt, nrt } = await notionToken({ grant_type: 'refresh_token', refresh_token: nrt }));
      } catch (err) {
        console.error('[ramble-on OAuth]', err.message);
        if (err.notionError === 'invalid_grant' || err.notionError === 'unauthorized_client') {
          return oauthError(res, 400, 'invalid_grant');
        }
        return oauthError(res, 503, 'temporarily_unavailable');
      }
    }
    return issueTokens(res, r.cid, nt, nrt);
  }

  return oauthError(res, 400, 'unsupported_grant_type');
};

/**
 * Routes OAuth and metadata requests. Returns true when it handled one.
 *
 * @param {import('http').IncomingMessage} req
 * @param {import('http').ServerResponse} res
 * @returns {Promise<boolean>}
 */
const handleOAuthRequest = async (req, res) => {
  const url = new URL(req.url || '/', 'http://localhost');
  const path = url.pathname;
  const known =
    path.startsWith('/.well-known/oauth-') || path.startsWith('/oauth/');
  if (!known) return false;
  if (!isOAuthEnabled()) {
    sendJson(res, 404, { error: 'not_found' });
    return true;
  }
  try {
    if (req.method === 'GET' && (path === '/.well-known/oauth-protected-resource' || path === '/.well-known/oauth-protected-resource/mcp')) {
      protectedResourceMetadata(res);
    } else if (req.method === 'GET' && path === '/.well-known/oauth-authorization-server') {
      authorizationServerMetadata(res);
    } else if (req.method === 'POST' && path === '/oauth/register') {
      await register(req, res);
    } else if (req.method === 'GET' && path === '/oauth/authorize') {
      await authorizePage(req, res, url);
    } else if (req.method === 'POST' && path === '/oauth/authorize') {
      await authorizeContinue(req, res);
    } else if (req.method === 'GET' && path === '/oauth/notion/callback') {
      await notionCallback(req, res, url);
    } else if (req.method === 'POST' && path === '/oauth/token') {
      await token(req, res);
    } else {
      sendJson(res, 404, { error: 'not_found' });
    }
  } catch (err) {
    console.error('[ramble-on OAuth] Request error:', err.message);
    if (!res.headersSent) oauthError(res, 500, 'server_error');
  }
  return true;
};

/**
 * Reads the caller's Notion token from a Bearer access token.
 *
 * @param {import('http').IncomingHttpHeaders} headers
 * @returns {{present: boolean, notionToken: string | null}}
 */
const readBearer = (headers) => {
  const auth = String(headers.authorization || '');
  const m = auth.match(/^Bearer\s+(\S+)$/i);
  if (!m) return { present: false, notionToken: null };
  if (!isOAuthEnabled()) return { present: true, notionToken: null };
  const t = open('access', m[1]);
  return { present: true, notionToken: t && typeof t.nt === 'string' ? t.nt : null };
};

/** Sends the 401 that starts (or restarts) sign-in. */
const sendUnauthorized = (res, invalidToken = false) =>
  sendJson(
    res,
    401,
    { error: invalidToken ? 'invalid_token' : 'unauthorized', error_description: 'Sign in with Notion to use Ramble On.' },
    {
      'WWW-Authenticate': `Bearer resource_metadata="${resourceMetadataUrl()}"${invalidToken ? ', error="invalid_token"' : ''}`,
    },
  );

module.exports = {
  handleOAuthRequest,
  isOAuthEnabled,
  readBearer,
  sendUnauthorized,
  // exported for tests
  isAllowedRedirect,
  redirectMatches,
  pkceMatches,
};

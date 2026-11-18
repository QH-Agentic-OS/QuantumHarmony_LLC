'use strict';
// End-to-end test of the connector's Notion sign-in (OAuth) flow, with
// Notion's token endpoint mocked. Run: npm run test:oauth
const crypto = require('node:crypto');
const path = require('node:path');

const H = path.join(__dirname, '..');
Object.assign(process.env, {
  RAMBLE_HOSTED: '1', PORT: '8797', RAMBLE_PUBLIC_URL: 'https://ramble-on-mcp.example',
  NOTION_OAUTH_CLIENT_ID: 'cid', NOTION_OAUTH_CLIENT_SECRET: 'secret',
  RAMBLE_TOKEN_KEY: crypto.randomBytes(32).toString('base64'),
});
const realFetch = global.fetch;
let notionCalls = [];
global.fetch = async (url, opts = {}) => {
  if (String(url) === 'https://api.notion.com/v1/oauth/token') {
    const body = JSON.parse(opts.body);
    notionCalls.push({ body, auth: opts.headers.Authorization, ver: opts.headers['Notion-Version'] });
    const n = notionCalls.length;
    return new Response(JSON.stringify({ access_token: `ntn_access_${n}`, refresh_token: `ntn_refresh_${n}`, bot_id: 'b' }), { status: 200 });
  }
  return realFetch(url, opts);
};
const { startMcpServer } = require(path.join(H, 'mcp/server.cjs'));
const B = 'http://127.0.0.1:8797';
const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) process.exitCode = 1; };
const mcp = (headers) => realFetch(`${B}/mcp`, { method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream', ...headers }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }) });
const toolCount = async (r) => (await r.text()).match(/"name":"ramble\.[a-z_]+"/g)?.length || 0;
const form = (o) => ({ method: 'POST', headers: { 'content-type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(o).toString() });
(async () => {
  await startMcpServer();
  let r = await mcp({});
  ok(r.status === 401 && /resource_metadata="https:\/\/ramble-on-mcp\.example\/\.well-known\/oauth-protected-resource\/mcp"/.test(r.headers.get('www-authenticate')), 'no credentials -> 401 with resource_metadata');
  const prm = await (await realFetch(`${B}/.well-known/oauth-protected-resource/mcp`)).json();
  ok(prm.resource === 'https://ramble-on-mcp.example/mcp' && prm.authorization_servers[0] === 'https://ramble-on-mcp.example', 'protected resource metadata');
  const asm = await (await realFetch(`${B}/.well-known/oauth-authorization-server`)).json();
  ok(asm.client_id_metadata_document_supported === true && asm.token_endpoint_auth_methods_supported.includes('none') && asm.code_challenge_methods_supported[0] === 'S256', 'authorization server metadata');
  r = await realFetch(`${B}/oauth/register`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ redirect_uris: ['https://evil.example/cb'] }) });
  ok(r.status === 400, 'DCR rejects non-Claude redirect');
  r = await realFetch(`${B}/oauth/register`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ redirect_uris: ['http://localhost/callback', 'https://claude.ai/api/mcp/auth_callback'], client_name: 'Claude Code' }) });
  const reg = await r.json();
  ok(r.status === 201 && reg.client_id, 'DCR registers Claude redirect');
  const verifier = crypto.randomBytes(48).toString('base64url');
  const challenge = crypto.createHash('sha256').update(verifier).digest('base64url');
  const ru = 'http://localhost:54321/callback';
  const q = new URLSearchParams({ response_type: 'code', client_id: reg.client_id, redirect_uri: ru, code_challenge: challenge, code_challenge_method: 'S256', state: 'xyz' });
  r = await realFetch(`${B}/oauth/authorize?${new URLSearchParams({ ...Object.fromEntries(q), redirect_uri: 'https://evil.example/cb' })}`);
  ok(r.status === 400, 'authorize rejects unregistered redirect');
  r = await realFetch(`${B}/oauth/authorize?${new URLSearchParams({ ...Object.fromEntries(q), client_id: 'https://evil.example/meta' })}`);
  ok(r.status === 400, 'authorize rejects CIMD from unknown host');
  r = await realFetch(`${B}/oauth/authorize?${q}`);
  const html = await r.text();
  ok(r.status === 200 && /localhost:54321/.test(html) && /program on your own computer/.test(html) && r.headers.get('x-frame-options') === 'DENY', 'consent page shows host, loopback warning, no framing');
  const flow = html.match(/name="flow" value="([^"]+)"/)[1];
  r = await realFetch(`${B}/oauth/authorize`, { ...form({ flow }), redirect: 'manual' });
  const toNotion = new URL(r.headers.get('location'));
  ok(r.status === 302 && toNotion.origin + toNotion.pathname === 'https://api.notion.com/v1/oauth/authorize' && toNotion.searchParams.get('owner') === 'user' && toNotion.searchParams.get('redirect_uri') === 'https://ramble-on-mcp.example/oauth/notion/callback', 'consent -> Notion authorize');
  r = await realFetch(`${B}/oauth/notion/callback?error=access_denied&state=${encodeURIComponent(toNotion.searchParams.get('state'))}`, { redirect: 'manual' });
  let back = new URL(r.headers.get('location'));
  ok(back.searchParams.get('error') === 'access_denied' && back.searchParams.get('state') === 'xyz', 'Notion cancel -> access_denied to Claude');
  r = await realFetch(`${B}/oauth/notion/callback?code=notioncode&state=${encodeURIComponent(toNotion.searchParams.get('state'))}`, { redirect: 'manual' });
  back = new URL(r.headers.get('location'));
  ok(back.origin === 'http://localhost:54321' && back.searchParams.get('code') && back.searchParams.get('state') === 'xyz', 'Notion callback -> code to Claude');
  ok(notionCalls[0].body.grant_type === 'authorization_code' && notionCalls[0].auth === 'Basic ' + Buffer.from('cid:secret').toString('base64'), 'Notion code exchange uses Basic auth');
  const code = back.searchParams.get('code');
  r = await realFetch(`${B}/oauth/token`, form({ grant_type: 'authorization_code', code, redirect_uri: ru, client_id: reg.client_id, code_verifier: 'x'.repeat(50) }));
  ok(r.status === 400 && (await r.json()).error === 'invalid_grant', 'wrong PKCE verifier rejected');
  r = await realFetch(`${B}/oauth/token`, form({ grant_type: 'authorization_code', code, redirect_uri: 'http://localhost:1/callback', client_id: reg.client_id, code_verifier: verifier }));
  ok(r.status === 400, 'wrong redirect_uri rejected');
  r = await realFetch(`${B}/oauth/token`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' });
  ok(r.status === 400, 'JSON token request rejected');
  r = await realFetch(`${B}/oauth/token`, form({ grant_type: 'authorization_code', code, redirect_uri: ru, client_id: reg.client_id, code_verifier: verifier }));
  const tok = await r.json();
  ok(r.status === 200 && tok.access_token && tok.refresh_token && tok.expires_in === 3600 && r.headers.get('cache-control') === 'no-store', 'code exchange issues tokens');
  ok(!JSON.stringify(tok).includes('ntn_'), 'Notion token not readable in our tokens');
  r = await mcp({ authorization: `Bearer ${tok.access_token}` });
  ok(r.status === 200 && (await toolCount(r)) === 3, 'Bearer -> 3 Notion tools');
  r = await mcp({ authorization: `Bearer ${tok.access_token.slice(0, -2)}xx` });
  ok(r.status === 401 && /invalid_token/.test(r.headers.get('www-authenticate')), 'tampered token -> 401 invalid_token');
  r = await realFetch(`${B}/oauth/token`, form({ grant_type: 'refresh_token', refresh_token: tok.refresh_token, client_id: reg.client_id }));
  const tok2 = await r.json();
  ok(r.status === 200 && tok2.access_token !== tok.access_token && notionCalls[1].body.grant_type === 'refresh_token' && notionCalls[1].body.refresh_token === 'ntn_refresh_1', 'refresh rotates via Notion refresh');
  r = await realFetch(`${B}/oauth/token`, form({ grant_type: 'refresh_token', refresh_token: tok.access_token }));
  ok(r.status === 400, 'access token not accepted as refresh token');
  r = await mcp({ 'x-gemini-api-key': 'AIzaFAKE', 'x-ai-provider': 'gemini' });
  ok(r.status === 200 && (await toolCount(r)) === 9, 'plugin key headers -> all 9 tools');
  r = await mcp({ 'x-ai-provider': 'gemini' });
  ok(r.status === 401, 'provider header alone (no keys) -> 401 sign-in');
  process.exit();
})().catch((e) => { console.error(e); process.exit(1); });

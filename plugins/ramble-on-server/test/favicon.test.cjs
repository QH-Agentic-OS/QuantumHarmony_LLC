'use strict';
// The server serves its waveform icon, in hosted mode with sign-in on (the
// Render setup), without asking for credentials. Run: npm run test:favicon
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const H = path.join(__dirname, '..');
Object.assign(process.env, {
  RAMBLE_HOSTED: '1', PORT: '8798', RAMBLE_PUBLIC_URL: 'https://ramble-on-mcp.example',
  NOTION_OAUTH_CLIENT_ID: 'cid', NOTION_OAUTH_CLIENT_SECRET: 'secret',
  RAMBLE_TOKEN_KEY: crypto.randomBytes(32).toString('base64'),
});
const { startMcpServer, stopMcpServer } = require(path.join(H, 'mcp/server.cjs'));
const B = 'http://127.0.0.1:8798';
const ok = (c, m) => { console.log((c ? 'PASS ' : 'FAIL ') + m); if (!c) process.exitCode = 1; };
const asset = (name) => fs.readFileSync(path.join(H, 'mcp/assets', name));

(async () => {
  await startMcpServer();

  let r = await fetch(`${B}/favicon.ico`);
  let body = Buffer.from(await r.arrayBuffer());
  ok(r.status === 200 && r.headers.get('content-type') === 'image/x-icon', '/favicon.ico -> 200 image/x-icon, no sign-in');
  ok(body.equals(asset('favicon.ico')) && body.readUInt32LE(0) === 0x00010000, '/favicon.ico body is the ICO file');
  ok(/max-age=86400/.test(r.headers.get('cache-control') || ''), '/favicon.ico is cacheable');

  r = await fetch(`${B}/favicon.png?v=1`);
  body = Buffer.from(await r.arrayBuffer());
  ok(r.status === 200 && r.headers.get('content-type') === 'image/png' && body.equals(asset('icon.png')), '/favicon.png (with query) -> the 512 px PNG');

  r = await fetch(`${B}/apple-touch-icon.png`);
  ok(r.status === 200 && r.headers.get('content-type') === 'image/png', '/apple-touch-icon.png -> PNG');

  r = await fetch(`${B}/favicon.ico`, { method: 'HEAD' });
  ok(r.status === 200 && Number(r.headers.get('content-length')) === asset('favicon.ico').length && (await r.text()) === '', 'HEAD /favicon.ico -> headers, no body');

  r = await fetch(`${B}/favicon.ico`, { method: 'POST' });
  ok(r.status === 404, 'POST /favicon.ico -> 404');

  r = await fetch(`${B}/mcp`, { method: 'POST', headers: { 'content-type': 'application/json', accept: 'application/json, text/event-stream' }, body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'tools/list' }) });
  ok(r.status === 401, '/mcp without credentials still -> 401');

  r = await fetch(`${B}/health`);
  ok(r.status === 200, '/health still -> 200');

  await stopMcpServer();
  process.exit();
})().catch((e) => { console.error(e); process.exit(1); });

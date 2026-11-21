/**
 * mcp/favicon.cjs
 *
 * Serves the Ramble On waveform icon, so clients that look for a site icon
 * (the Claude connector directory, browsers) find one instead of a
 * placeholder.
 *
 *   GET /favicon.ico           → 16/32/48 px ICO
 *   GET /favicon.png           → 512 px PNG
 *   GET /apple-touch-icon.png  → 512 px PNG
 *
 * The files live in mcp/assets and are read once at startup.
 */

'use strict';

const fs = require('fs');
const path = require('path');

const ASSETS = path.join(__dirname, 'assets');

const read = (name) => {
  try {
    return fs.readFileSync(path.join(ASSETS, name));
  } catch (err) {
    console.warn(`[ramble-on MCP] Icon ${name} not found: ${err.message}`);
    return null;
  }
};

const ICO = read('favicon.ico');
const PNG = read('icon.png');

const ROUTES = {
  '/favicon.ico': { body: ICO, type: 'image/x-icon' },
  '/favicon.png': { body: PNG, type: 'image/png' },
  '/apple-touch-icon.png': { body: PNG, type: 'image/png' },
};

/**
 * Answers an icon request. Returns true when it handled one.
 *
 * @param {import('http').IncomingMessage} req
 * @param {import('http').ServerResponse} res
 * @param {string} pathname
 * @returns {boolean}
 */
const handleFaviconRequest = (req, res, pathname) => {
  const route = ROUTES[pathname];
  if (!route || !route.body) return false;
  if (req.method !== 'GET' && req.method !== 'HEAD') return false;
  res.writeHead(200, {
    'Content-Type': route.type,
    'Content-Length': route.body.length,
    'Cache-Control': 'public, max-age=86400',
    'X-Content-Type-Options': 'nosniff',
  });
  res.end(req.method === 'HEAD' ? undefined : route.body);
  return true;
};

module.exports = { handleFaviconRequest };

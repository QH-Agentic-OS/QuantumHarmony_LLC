/**
 * mcp/oauth/seal.cjs
 *
 * Authenticated encryption for the connector's OAuth codes and tokens.
 *
 * The connector keeps no database. Everything it must remember between the
 * steps of a sign-in (and the user's Notion token afterwards) is sealed with
 * AES-256-GCM into the code or token it hands back, and only this server can
 * open it. RAMBLE_TOKEN_KEY (32 random bytes, base64) is the only secret
 * needed; rotating it signs everyone out.
 */

'use strict';

const crypto = require('node:crypto');

const PREFIX = 'ro1.';

let cachedKey = null;

/** @returns {Buffer} The 32-byte sealing key. */
const getKey = () => {
  if (cachedKey) return cachedKey;
  const raw = process.env.RAMBLE_TOKEN_KEY || '';
  const key = Buffer.from(raw, 'base64');
  if (key.length !== 32) {
    throw new Error('RAMBLE_TOKEN_KEY must be 32 bytes, base64-encoded.');
  }
  cachedKey = key;
  return key;
};

/** @returns {boolean} True when a usable sealing key is configured. */
const hasKey = () => {
  try {
    getKey();
    return true;
  } catch {
    return false;
  }
};

/**
 * Seals a JSON payload. `typ` is bound into the ciphertext so a code can
 * never be used as a token or the other way round.
 *
 * @param {string} typ e.g. "code", "access", "refresh", "state", "client"
 * @param {object} payload
 * @returns {string} An opaque, URL-safe string.
 */
const seal = (typ, payload) => {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', getKey(), iv);
  cipher.setAAD(Buffer.from(typ));
  const body = Buffer.concat([
    cipher.update(JSON.stringify(payload), 'utf8'),
    cipher.final(),
  ]);
  const tag = cipher.getAuthTag();
  return PREFIX + Buffer.concat([iv, tag, body]).toString('base64url');
};

/**
 * Opens a sealed string. Returns null for anything tampered with, of the
 * wrong type, or past its `exp` (seconds since the epoch).
 *
 * @param {string} typ
 * @param {string} sealed
 * @returns {object | null}
 */
const open = (typ, sealed) => {
  if (typeof sealed !== 'string' || !sealed.startsWith(PREFIX)) return null;
  try {
    const raw = Buffer.from(sealed.slice(PREFIX.length), 'base64url');
    if (raw.length < 29) return null;
    const iv = raw.subarray(0, 12);
    const tag = raw.subarray(12, 28);
    const body = raw.subarray(28);
    const decipher = crypto.createDecipheriv('aes-256-gcm', getKey(), iv);
    decipher.setAAD(Buffer.from(typ));
    decipher.setAuthTag(tag);
    const text = Buffer.concat([decipher.update(body), decipher.final()]).toString('utf8');
    const payload = JSON.parse(text);
    if (typeof payload.exp === 'number' && payload.exp < Math.floor(Date.now() / 1000)) {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
};

module.exports = { seal, open, hasKey };

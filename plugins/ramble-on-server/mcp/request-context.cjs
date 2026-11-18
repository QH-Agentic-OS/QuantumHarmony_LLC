/**
 * mcp/request-context.cjs
 *
 * Per-request settings for the hosted (remote) server.
 *
 * Run locally (stdio, or HTTP on loopback), the server reads its keys and
 * settings from its own environment, which the MCP client sets from the
 * plugin's userConfig.
 *
 * Run hosted (RAMBLE_HOSTED=1), many users share one process, so every key
 * and setting comes from the headers of the request being served, and the
 * process environment is never consulted for them. Each user's own keys are
 * used only for that user's request and are never stored or logged.
 */

'use strict';

const { AsyncLocalStorage } = require('node:async_hooks');

const store = new AsyncLocalStorage();

// Setting name → request header that carries it in hosted mode.
const HEADER_FOR = {
  NOTION_API_KEY: 'x-notion-api-key',
  RAMBLE_NOTION_ROOT: 'x-ramble-notion-root',
  GEMINI_API_KEY: 'x-gemini-api-key',
  ANTHROPIC_API_KEY: 'x-anthropic-api-key',
  OPENAI_API_KEY: 'x-openai-api-key',
  AI_PROVIDER: 'x-ai-provider',
};

const MAX_HEADER_VALUE = 512;

/** @returns {boolean} True when running as the shared hosted server. */
const isHosted = () => process.env.RAMBLE_HOSTED === '1';

/**
 * Builds a settings object from an incoming request's headers.
 *
 * @param {import('http').IncomingHttpHeaders} headers
 * @returns {Record<string, string>}
 */
const contextFromHeaders = (headers) => {
  const ctx = {};
  for (const [name, header] of Object.entries(HEADER_FOR)) {
    const raw = headers[header];
    const value = Array.isArray(raw) ? raw[0] : raw;
    if (typeof value === 'string' && value.trim()) {
      ctx[name] = value.trim().slice(0, MAX_HEADER_VALUE);
    }
  }
  return ctx;
};

/**
 * Runs `fn` with `ctx` as the settings for everything it awaits.
 *
 * @template T
 * @param {Record<string, string>} ctx
 * @param {() => Promise<T>} fn
 * @returns {Promise<T>}
 */
const runWithContext = (ctx, fn) => store.run(ctx, fn);

/**
 * Reads one setting: from the current request in hosted mode, otherwise
 * from the process environment.
 *
 * @param {string} name e.g. "GEMINI_API_KEY"
 * @returns {string} The value, or an empty string when unset.
 */
const readSetting = (name) => {
  if (isHosted()) {
    const ctx = store.getStore();
    return (ctx && ctx[name]) || '';
  }
  return process.env[name] || '';
};

module.exports = {
  HEADER_FOR,
  isHosted,
  contextFromHeaders,
  runWithContext,
  readSetting,
};

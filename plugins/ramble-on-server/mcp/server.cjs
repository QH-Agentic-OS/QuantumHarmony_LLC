/**
 * mcp/server.cjs
 *
 * Ramble On — MCP HTTP server (local on loopback, or hosted with RAMBLE_HOSTED=1) using the official `McpServer` API
 * from `@modelcontextprotocol/sdk/server/mcp.js`. Each tool is registered
 * via `server.registerTool(name, {title, description, inputSchema, annotations}, cb)`
 * with a Zod input shape; per-request the SDK validates arguments before
 * the handler runs and wraps handler exceptions as in-band tool errors
 * (`isError: true`) per MCP spec.
 *
 * Transport: Streamable HTTP (stateless), per-request server + transport
 * pair, since the SDK's stateless transport cannot be reused.
 *
 * Endpoints:
 *   GET  /health → readiness probe
 *   GET  /favicon.ico, /favicon.png, /apple-touch-icon.png → waveform icon
 *   POST /mcp    → MCP requests (JSON-RPC over Streamable HTTP)
 *   POST /       → alias for /mcp (backwards compat)
 */

'use strict';

const http = require('http');
const { McpServer } = require('@modelcontextprotocol/sdk/server/mcp.js');
const {
  StreamableHTTPServerTransport,
} = require('@modelcontextprotocol/sdk/server/streamableHttp.js');

const { CONFIG } = require('./env.cjs');
const {
  isHosted,
  contextFromHeaders,
  runWithContext,
} = require('./request-context.cjs');
const {
  handleOAuthRequest,
  isOAuthEnabled,
  readBearer,
  sendUnauthorized,
} = require('./oauth/server.cjs');
const { handleFaviconRequest } = require('./favicon.cjs');

// Tools a Notion sign-in (the connector) can use. The AI-provider tools need
// the user's own provider keys, which only the plugin's settings can supply.
const CONNECTOR_TOOLS = new Set([
  'ramble.kb_search',
  'ramble.kb_write',
  'ramble.get_voice_model',
]);

const KEY_SETTINGS = ['NOTION_API_KEY', 'GEMINI_API_KEY', 'ANTHROPIC_API_KEY', 'OPENAI_API_KEY'];
const { ALL_TOOLS } = require('./tools/index.cjs');

const SERVER_INFO = { name: 'ramble-on', version: '1.5.0' };

/**
 * Default response wrapper. Tools may override this by exporting
 * `formatResponse(result)` to shape their own response, for example one
 * that also emits `structuredContent`.
 *
 * @param {unknown} result Handler return value.
 * @returns {{content: Array<{type: string, text: string}>}}
 */
const defaultFormatResponse = (result) => ({
  content: [{ type: 'text', text: JSON.stringify(result) }],
});

/**
 * Creates a new MCP server instance with every Ramble On tool registered.
 *
 * @returns {import('@modelcontextprotocol/sdk/server/mcp.js').McpServer}
 */
const createMcpServer = ({ only } = {}) => {
  const server = new McpServer(SERVER_INFO, { capabilities: { tools: {} } });

  for (const tool of ALL_TOOLS) {
    if (only && !only.has(tool.name)) continue;
    const wrappedHandler = async (params) => {
      const result = await tool.handler(params || {});
      return tool.formatResponse
        ? tool.formatResponse(result)
        : defaultFormatResponse(result);
    };

    server.registerTool(
      tool.name,
      {
        title: tool.title,
        description: tool.description,
        inputSchema: tool.inputSchemaZod,
        annotations: tool.annotations,
      },
      wrappedHandler,
    );
  }

  return server;
};

let httpServer = null;

const writeJson = (res, statusCode, payload) => {
  res.writeHead(statusCode, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify(payload));
};

const applyCors = (req, res) => {
  const origin = req.headers.origin || '';
  if (
    origin.startsWith('http://127.0.0.1') ||
    origin.startsWith('http://localhost')
  ) {
    res.setHeader('Access-Control-Allow-Origin', origin);
  }
  res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
  res.setHeader(
    'Access-Control-Allow-Headers',
    'Content-Type, Authorization, Mcp-Session-Id, Mcp-Protocol-Version',
  );
  res.setHeader('Access-Control-Expose-Headers', 'Mcp-Session-Id, WWW-Authenticate');
};

/**
 * Handles a single MCP request with a freshly-constructed server +
 * transport (the SDK's stateless Streamable HTTP transport cannot be
 * reused across requests).
 *
 * @param {import('http').IncomingMessage} req
 * @param {import('http').ServerResponse} res
 * @returns {Promise<void>}
 */
const handleMcpRequest = async (req, res) => {
  // Work out who is calling and with which credentials.
  //   Local: settings come from the process environment.
  //   Hosted, Bearer token: a Notion sign-in through the connector; only the
  //     Notion tools are offered.
  //   Hosted, key headers: the plugin, with the user's own keys.
  //   Hosted, neither: answer 401 so Claude starts the Notion sign-in (when
  //     it's configured), otherwise serve the plugin tools with setup hints.
  let ctx = {};
  let only;
  if (isHosted()) {
    const bearer = readBearer(req.headers);
    if (bearer.present) {
      if (!bearer.notionToken) return sendUnauthorized(res, true);
      ctx = { NOTION_API_KEY: bearer.notionToken };
      only = CONNECTOR_TOOLS;
    } else {
      ctx = contextFromHeaders(req.headers);
      const hasKeys = KEY_SETTINGS.some((k) => ctx[k]);
      if (!hasKeys && isOAuthEnabled()) return sendUnauthorized(res);
    }
  }

  const server = createMcpServer({ only });
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
  });
  transport.onerror = (err) => {
    console.error('[ramble-on MCP] Transport error:', err);
  };

  try {
    await server.connect(transport);
    await runWithContext(ctx, () => transport.handleRequest(req, res));
  } finally {
    await transport.close().catch(() => {});
    await server.close().catch(() => {});
  }
};

/**
 * Starts the local MCP HTTP server used by desktop clients and tool
 * routing.
 *
 * @returns {Promise<import('http').Server>} The running HTTP server.
 */
const startMcpServer = async () => {
  if (httpServer) return httpServer;

  httpServer = http.createServer(async (req, res) => {
    applyCors(req, res);

    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    const pathname = (req.url || '').split('?')[0];

    if (handleFaviconRequest(req, res, pathname)) return;

    if (isHosted() && (await handleOAuthRequest(req, res))) return;

    if (req.method === 'GET' && pathname === '/health') {
      writeJson(res, 200, {
        status: 'ok',
        server: SERVER_INFO.name,
        version: SERVER_INFO.version,
      });
      return;
    }

    if (pathname === '/mcp' || pathname === '/') {
      try {
        await handleMcpRequest(req, res);
      } catch (err) {
        console.error('[ramble-on MCP] Request error:', err);
        if (!res.headersSent) {
          writeJson(res, 500, {
            jsonrpc: '2.0',
            id: null,
            error: { code: -32603, message: 'Internal error' },
          });
        }
      }
      return;
    }

    res.writeHead(404);
    res.end();
  });

  await new Promise((resolve, reject) => {
    const onError = (err) => {
      if (err.code === 'EADDRINUSE') {
        console.warn(
          `[ramble-on MCP] Port ${CONFIG.port} in use — MCP server not started. App will run without MCP.`,
        );
        httpServer = null;
        resolve();
      } else {
        reject(err);
      }
    };
    httpServer.once('error', onError);
    // Loopback only, unless this is the shared hosted server.
    const host = isHosted() ? '0.0.0.0' : '127.0.0.1';
    httpServer.listen(CONFIG.port, host, () => {
      httpServer.removeListener('error', onError);
      const toolNames = ALL_TOOLS.map((t) => t.name).join(', ');
      console.log(
        `[ramble-on MCP] Server running on ${host}:${CONFIG.port}${isHosted() ? ' (hosted mode)' : ''}`,
      );
      console.log(`[ramble-on MCP] Tools: ${toolNames}`);
      resolve();
    });
  });

  return httpServer;
};

/**
 * Stops the local MCP HTTP server when the Electron app is shutting down.
 *
 * @returns {Promise<void>} Resolves once the server is closed.
 */
const stopMcpServer = async () => {
  if (httpServer) {
    const server = httpServer;
    httpServer = null;
    await new Promise((resolve) => server.close(() => resolve()));
    console.log('[ramble-on MCP] Server stopped.');
  }
};

module.exports = {
  startMcpServer,
  stopMcpServer,
  createMcpServer,
  SERVER_INFO,
};

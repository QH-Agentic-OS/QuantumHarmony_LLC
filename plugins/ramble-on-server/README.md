# Ramble On Server

Source for the Ramble On MCP server, which gives the [Ramble On](../ramble-on) skill full Notion knowledge-base context, your stored voice model, and translation, transcription, and video tools on the AI provider you choose.

The same code runs two ways:

- **Hosted (what the `ramble-on` plugin uses):** one shared server on Render, at `https://ramble-on-mcp.onrender.com/mcp`. Each request carries the caller's own keys in headers.
- **Local (this plugin):** a stdio server on your computer, for running without the hosted server. It's distributed only through the Quantum Harmony marketplace, not Anthropic's plugin directory. Don't enable it together with `ramble-on`'s hosted connection, or the tools appear twice.

## Tools

- `ramble.translate`: raw input to a polished note, with Notion KB context
- `ramble.to_atp`: raw input to an Artemis Transmission Protocol block
- `ramble.to_platform_post`: raw input to a Medium, Substack, LinkedIn, or blog post
- `ramble.kb_search` / `ramble.kb_write`: search, read, and write pages in your Notion KB
- `ramble.get_voice_model`: reads your Voice Model page for calibration
- `ramble.generate_text`: low-level text completion on the configured provider
- `ramble.transcribe_audio`: transcribes a base64 audio clip
- `ramble.generate_video`: generates a short video from a prompt with Gemini Veo

## Install

```
/plugin marketplace add QH-Agentic-OS/QuantumHarmony_LLC
/plugin install ramble-on-server@quantum-harmony-marketplace
```

The skill ships in the `ramble-on` plugin. If you use both, turn off `ramble-on`'s hosted connection (or leave its settings empty and don't sign in), or the tools appear twice.

Claude Code installs the server's Node.js dependencies (from `package-lock.json`) when it installs the plugin. Node 20 or later is required.

## Configuration

Claude Code asks for these values when you enable the plugin. Change them later with `/plugin`, then **Configure** on `ramble-on-server`. API keys are marked sensitive, so Claude Code keeps them in your system's secure credential store, not in `settings.json`. Every value is optional: the skill degrades gracefully without them.

| Option | Purpose |
|---|---|
| `notion_api_key` | Notion integration token for KB and voice-model access |
| `notion_root_page` | ID of your Ramble On root page in Notion (share it with the integration) |
| `gemini_api_key` | Default translation provider; also audio transcription and video generation |
| `anthropic_api_key` | Optional provider, and the automatic fallback when the main provider fails |
| `openai_api_key` | Optional provider |
| `ai_provider` | `gemini` (default), `anthropic`, or `openai` |

The server reads these values only from the environment that Claude Code passes it. It never reads your shell profile or keychain.

### Provider fallback

Text generation runs on the selected provider (`ai_provider`, default Gemini). If that provider fails with an auth error, a retired model (404), or a quota `429`, the server retries on Anthropic when an Anthropic key is set. The switch is logged to stderr and never touches stdout, which is the JSON-RPC channel.

## Data and network use

The server runs locally over stdio, launched by Claude Code. It opens no port and runs no background process after the session ends. It contacts only these services, and only when a tool that needs one is called and you have set that service's key:

| Service | Endpoint | What is sent | When |
|---|---|---|---|
| Notion | `api.notion.com` | Search queries, page IDs, and the text you ask it to write | `kb_search`, `kb_write`, `get_voice_model`, and KB context for the translate tools |
| Google Gemini | `generativelanguage.googleapis.com` (via the `@google/genai` SDK) | Your input text with KB context; audio clips; video prompts | Translate tools and `generate_text` on the Gemini provider; `transcribe_audio`; `generate_video` |
| Anthropic | `api.anthropic.com` | Your input text with KB context | When Anthropic is the provider, or as the fallback |
| OpenAI | `api.openai.com` | Your input text with KB context; audio clips | When OpenAI is the provider, or for transcription on OpenAI |

Each request goes straight to that provider under your own API key and its terms. The plugin sends nothing to Quantum Harmony LLC or any other service, has no telemetry, and keeps no copy of your text. Anything it stores is what you ask `kb_write` to write into your own Notion workspace. Key values are never logged; at start-up the server checks each key's shape and prints only a masked fingerprint (prefix and length) to stderr when one looks malformed. To check a key yourself without storing it:

```bash
printf '%s' "$MY_KEY" | node mcp/bin/inspect-key.cjs ANTHROPIC_API_KEY
```

`mcp/bin/http.cjs` (a loopback HTTP transport on port 3748) is kept for the Ramble On desktop app and is **not** registered or started by this plugin.

## Running the hosted server

Hosted mode is turned on with `RAMBLE_HOSTED=1`. In that mode the server:

- listens on `0.0.0.0` at `$PORT` and serves MCP over Streamable HTTP at `/mcp` (stateless), with `/health` for health checks and the waveform icon at `/favicon.ico`, `/favicon.png` and `/apple-touch-icon.png` (no sign-in needed, so directory listings pick it up);
- takes every key and setting from the request's headers, never from its own environment, so no operator keys are needed or used:

| Header | Setting |
|---|---|
| `X-Notion-Api-Key` | Notion token |
| `X-Ramble-Notion-Root` | Notion root page ID |
| `X-Gemini-Api-Key` | Gemini key |
| `X-Anthropic-Api-Key` | Anthropic key |
| `X-OpenAI-Api-Key` | OpenAI key |
| `X-AI-Provider` | `gemini`, `anthropic`, or `openai` |

### Notion sign-in (MCP connector)

When these are also set, the hosted server becomes an OAuth 2.1 authorization server with Notion as the sign-in, so it can be listed as an MCP connector and used on claude.ai, Desktop, mobile, and Cowork:

| Variable | Value |
|---|---|
| `RAMBLE_PUBLIC_URL` | The server's public origin, e.g. `https://ramble-on-mcp.onrender.com` |
| `NOTION_OAUTH_CLIENT_ID` | From a Notion public integration |
| `NOTION_OAUTH_CLIENT_SECRET` | From the same integration (a secret) |
| `RAMBLE_TOKEN_KEY` | 32 random bytes, base64 (`openssl rand -base64 32`); a secret. Changing it signs everyone out |

The Notion integration's redirect URI is `$RAMBLE_PUBLIC_URL/oauth/notion/callback`.

How it works:

- An `/mcp` request with no keys and no token gets `401` with `WWW-Authenticate: Bearer resource_metadata=…`, which starts sign-in in Claude.
- Metadata: `/.well-known/oauth-protected-resource/mcp` (RFC 9728) and `/.well-known/oauth-authorization-server` (RFC 8414). Clients register through stateless DCR at `/oauth/register`, or with a Client ID Metadata Document from a Claude host. Only Claude's redirect URIs are accepted: `https://claude.ai/api/mcp/auth_callback` and loopback `http://localhost|127.0.0.1:*/callback`.
- `/oauth/authorize` shows a short consent page, then sends the user to Notion. `/oauth/notion/callback` exchanges Notion's code and returns our code to Claude. `/oauth/token` does the code exchange (PKCE S256 required) and refresh. Refreshes also refresh the Notion token.
- Nothing is stored. Codes and tokens are AES-256-GCM sealed blobs that carry the Notion tokens. Access tokens last 1 hour, refresh tokens 90 days. Because nothing is stored, an old refresh token stays usable until it expires; rotating `RAMBLE_TOKEN_KEY` revokes everything.
- A signed-in caller gets only `kb_search`, `kb_write`, and `get_voice_model` (Claude shows them as `ramble_kb_search`, `ramble_kb_write`, `ramble_get_voice_model`). A sign-in never uses a root page ID: `get_voice_model` takes the first shared page whose title contains "Voice Model", and `kb_write` without a `page_id` creates new pages under the first shared page whose title contains "Ramble On" (with the space; `Ramble_On` doesn't match). User-facing setup is in the [Ramble On README](../ramble-on/README.md#option-1-sign-in-with-notion).
- Only Claude's redirect URIs are accepted, so generic clients such as MCP Inspector are refused at registration by design. Test by connecting the server in Claude as a custom connector.

Test the flow with `npm run test:oauth` (Notion mocked).

Render settings: root directory `plugins/ramble-on-server`, runtime Node, build `npm ci`, start `node mcp/bin/http.cjs`, environment `RAMBLE_HOSTED=1`, health check path `/health`.

## Changelog

### 1.5.0
- Added Notion sign-in (OAuth) for use as an MCP connector, off until its environment variables are set.
- Added hosted mode (`RAMBLE_HOSTED=1`): per-request keys from headers, public bind, `/health` reports the version. The Gemini video download now sends the key as a header instead of in the URL.
- Split out of the `ramble-on` plugin (previously its bundled `mcp/` server, version 1.4.0). Configuration and behavior are unchanged, except that `ramble.get_skill` is removed: the skill now ships in the `ramble-on` plugin.

## License

Apache License 2.0. See [LICENSE](LICENSE).

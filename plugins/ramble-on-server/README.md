# Ramble On Server

Local MCP server for the [Ramble On](../ramble-on) skill. It gives the skill full Notion knowledge-base context, your stored voice model, and translation, transcription, and video tools on the AI provider you choose. Install it alongside the `ramble-on` plugin; the skill works without it, with less personal context.

This plugin runs code on your computer, so it is distributed only through the Quantum Harmony marketplace, not Anthropic's plugin directory.

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
/plugin install ramble-on@quantum-harmony-marketplace
/plugin install ramble-on-server@quantum-harmony-marketplace
```

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

## Changelog

### 1.5.0
- Split out of the `ramble-on` plugin (previously its bundled `mcp/` server, version 1.4.0). Configuration and behavior are unchanged, except that `ramble.get_skill` is removed: the skill now ships in the `ramble-on` plugin.

## License

Apache License 2.0. See [LICENSE](LICENSE).

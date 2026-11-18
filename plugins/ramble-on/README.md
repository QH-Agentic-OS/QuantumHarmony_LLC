# Ramble On

Signal translation layer for fast, non-linear thinkers. Converts raw rambles, voice-note transcripts, and stream-of-consciousness input into polished notes, ATP blocks, or platform-ready posts — calibrated against a Notion-hosted voice model so the output sounds like you, not like a model.

## What's in the box

| Component | Path | Purpose |
|---|---|---|
| Skill | `skills/ramble-on/` | Translation modes, voice calibration, KB routing logic |
| MCP server | `mcp/` | Notion KB access, voice-model retrieval, AI-provider translation tools |
| Server registration | `.mcp.json` | Auto-launches the server over stdio when the plugin enables |

## Tools exposed (when the server is running)

- `ramble.translate`: raw input to a polished note, with Notion KB context
- `ramble.to_atp`: raw input to an Artemis Transmission Protocol block
- `ramble.to_platform_post`: raw input to a Medium, Substack, LinkedIn, or blog post
- `ramble.kb_search` / `ramble.kb_write`: search, read, and write pages in your Notion KB
- `ramble.get_voice_model`: reads your Voice Model page for calibration
- `ramble.get_skill`: returns this plugin's SKILL.md
- `ramble.generate_text`: low-level text completion on the configured provider
- `ramble.transcribe_audio`: transcribes a base64 audio clip
- `ramble.generate_video`: generates a short video from a prompt with Gemini Veo

## Install

```
/plugin marketplace add QH-Agentic-OS/QuantumHarmony_LLC
/plugin install ramble-on@quantum-harmony-marketplace
```

Claude Code installs the server's Node.js dependencies (from `package-lock.json`) when it installs the plugin, so there is no separate `npm install` step. Node 20 or later is required.

## Configuration

Claude Code asks for these values when you enable the plugin. Change them later with `/plugin`, then **Configure** on `ramble-on`. API keys are marked sensitive, so Claude Code keeps them in your system's secure credential store, not in `settings.json`. Every value is optional: the skill degrades gracefully without them.

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

## Graceful degradation

The skill works at three tiers — the server is an amplifier, not a dependency:

1. **`ramble.*` tools available** → full signal, full KB, full voice model
2. **Notion MCP connected, no server** → good signal, live KB, no local persistence
3. **Neither** → capable instruction-based translation, no personal context

## Requirements

- Node 20+
- Claude Code with plugin support

## Changelog

### 1.4.0
- **Fix:** The MCP server failed to start on a fresh install ("Cannot find module"), because its dependencies needed a manual `npm install`. `package.json` and `package-lock.json` now sit at the plugin root, so Claude Code installs them with the plugin.
- **Change:** API keys and settings now come from the plugin's own configuration (`userConfig`, with keys stored as sensitive) instead of the shell environment and macOS Keychain. The `sidecar.sh` and `seed-keychain.sh` scripts are removed, and the server is launched directly with `node`.
- **Change:** The Notion root page is now a setting (`notion_root_page`) instead of a built-in page ID.
- **Fix:** `ramble.get_skill` read a path outside the plugin; it now reads `skills/ramble-on/SKILL.md`.
- **License:** Apache 2.0, matching the rest of the repository (the manifest said MIT). `LICENSE` is now in the plugin folder.
- **Docs:** Added a data and network use section, the full tool list, and the marketplace install line.

### 1.3.0
- **Fix:** Anthropic text generation returned `404` — the pinned model
  `claude-3-5-sonnet-latest` retired 2026-02-19. Now uses `claude-opus-4-8`
  (override with `ANTHROPIC_TEXT_MODEL`).
- **Add:** Automatic provider fallback to Anthropic when the primary provider
  fails (auth error, 404, or quota `429`).
- **Add:** Malformation-visible key input. The seed script and a new
  `bin/inspect-key.cjs` report a masked fingerprint plus structural issues so a
  bad paste is caught without exposing the secret; the server also warns on
  stderr at spawn if a stored key is malformed.
- **Chore:** Removed the legacy root `plugins/.mcp.json` (superseded by the
  sidecar launcher in this plugin's `.mcp.json`).

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Attribution

Sole intellectual origin, Quantum Harmony LLC. One theoretical credit: Donald O. Hebb — Hebbian learning as the foundational principle behind the KB-as-context-layer design.

# Ramble On

Signal translation layer for fast, non-linear thinkers. Ramble On turns raw rambles, voice-note transcripts, and stream-of-consciousness input into polished notes, ATP (Artemis Transmission Protocol) blocks, or platform-ready posts for Medium, Substack, LinkedIn, or a blog. It keeps your voice: the output should sound like you on your clearest day, not like a model.

## What's in the box

| Component | Path | Purpose |
|---|---|---|
| Skill | `skills/ramble-on/SKILL.md` | Translation modes, voice calibration, KB routing |
| Platform guide | `skills/ramble-on/references/platform-guides.md` | Structure and tone rules for each publishing platform |
| Voice guide | `skills/ramble-on/references/voice-calibration.md` | How the skill learns and keeps your voice |
| Server connection | `.mcp.json` | Connects to the hosted Ramble On MCP server at `https://ramble-on-mcp.onrender.com/mcp` |

The plugin installs nothing that runs on your computer. The `ramble.*` tools run on the hosted server, using your own API keys.

## Hosted server tools

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
```

## How it works

Paste a brain dump, a dictation transcript, or rough notes and ask Claude to clean it up, translate it, or turn it into a post. The skill picks a mode (clean note, ATP block, or platform post), keeps your rhythm and vocabulary, and asks at most one question when the voice feels off.

It uses whatever context is already available, in three tiers:

1. **Ramble On server tools (`ramble.*`) available:** full Notion KB context and your stored voice model, through the hosted server once you add your keys.
2. **A Notion connector, no server:** live KB context through your Notion connector.
3. **Neither:** capable instruction-based translation with no personal context.

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

Claude Code sends these values to the hosted server as HTTPS request headers on each tool call. The server uses them for that request only and never stores or logs them.

### Provider fallback

Text generation runs on the selected provider (`ai_provider`, default Gemini). If that provider fails with an auth error, a retired model (404), or a quota `429`, the server retries on Anthropic when an Anthropic key is set. The switch is logged to stderr and never touches stdout, which is the JSON-RPC channel.

## Data and network use

The skill itself runs nothing. The hosted server is called only when Claude uses a `ramble.*` tool, and it contacts only the services below, only for the tool being called, and only under your own keys:

| Service | Endpoint | What is sent |
|---|---|---|
| Ramble On hosted server | `ramble-on-mcp.onrender.com` (run by Quantum Harmony LLC on Render) | The tool's input and your plugin settings, including your API keys, over HTTPS |
| Notion | `api.notion.com` | Search queries, page IDs, and the text you ask it to write |
| Google Gemini | `generativelanguage.googleapis.com` | Your input text with KB context; audio clips; video prompts |
| Anthropic | `api.anthropic.com` | Your input text with KB context, when Anthropic is the provider or the fallback |
| OpenAI | `api.openai.com` | Your input text with KB context; audio clips, when OpenAI is used |

The hosted server is stateless. It stores nothing and never logs your keys or content. There is no telemetry. Full details are in the [privacy policy](PRIVACY.md).

## Changelog

### 1.5.0
- **Change:** The MCP server no longer runs on your computer. The plugin connects to the hosted Ramble On server over HTTPS and passes your own keys from the plugin settings with each call. The server's source and a local option live in the `ramble-on-server` plugin.
- **Change:** `ramble.get_skill` is removed; the skill ships in this plugin.
- **Docs:** Added a privacy policy.

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

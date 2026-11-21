# Ramble On

Signal translation layer for fast, non-linear thinkers. Ramble On turns raw rambles, voice-note transcripts, and stream-of-consciousness input into polished notes, ATP (Artemis Transmission Protocol) blocks, or platform-ready posts for Medium, Substack, LinkedIn, or a blog. It keeps your voice: the output should sound like you on your clearest day, not like a model.

## What's in the box

| Component | Path | Purpose |
|---|---|---|
| Skill | `skills/ramble-on/SKILL.md` | Translation modes, voice calibration, KB routing |
| Platform guide | `skills/ramble-on/references/platform-guides.md` | Structure and tone rules for each publishing platform |
| Voice guide | `skills/ramble-on/references/voice-calibration.md` | How the skill learns and keeps your voice |
| Server connection | `.mcp.json` | Connects to the hosted Ramble On MCP server |
| Privacy policy | `PRIVACY.md` | What the hosted server receives, and that it stores nothing |

The plugin installs nothing that runs on your computer. Its tools run on the hosted Ramble On server, which is stateless and stores nothing.

## Install

```
/plugin marketplace add QH-Agentic-OS/QuantumHarmony_LLC
/plugin install ramble-on@quantum-harmony-marketplace
```

The skill works on its own. To give it your Notion knowledge base and voice model, connect the hosted server in one of the two ways below.

## The hosted server

| | |
|---|---|
| URL | `https://ramble-on-mcp.onrender.com/mcp` |
| Transport | Streamable HTTP (stateless) |
| Sign-in | OAuth 2.1, with Notion as the sign-in |
| Run by | Quantum Harmony LLC, on Render |

There are two ways to use it:

1. **Sign in with Notion** (the Ramble On connector). Works in Claude on the web, desktop, mobile, Cowork, and Claude Code. You get the three Notion tools; Claude does the writing itself, guided by the skill. No keys needed.
2. **Your own keys in the plugin settings** (Claude Code). You get every tool, including the server-side translate, ATP, and post tools, which run on your own AI provider key.

If you install the plugin and leave every key empty, Claude starts the Notion sign-in the first time a Ramble On tool runs, so option 1 is also the plugin's default.

## Option 1: Sign in with Notion

### Connect

Add the Ramble On connector in Claude, or add a custom connector with the URL above. Claude registers itself with the server automatically (dynamic client registration, or a Client ID Metadata Document from a Claude host), so there is no client ID or secret to enter.

The server accepts only Claude's redirect URIs: `https://claude.ai/api/mcp/auth_callback` and loopback `http://localhost:*/callback` or `http://127.0.0.1:*/callback`. Generic OAuth clients such as MCP Inspector are refused at registration. That is by design, not an outage. To test the server, connect it in Claude as a custom connector and run each tool there.

### Share the right pages

Notion's consent screen asks which pages Ramble On may use. Ramble On sees only those pages and the pages inside them, so share these:

- **A root page titled exactly `Ramble On`.** The server finds it by its title, so the space matters: a page titled `Ramble_On` is not found. New pages that `kb_write` creates without a `page_id` go under it. The server takes the first page whose title contains "Ramble On", so avoid giving other shared pages titles that contain "Ramble On".
- **A page titled `Voice Model`**, best kept inside the `Ramble On` page. `get_voice_model` finds it by title. If there is none, the tool returns "not found" and the skill offers to set one up.
- **The knowledge base pages you want searched.** `kb_search` only sees shared pages. If a search comes back empty, reconnect Ramble On and share more pages on the consent screen.

### Tools

| Tool | Access | What it does |
|---|---|---|
| `ramble.kb_search` | Read-only | Searches your shared Notion pages; returns titles, IDs, and URLs |
| `ramble.get_voice_model` | Read-only | Reads your `Voice Model` page so output matches your voice |
| `ramble.kb_write` | Writes | Creates a child page (pass `title`), or appends to a page (pass `page_id`) |

Claude shows these as `ramble_kb_search`, `ramble_get_voice_model`, and `ramble_kb_write`. `kb_write` never deletes or overwrites; it only adds pages and paragraphs.

### Signing out

Disconnect Ramble On in Claude, or remove Ramble On's access in Notion's settings. Otherwise a sign-in lasts up to 90 days.

## Option 2: Your own keys (Claude Code)

Claude Code asks for these values when you enable the plugin. Change them later with `/plugin`, then **Configure** on `ramble-on`. Keys are marked sensitive, so Claude Code keeps them in your system's secure credential store, not in `settings.json`. Every value is optional.

| Option | Purpose |
|---|---|
| `notion_api_key` | Notion integration token for KB and voice-model access |
| `notion_root_page` | ID of your Ramble On root page in Notion (share it with your integration) |
| `gemini_api_key` | Default translation provider; also audio transcription and video generation |
| `anthropic_api_key` | Optional provider, and the automatic fallback when the main provider fails |
| `openai_api_key` | Optional provider |
| `ai_provider` | `gemini` (default), `anthropic`, or `openai` |

Claude Code sends these values to the hosted server as HTTPS request headers on each tool call. The server uses them for that request only and never stores or logs them.

With a root page ID set, `get_voice_model` looks for a child page titled `Voice Model` directly under it, and `kb_write` creates new pages under it. The root page setting works only together with `notion_api_key`; under a Notion sign-in the server finds pages by title, as described above.

### All tools with your own keys

- `ramble.translate`: raw input to a polished note, with Notion KB context
- `ramble.to_atp`: raw input to an Artemis Transmission Protocol block
- `ramble.to_platform_post`: raw input to a Medium, Substack, LinkedIn, or blog post
- `ramble.kb_search`, `ramble.kb_write`, `ramble.get_voice_model`: as above
- `ramble.generate_text`: low-level text completion on the configured provider
- `ramble.transcribe_audio`: transcribes a base64 audio clip
- `ramble.generate_video`: generates a short video from a prompt with Gemini Veo

### Provider fallback

Text generation runs on the selected provider (`ai_provider`, default Gemini). If that provider fails with an auth error, a retired model (404), or a quota `429`, the server retries on Anthropic when an Anthropic key is set.

## How it works

Paste a brain dump, a dictation transcript, or rough notes and ask Claude to clean it up, translate it, or turn it into a post. The skill picks a mode (clean note, ATP block, or platform post), keeps your rhythm and vocabulary, and asks at most one question when the voice feels off.

It uses whatever context is available, in three tiers:

1. **Ramble On tools available** (Notion sign-in or your own keys): your Notion KB and your stored voice model.
2. **A Notion connector, no Ramble On server:** live KB context through your Notion connector.
3. **Neither:** capable instruction-based translation with no personal context.

## Data and network use

The skill itself runs nothing. The hosted server is called only when Claude uses a Ramble On tool, and it contacts only the services below, only for the tool being called:

| Service | Endpoint | What is sent |
|---|---|---|
| Ramble On hosted server | `ramble-on-mcp.onrender.com` (Quantum Harmony LLC, on Render) | The tool's input, plus either your sealed Notion sign-in or your plugin settings and keys, over HTTPS |
| Notion | `api.notion.com` | Search queries, page IDs, and the text you ask it to write |
| Google Gemini | `generativelanguage.googleapis.com` | With your own key only: input text with KB context; audio clips; video prompts |
| Anthropic | `api.anthropic.com` | With your own key only: input text with KB context, when Anthropic is the provider or the fallback |
| OpenAI | `api.openai.com` | With your own key only: input text with KB context; audio clips |

A Notion sign-in reaches Notion only. Ramble On stores nothing: no database, no files, no copies of your input, output, keys, or Notion sign-in, and no telemetry. Your Notion tokens travel encrypted inside the tokens Claude keeps for you. Full details are in the [privacy policy](PRIVACY.md).

## Running the server yourself

The server's source, its environment variables, and a local stdio option are in the [`ramble-on-server`](../ramble-on-server) plugin.

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

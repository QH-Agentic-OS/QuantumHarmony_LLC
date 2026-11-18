# Ramble On

Signal translation layer for fast, non-linear thinkers. Ramble On turns raw rambles, voice-note transcripts, and stream-of-consciousness input into polished notes, ATP (Artemis Transmission Protocol) blocks, or platform-ready posts for Medium, Substack, LinkedIn, or a blog. It keeps your voice: the output should sound like you on your clearest day, not like a model.

## What's in the box

| Component | Path | Purpose |
|---|---|---|
| Skill | `skills/ramble-on/SKILL.md` | Translation modes, voice calibration, KB routing |
| Platform guide | `skills/ramble-on/references/platform-guides.md` | Structure and tone rules for each publishing platform |
| Voice guide | `skills/ramble-on/references/voice-calibration.md` | How the skill learns and keeps your voice |

This plugin is instructions only. It contains no scripts, no server, and no dependencies.

## Install

```
/plugin marketplace add QH-Agentic-OS/QuantumHarmony_LLC
/plugin install ramble-on@quantum-harmony-marketplace
```

## How it works

Paste a brain dump, a dictation transcript, or rough notes and ask Claude to clean it up, translate it, or turn it into a post. The skill picks a mode (clean note, ATP block, or platform post), keeps your rhythm and vocabulary, and asks at most one question when the voice feels off.

It uses whatever context is already available, in three tiers:

1. **Ramble On server tools (`ramble.*`) available:** full Notion KB context and your stored voice model. The server is optional and ships separately as the `ramble-on-server` plugin in the same marketplace.
2. **A Notion connector, no server:** live KB context through your Notion connector.
3. **Neither:** capable instruction-based translation with no personal context.

## Data and network use

The plugin itself runs nothing and sends nothing anywhere. It adds instructions that Claude follows inside your conversation. When you have a Notion connector or the optional Ramble On server connected, the skill may ask Claude to read or write your Notion pages through them; those tools disclose their own data handling.

## Changelog

### 1.5.0
- **Change:** Ramble On is now a skill-only plugin. The local MCP server moved to its own plugin, `ramble-on-server`, so the skill can be listed on its own.

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

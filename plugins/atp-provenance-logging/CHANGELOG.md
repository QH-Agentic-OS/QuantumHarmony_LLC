# Changelog

## 2.0.0
- **Plugin, not just a skill.** Bundles the Prove provenance service, the ATP
  Mission Control dashboard and capture hooks alongside the skill.
- **Harness step capture.** Hooks for SessionStart, UserPromptSubmit,
  PostToolUse, Stop and SubagentStop forward the session transcript to
  `POST /ingest/trajectory`; Prove records each step as a hash-chained child.
- **Three modes.** `standalone` (default, local service started by the hooks),
  `offline` (loopback only, nothing leaves the machine) and `hosted` (your own
  deployment over https with a token), set in the plugin settings.
- **Network-free dashboard.** React 18.3.1 vendored; no CDN. Adds
  `ui/prove-offline.html`, a single file that opens from disk.
- **Skill updated** to the current contract: one root per session (minted by
  the hooks), ATP prompt and response as markers under it, `prove_log.py`
  helper, `self_reported` entries. Without a captured session the helper binds
  and mints its own root.
- **Local service is same-origin only.** No CORS grant; requests from another
  origin, a `null` origin or a non-loopback Host are refused, so a web page
  cannot read or change the local ledger.
- **Strict mode** refuses a prompt when Prove is unreachable, rejects the
  token, the endpoint setting is invalid, or capture fails.
- Adds `PRIVACY.md`, plugin tests, and `server/SOURCE.md` sync notes.

## 1.0.0
- Initial ATP provenance-logging skill packaged as a plugin.

## 1.1.0

- **ATP Integration:** Added ATP provenance-logging skill to ATP provenance-logging plugin, creating a functional bridge between ATP and provenance logging for standardized communication.
- **Cloud Code Compatibility:** Enhanced compatibility with Claude Code IDE (added `CLAUDE.md` and `GEMINI.md`), ensuring proper plugin loading and user-facing documentation in the IDE.
- **Plugin Metadata:** Refined `plugin.json` and `README.md` for clarity, versioning, and marketplace presentation.

### Changes
- Modified `plugin.json` to include new dependencies and metadata.
- Updated `README.md` with compatibility information and project overview.
- Created `CHANGELOG.md` for version tracking.`
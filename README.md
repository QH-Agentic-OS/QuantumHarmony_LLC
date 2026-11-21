# Quantum Harmony
Agent infrastructure for [Artemis City](https://artemiscity.com), published by Quantum Harmony LLC.

This repository is a Claude Code plugin marketplace named `quantum-harmony-marketplace`. The
catalog lives at `.claude-plugin/marketplace.json`; each plugin lives under `plugins/<name>/` with
its own `.claude-plugin/plugin.json` and README.

## Plugins

| Plugin | Version | Description |
| --- | --- | --- |
| [`artemis-transmission-protocol`](plugins/artemis-transmission-protocol) | 1.1.0 | Structured agent-to-agent communication via the Artemis Transmission Protocol (ATP). |
| [`atp-provenance-logging`](plugins/atp-provenance-logging) | 1.0.0 | Line-item action provenance (parent + child `prov_id` in `agent_logs`; halt-and-alert on log failure). |
| [`agent-scaffolder`](plugins/agent-scaffolder) | 1.0.0 | Scaffold AI agents from an Agent Card; generates system prompts + `index.md` / `AGENTS.md` / `.codex/instructions.md`. |
| [`agent-definition`](plugins/agent-definition) | 1.0.0 | Build an Agent Card and write it to `agents/NAME/AGENTS.md`, inheriting parent `.agents` governance. |
| [`project-scaffolder`](plugins/project-scaffolder) | 1.0.0 | Scaffold a project's `.agents/` governance frame (`instructions.md`, `index.md`, seeded `logs/`). |
| [`ramble-on`](plugins/ramble-on) | 1.5.0 | Signal translation: raw brain dumps to voice-preserving notes, ATP blocks, and platform posts, with a hosted MCP server for your Notion KB. |
| [`ramble-on-server`](plugins/ramble-on-server) | 1.5.0 | Source of the Ramble On MCP server, and a local stdio alternative to the hosted one. |

**The stack:** `project-scaffolder` lays the governance frame → `agent-definition` / `agent-scaffolder`
define agents → `artemis-transmission-protocol` carries messages between them → `atp-provenance-logging`
records every action → `ramble-on` polishes reflections into the Notion KB.

## Install

```
/plugin marketplace add QH-Agentic-OS/QuantumHarmony_LLC
/plugin install artemis-transmission-protocol@quantum-harmony-marketplace
/plugin install ramble-on@quantum-harmony-marketplace
# …repeat for any plugin above
```

The source accepts a GitHub `owner/repo` shorthand, a git URL, a remote URL to `marketplace.json`,
or a **local directory path** (no GitHub or auth needed). Install either `ramble-on` (hosted server)
or `ramble-on-server` (local server), not both: they register the same tools, which would then
appear twice. Setup for each is in its own README.

## Anthropic's directory

`ramble-on` is also submitted to Anthropic's plugin directory, and its hosted server
(`https://ramble-on-mcp.onrender.com/mcp`) as an MCP connector. The directory listing is built from
`plugins/ramble-on` on `main`, so changes merged there, README included, flow into the listing.
Keep work in progress on a branch until it's ready.

## Local testing (no GitHub)

```
/plugin marketplace add /absolute/path/to/QuantumHarmony_LLC
claude --plugin-dir /absolute/path/to/QuantumHarmony_LLC/plugins/ramble-on   # single plugin
```

## Validate before publishing

```
claude plugin validate ./plugins/<name>
```

## Adding more plugins

Create `plugins/<new>/.claude-plugin/plugin.json`, drop components alongside it
(`skills/`, `agents/`, `hooks/`, `.mcp.json`), add an entry to the `plugins` array in
`.claude-plugin/marketplace.json`, and add a row to the table above.

## License

Apache License 2.0. See [LICENSE](LICENSE).

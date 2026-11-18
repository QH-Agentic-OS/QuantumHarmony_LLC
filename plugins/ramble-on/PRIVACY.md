# Ramble On privacy policy

Last updated: November 18, 2026. Published by Quantum Harmony LLC.

This policy covers the Ramble On plugin and the hosted Ramble On MCP server at `ramble-on-mcp.onrender.com`.

## What the plugin does on its own

The Ramble On skill is instructions that Claude follows inside your conversation. It runs no code on your computer and sends nothing anywhere by itself.

## What the hosted server receives

When Claude calls one of the `ramble.*` tools, Claude Code sends the hosted server:

- the tool's input, such as the text you asked it to translate, an audio clip to transcribe, or a Notion search query;
- the API keys and settings you entered in the plugin's settings, sent as HTTPS request headers: your Notion token, Notion root page ID, Gemini, Anthropic, and OpenAI keys, and your choice of provider.

## How it is used

The server uses your input and your keys only to make the requests that the tool needs, and only to these services:

| Service | What is sent |
|---|---|
| Notion (`api.notion.com`) | Search queries, page IDs, and text you ask it to write, under your Notion token |
| Google Gemini (`generativelanguage.googleapis.com`) | Your input text with Notion context, audio clips, video prompts, under your Gemini key |
| Anthropic (`api.anthropic.com`) | Your input text with Notion context, under your Anthropic key |
| OpenAI (`api.openai.com`) | Your input text with Notion context, and audio clips, under your OpenAI key |

Each of those services handles your data under its own terms and privacy policy, with your own account.

## What is stored

Nothing. The server is stateless: it keeps no database, files, or copies of your input, its output, or your keys. It never writes your keys, input, or output to its logs; when a request fails, it logs only the error message returned by the failing service. Keys exist in memory only for the request that carried them. The only lasting record is anything you ask `kb_write` to write into your own Notion workspace.

The server runs on Render. Render's platform keeps standard request logs, such as time, path, status code, and IP address, under Render's own privacy policy. There is no analytics or telemetry, and nothing is sold or shared with anyone else.

## Children

Ramble On is not intended for people under 18.

## Changes and contact

Changes to this policy are made in this file and recorded in the repository's history. Questions can be raised as an issue on the [QuantumHarmony_LLC repository](https://github.com/QH-Agentic-OS/QuantumHarmony_LLC).

---
name: atp-provenance-logging
description: Create a parent provenance ID for each ATP prompt and log every agent action (tool calls, reads, writes, executes) as child entries in agent_logs with parent_prov_id linking back to the ATP prompt. Use when the user asks for ATP/Artemis provenance, an audit trail of agent actions, or to open the Prove (ATP Mission Control) dashboard.
---

# ATP Provenance Logging

Every agent action must be traceable to the prompt that caused it. This plugin
does that in two layers:

1. **Harness capture (automatic).** The plugin's hooks forward the session
   transcript to Prove (`POST /ingest/trajectory`) on every prompt, tool call,
   stop and sub-agent stop. Prove parses each record into a hash-chained child
   step. You do not write these entries and cannot leave any out.
2. **ATP structure (this skill).** For an ATP prompt you add the root and the
   response marker, and log any action the transcript cannot show (for
   example work done outside Claude Code). Prove stamps these entries
   `self_reported`, and a binding can be set to refuse them.

## When to use
Use this skill whenever the user requests ATP/Artemis protocol **and** wants
provenance logging, asks for line-item tracking of agent actions in
`agent_logs`, or asks to see the provenance dashboard.

## Modes (set in the plugin's settings)
- **standalone** (default): Prove runs on this machine at `http://127.0.0.1:8787`.
  The hooks start it at session start. Ledger: `~/.prove/provenance.db`.
- **offline**: the same local service, but nothing may leave the machine. Any
  non-loopback service URL is refused and no token is ever sent.
- **hosted**: your own deployed Prove (`service_url`, https) with an API token.

## Workflow (enforced)

### 0) Preconditions
- Check the service: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prove_local.py" status`
  (hosted: `curl -s "$PROVENANCE_SERVICE_URL/health"`).
- Standalone/offline and not running: `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prove_local.py" start`.
- If the service is unavailable, **do not proceed with actions**. Alert the
  user immediately and ask for remediation.
- Never log secrets. Prove redacts secret-named keys and obvious token shapes;
  keep inputs minimal anyway.

### 1) Mint the ATP root (one per ATP prompt)
```bash
ID=$(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prove_log.py" begin \
  --agent claude-code --model "<model id if known>" \
  --context "<sanitized user prompt + context sources>" --plan "<one-line intent>")
```
`begin` binds the four manifest layers (declaration → version → session →
route) under one `manifest_binding_id`, then mints the root with that binding
in a single `POST /mint`. Never re-send the root via `/log`.
If it exits non-zero: **alert the user and stop**. No action is valid without
the root `prov_id`.

### 2) Emit the ATP header with the root prov_id
- Output the ATP header first; append `prov_id=<uuid>` to `[[Special Instructions]]`
  (`; prov_id=<uuid>` if it already has content).
- If the user supplied a header, keep their values and only add the `prov_id`.

### 3) Actions
- Inside Claude Code the hooks already record every read, write, command and
  tool call. Do not duplicate them.
- Log an action yourself only when the transcript cannot show it, or when the
  hooks are off (`capture` setting false, or another harness):
  ```bash
  python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prove_log.py" log "$ID" \
    --phase read_file|write_file|execute_command|tool_call \
    --target "<path, command or tool>" --summary "<brief result>" [--status error --error "<msg>"]
  ```
- Failures are logged as children with `--status error`; lineage is kept.
- If any write fails (non-zero exit): **alert the user and stop**.

### 4) Log the ATP response (required)
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prove_log.py" end "$ID" --summary "<what was done>"
```
If this fails: **alert the user and stop**. The response is invalid without it.

### 5) Verify and show
- `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/prove_log.py" verify "$ID"` checks the
  hash chain, sequence and manifest refs.
- Dashboard (standalone/offline): `http://127.0.0.1:8787/`. Paste the root
  `prov_id` into **watch existing chain**, or export with
  `prove_log.py chain "$ID" > run.json` and use **Import JSON**.
- No server at all: open `ui/prove-offline.html` from disk and import the JSON.

## Transport reference (HTTP)
Base URL `$PROVENANCE_SERVICE_URL` (default `http://127.0.0.1:8787`); a hosted
Prove needs `Authorization: Bearer $PROV_API_TOKEN` over https.
- `POST /manifest/bind` `{layer, manifest_binding_id, body, parent_ref, session_id?}`
- `POST /mint` `{agent_id, actor, model, manifest_binding_id, atp_context, input, output, tags}`
- `POST /log` `{parent_prov_id, manifest_binding_id, agent_id, actor, phase, action_type, target, payload_summary, input, output, status, error, tags}`
  (no complete manifest context → `422`; duplicate child id → `409`)
- `GET /chain?parent_prov_id=` export, `GET /verify?parent_prov_id=` integrity report
- `POST /ingest/trajectory` harness capture (used by the hooks)
- `GET /health`

## Required guarantees
- Exactly **one** root `prov_id` per ATP prompt.
- Every action is a child with `parent_prov_id` set to that root, chained by
  `prev_action_hash` within its binding.
- Any missing provenance invalidates the output and triggers human review.

## Governance posture
- Assume continuous monitoring, logging and review; treat every prompt as
  evaluation-grade.
- Do not speculate about alerting or scoring systems; the orchestrator and
  humans define them.
- Keep `actor` names consistent (`claude-code`, `shell_command`, `mcp__<server>`)
  so rollups stay clean.

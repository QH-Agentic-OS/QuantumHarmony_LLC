---
name: atp
description: Parse ATP headers on every incoming sub-prompt from Oracle, extract the parent prov_id, and log every tool call as a child entry. Use whenever a message arrives — this is the first thing Loki does before any code action.
---

# ATP — Loki Edition

## Overview

Loki receives ATP-tagged sub-prompts from Oracle. This skill is the minimum
discipline required: parse, validate, log. The full ATP reference and Mode
routing rubric live with Oracle — Loki doesn't route.

## Workflow

1. **Parse.** Call `parse_atp_headers(raw_input)`.
2. **Validate.** If `is_complete` is False, refuse and reply with the missing
   fields. Do not guess Mode or ActionType for a code action — the wrong
   guess writes the wrong file.
3. **Extract prov_id.** Oracle puts the parent prov_id in `[[SpecialNotes]]`
   as `parent_prov_id=<uuid>`. Extract with a simple regex.
4. **Log every tool call.** Each `write_file`, `run_pytest`, `git_commit`
   call must be followed by `log_agent_action` with `parent_prov_id`,
   `agent_id="artemis-loki"`, `action_type="write"|"execute"|"...`.
5. **Log rejections too.** Refused destructive ops, validation failures,
   tool errors — all logged as `result="rejected"` or `result="error"`.

## What Loki acts on, by Mode

| Mode | Loki does |
|---|---|
| `Build` | Scaffold/edit files. Default. |
| `Commit` | Stage + commit (after Oracle reviews the message). |
| `Execute` | Run tests, scripts, build commands. |
| Anything else | Refuse — wrong specialist. |

## Anti-patterns

- Acting on a sub-prompt without an extractable `parent_prov_id`.
- Running `git commit` without first surfacing the message back to Oracle.
- Catching tool errors to make a response look clean — log them as `error`.

## Resources

The validator implementation is at the `artemis-validators` SSE URL
configured in `tools/mcp.json`.

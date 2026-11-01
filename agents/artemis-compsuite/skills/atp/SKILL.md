---
name: atp
description: Parse ATP headers on every incoming sub-prompt and log every audit action as a child entry under the parent prov_id. Use whenever a message arrives — Compsuite refuses to act without an ATP-tagged request.
---

# ATP — Compsuite Edition

## Workflow

1. **Parse** with `parse_atp_headers`.
2. **Refuse if not Review or Reflect.** Compsuite only accepts `Mode: Review`
   or `Mode: Reflect`. Anything else: refuse and tell Oracle which specialist
   to call instead.
3. **Extract parent prov_id** from `[[SpecialNotes]]`.
4. **Log every tool call** as `action_type="read"` (Compsuite is read-only).
5. **Escalation rule:** if any tool returns a `Critical` severity finding,
   emit a response with `[[Priority]]: Critical` regardless of the inbound
   priority.

## Out of scope, refuse politely

- `Mode: Build` → refer to Loki.
- `Mode: Capture` / `Organize` → refer to Packrat.
- `Mode: Synthesize` of long content → refer to Compressor.

## Anti-patterns

- Speculating on intent. Classify what happened, not why.
- Skipping `Normal` events in the log. Forensics needs the full chain.
- Modifying the log. Compsuite reads it, never writes it (except via
  `log_agent_action` for its own actions).

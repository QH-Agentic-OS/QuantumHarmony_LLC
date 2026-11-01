---
name: atp
description: Parse, validate, format, and reason about Artemis Transmission Protocol (ATP) headers. Use whenever a user message arrives, whenever the agent prepares an outbound message to a sibling agent, whenever the user mentions ATP, asks to "add the ATP header", "translate this ramble into ATP", "tag this with Mode/Context/Priority", or pastes a raw prompt expecting structured routing. Also use when reviewing past prompts and you need to extract the Mode, Context, or TargetZone fields. This is the workflow layer above the validator tools — call it before doing any other thinking about an incoming message.
---

# ATP — Artemis Transmission Protocol

## Overview

ATP is the inter-agent communication standard for the Artemis stack. Every
prompt that flows into or between agents carries a structured header block
that names the intent (`Mode`), purpose (`Context`), urgency (`Priority`),
expected output shape (`ActionType`), target area (`TargetZone`), and any
exceptional notes (`SpecialNotes`). This skill is the workflow layer — the
raw tools live in `artemis-validators-tools`.

## When to use which tool

| You want to... | Call |
|---|---|
| Extract fields from an incoming message | `parse_atp_headers(raw_input)` |
| Block a malformed message and explain why | `validate_atp_message(raw_input)` |
| Build a clean header for an outbound message | `format_atp_header(...)` |

## Core workflow — every incoming message

1. **Call `parse_atp_headers(raw_input)` first.** Look at `has_atp_headers`.
2. If headers are present, look at `is_complete`. If `is_complete` is True,
   proceed. If False, call `validate_atp_message` to enumerate the errors,
   ask the user to fix them, and stop.
3. If headers are absent (`has_atp_headers: False`), do NOT route blindly.
   Infer the likely Mode/Context/ActionType from the content and ask the user:
   > "I'll treat this as `Mode: <X>, Context: <Y>, ActionType: <Z>` —
   > confirm or correct?"
4. Once confirmed, mint a `prov_id` via the provenance skill and proceed.

## Core workflow — every outbound delegation

When Oracle hands off to a specialist (Loki, Compsuite, Packrat, Compressor):

1. Decide the Mode/Context/ActionType for the sub-task.
2. Call `format_atp_header(mode=..., context=..., action_type=..., target_zone=...)`
   with `syntax="bracket"` (Apollo's preferred grep-able form).
3. Prepend that header to the sub-prompt before sending it via the specialist's
   SSE tool.

## Mode interpretation

The Mode tag tells the agent **what kind of work** is expected, not just what
to do. Behavior shifts:

- `Build` — produce new artifacts. Verbose explanations of structure.
- `Review` — read, critique, report. **Do not edit.**
- `Organize` — tag, file, index. No new content created.
- `Capture` — preserve raw input verbatim. Light cleanup only.
- `Synthesize` — combine multiple inputs into one unified narrative.
- `Commit` — finalize, version, freeze. Touch git.
- `Reflect` — surface patterns and drift. Long-form narrative output.

## Examples

**Example 1 — fully-formed incoming ATP prompt:**

```
[[Mode]]: Build
[[Context]]: Scaffold the validator tool server
[[Priority]]: High
[[ActionType]]: Scaffold
[[TargetZone]]: /artemis-agent-stack/artemis-validators-tools/
[[SpecialNotes]]: Must work with EXO and Anthropic providers both.

Please create the tool server with parse_atp_headers and provenance logging.
```

Workflow: parse → validate → mint prov_id → delegate to Loki with the same
header (or a refined sub-header).

**Example 2 — incoming ramble, no headers:**

> "ok so I'm thinking we should maybe pull all the old hebbian notebook stuff
> and just collapse it into one summary, the v4 critique stuff and v5 too,
> idk"

Inferred: `Mode: Synthesize`, `Context: Collapse v4+v5 Hebbian notebooks into one summary`,
`ActionType: Summarize`. Ask Apollo to confirm before routing to Compressor.

**Example 3 — outbound delegation header for Loki:**

```python
format_atp_header(
    mode="Build",
    context="Implement parse_atp_headers tool with hash + bracket syntax support",
    action_type="Scaffold",
    priority="High",
    target_zone="/artemis-agent-stack/artemis-validators-tools/tools/atp_validator.py",
    syntax="bracket",
)
```

## Anti-patterns

- **Don't route a message that has `is_complete: False`.** It will fan out
  garbage. Ask first.
- **Don't strip the ATP header before delegating.** The specialist needs it
  to set its own mode.
- **Don't invent new Mode values.** Stick to the canonical set. If you think
  you need a new one (e.g., `VoiceReflect`), flag it to Apollo first.
- **Don't treat `Priority: Normal` as silent default.** If the user explicitly
  set a priority other than Normal, surface it in your acknowledgment so they
  know it was received.

## Resources

The actual parser lives in `artemis-validators-tools/tools/atp_validator.py`
(ported from `build/agents/atp/atp_parser.py` in the Artemis City repo).
Changes there propagate everywhere because every agent calls the same
validator MCP server.

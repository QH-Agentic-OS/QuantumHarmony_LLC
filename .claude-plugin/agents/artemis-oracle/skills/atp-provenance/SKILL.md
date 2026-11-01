---
name: atp-provenance
description: Mint a parent provenance ID for each incoming ATP prompt and log every subsequent agent action (tool calls, reads, writes, executes, delegations) as a child entry referencing the parent. Use whenever you receive an ATP-tagged prompt, whenever you delegate to a sibling agent, whenever you call any tool, and whenever the user asks "what did Oracle do with my last prompt?" or "show me the provenance chain". This is non-negotiable for the Artemis stack — Apollo's pitch is that provenance is the argument, and every action must be traceable.
---

# ATP Provenance Logging

## Overview

Apollo's project exists because a working system he built was replaced by
credentialed people who made it worse, and "just trust us" won over proof.
The provenance log is the structural response: every claim about what an
agent did is backed by an append-only YAML log entry, indexed by a parent
`prov_id` minted at the moment an ATP prompt arrived.

This skill governs **when** to mint and **what** to log. The implementation
lives in `artemis-validators-tools/tools/provenance.py`.

## The rule

> One parent `prov_id` per ATP prompt. One child entry per agent action.
> No tool runs without a `parent_prov_id` in hand.

## Workflow

### On every incoming ATP prompt

1. Parse headers (see the `atp` skill).
2. Once headers are validated, immediately call:
   ```python
   result = create_provenance_id(
       atp_context=parsed["context"],
       agent_id="artemis-oracle",
   )
   prov_id = result["prov_id"]
   ```
3. Store `prov_id` for the duration of the response. Pass it into every
   subsequent tool call.

### On every tool call (after the prov_id exists)

```python
log_agent_action(
    parent_prov_id=prov_id,
    agent_id="artemis-oracle",
    action_type="tool_call",
    target="format_atp_header",
    result="accepted",
    payload_summary="formatted Build/Scaffold header for Loki delegation",
)
```

`action_type` is one of: `tool_call`, `read`, `write`, `execute`,
`delegate`, `reject`.

### On every delegation to a sibling agent

```python
log_agent_action(
    parent_prov_id=prov_id,
    agent_id="artemis-oracle",
    action_type="delegate",
    target="artemis-loki",
    result="accepted",
    payload_summary="Build/Scaffold ATP header + sub-prompt sent to Loki",
)
```

The specialist receives the `prov_id` in the ATP header's `SpecialNotes`
field (or a custom `[[ParentProvId]]:` tag) and continues logging under
the same parent.

### On reject or error

Always log rejections. They're the forensic record:

```python
log_agent_action(
    parent_prov_id=prov_id,
    agent_id="artemis-oracle",
    action_type="reject",
    target="user_message",
    result="rejected",
    payload_summary="ATP header missing required Context field",
)
```

### On request to read the chain

When Apollo asks "what did you do?":

```python
chain = read_provenance_chain(parent_prov_id=prov_id)
# Return as a readable narrative, oldest first.
```

## What goes in `payload_summary`

- 280 chars max — it's a summary, not a payload dump.
- No secrets. No raw file contents. No PII.
- Lead with the verb: "delegated", "wrote", "read", "rejected because".
- The `body_sha256` field handles integrity; the summary handles readability.

## Anti-patterns

- **Don't mint multiple prov_ids per prompt.** One prompt = one parent.
- **Don't log AFTER the action.** Mint first, then log as you go. Post-hoc
  logs lose half their value because intermediate failures vanish.
- **Don't log secrets in `payload_summary`.** Hash them; the summary is
  human-readable and ends up in Git.
- **Don't skip logging "boring" reads.** Every read is part of the chain.
  Forensics needs them.

## Resources

- Log location inside the sandbox: `/work/logs/handshakes-YYYY-MM.yaml`
- Log location on the host: `~/Documents/Claude/Projects/Agentic Governance/artemis-agent-stack/logs/`
- Append-only by convention — never edit existing entries. Rotation happens
  per-month via filename.

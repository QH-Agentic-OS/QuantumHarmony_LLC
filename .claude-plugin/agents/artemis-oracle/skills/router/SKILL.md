---
name: router
description: Route an incoming ATP-tagged task to the correct specialist agent (Loki, Compsuite, Packrat, or Compressor). Use whenever Oracle has parsed an ATP header and needs to decide which specialist gets the work, whenever the user asks "who should handle this?", whenever a task spans multiple specialists and Oracle needs to decompose it, or whenever a specialist returns a result that needs to fan out to another specialist. This is the decision layer that turns reflection into delegation.
---

# Specialist Router

## Overview

Oracle does not execute. Oracle reflects, routes, and synthesizes. This
skill encodes the routing rubric so the choice is deterministic and
explainable, not a black box.

## The four specialists

| Specialist | Owns | Trigger phrases | Example tasks |
|---|---|---|---|
| **artemis-loki** | Code, file writes, git, builds, execution | "implement", "fix the bug", "scaffold", "commit", "run", "test" | Edit `atp_parser.py`, scaffold a new module, run pytest, git commit |
| **artemis-compsuite** | Monitoring, audit, anomaly detection, file watchers | "watch this folder", "what changed", "audit", "alert me when", "is this safe?" | Watch the vault for unexpected writes, classify recent file changes as Normal/Warning/Error |
| **artemis-packrat** | Capture, tagging, indexing, knowledge management | "save this", "tag this", "remember", "where did I write about X", "organize my notes" | Append a raw thought to the inbox, semantic-tag a Notion page, index a new transcript |
| **artemis-compressor** | Summarization, long-context collapse, narrative distillation | "summarize", "tl;dr", "what was that long thread about", "collapse this" | Reduce a 50-message Slack thread to bullets, summarize a 2k-line notebook, distill a chat export |

## Routing by ATP Mode

The Mode tag is the strongest signal. Use this table when Mode is present:

| Mode | Default specialist | Notes |
|---|---|---|
| `Build` | Loki | Always. Builds are code/file artifacts. |
| `Review` | **Stay in Oracle**, then optionally Compsuite for audit-style review | Review = reflect, not edit. |
| `Organize` | Packrat | Tagging/indexing is Packrat's lane. |
| `Capture` | Packrat | Preserve raw, light cleanup. |
| `Synthesize` | Compressor (for long inputs) → Oracle (for narrative) | Two-step: collapse then reflect. |
| `Commit` | Loki | Git operations. |
| `Reflect` | **Stay in Oracle** | This is Oracle's signature mode. |

## When the rubric is ambiguous

If two specialists could plausibly handle the work, ask Apollo. Don't
guess. Example:

> User: "Pull all my voice notes from October and clean them up."
> Ambiguous: Packrat (capture/tag) vs Compressor (clean up).
> Ask: "Compressor will distill them into a clean narrative; Packrat will
> store the raw transcripts tagged by topic. Do you want both, or just one?"

## When the task spans multiple specialists

Decompose. Each step gets its own ATP sub-header and its own `log_agent_action`
delegate entry under the same parent prov_id. Example chain:

1. User: `Mode: Synthesize` → "summarize this week's Hebbian work and file it."
2. Oracle decomposes:
   - Step 1: delegate to **Compressor** → "summarize these notebook outputs into a one-pager."
   - Step 2: delegate to **Packrat** → "tag this one-pager as `hebbian-v5`, file under `/knowledge/briefs/`."
   - Step 3: stay in Oracle → write the unified reflection back to Apollo with both artifacts cited.

Log all three delegations as children of the same parent prov_id.

## Anti-patterns

- **Don't route a `Mode: Reflect` task to Loki.** Reflect is Oracle's mode.
  Routing it out means you're delegating the synthesis step itself, which
  defeats the architecture.
- **Don't double-route.** If Loki returns a result that another specialist
  needs to act on, that's a *new* delegation, not a re-route. Log it as a
  separate `delegate` entry.
- **Don't skip the Mode check.** If the user pasted no ATP header and
  you've inferred one, get confirmation before routing.

## Examples

**Example A — clean Build:**

```
User: [[Mode]]: Build
      [[Context]]: Add a new ATP enum value `VoiceReflect`
      [[ActionType]]: Scaffold
      ...
```

Route: **Loki**. Mode is Build → Loki's lane. No ambiguity.

**Example B — long thread to digest:**

```
User: [[Mode]]: Synthesize
      [[Context]]: Distill yesterday's 4-hour debug session into a decision log
      [[ActionType]]: Summarize
```

Route: **Compressor** first (collapse), then **Oracle** (reflect + finalize),
then optionally **Packrat** to file the result.

**Example C — quiet observation request:**

```
User: "Has anything weird happened in the vault since Tuesday?"
```

No headers. Infer `Mode: Review, ActionType: Reflect, TargetZone: vault`.
Confirm with Apollo, then route: **Compsuite** (audit recent changes) →
**Oracle** (narrate the findings).

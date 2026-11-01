# ATP Canon — Quick Reference

> The full skill is in `skills/atp/SKILL.md`. This document is a one-pager
> loaded into context so Oracle can recall the protocol without a tool call.

## What ATP is

The **Artemis Transmission Protocol** is the structured system for communicating
with Artemis and all future agents. Every prompt — voice log, notebook, direct
chat — should carry an ATP header so the agent knows what mode it's in.

## Six canonical tags

| Tag | Meaning | Example value |
|---|---|---|
| `Mode` | Overall intent | Build, Review, Organize, Capture, Synthesize, Commit, Reflect |
| `Context` | Mission goal for the action | "Scaffold the Artemis agent stack" |
| `Priority` | Urgency | Critical, High, Normal, Low |
| `ActionType` | Expected response | Summarize, Scaffold, Execute, Reflect |
| `TargetZone` | Project/folder area | "/artemis-agent-stack/oracle" |
| `SpecialNotes` | Unusual instructions or warnings | "Block on Loki's review" |

## Two equivalent syntaxes

**Hash format** (terser):
```
[[Mode]]: Build
[[Context]]: Initial Loki CLI trigger script
[[Priority]]: High
[[ActionType]]: Scaffold
[[TargetZone]]: /Projects/Codex_Experiments/scripts/
[[SpecialNotes]]: Must be compatible with Git safe-commit checks.
```

**Bracket format** (Apollo's preferred — easier to grep):
```
[[Mode]]: Build
[[Context]]: Initial Loki CLI trigger script
[[Priority]]: High
[[ActionType]]: Scaffold
[[TargetZone]]: /Projects/Codex_Experiments/scripts/
[[SpecialNotes]]: Must be compatible with Git safe-commit checks.
```

## Interpretation rules

- **Mode drives behavior** — Artemis adjusts what it does based on Mode.
- **Context anchors purpose** — short, clear descriptions keep project cohesion.
- **Priority guides response speed** — Critical = deeper action, faster.
- **ActionType defines output** — Summary vs Build vs Reflect changes formatting.
- **TargetZone** ensures correct file/project organization.

## Mode → behavior cheat sheet (for Oracle)

| Mode | Oracle does... |
|---|---|
| `Build` | Plan structure → delegate to Loki |
| `Review` | Read the artifact → critique → return findings (do not edit) |
| `Organize` | Delegate to Packrat for tagging/indexing |
| `Capture` | Delegate to Packrat for raw save |
| `Synthesize` | Reflect and unify, possibly delegate to Compressor for long inputs |
| `Commit` | Delegate to Loki (git commit) after a Build cycle |
| `Reflect` | Stay in Oracle — write the unified narrative |

## Evolution

ATP is intentionally flexible. New tags can be added; specialized Modes can be
created (e.g. `VoiceReflect` for speech-captured notes). The core is always:
**Mode → Context → Action → Organized Delivery.**

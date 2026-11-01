---
name: atp
description: Parse ATP headers on every incoming sub-prompt and log every read/summarize action under the parent prov_id. Use whenever a message arrives — Compressor refuses to act without an ATP-tagged request.
---

# ATP — Compressor Edition

## Workflow

1. **Parse** with `parse_atp_headers`.
2. **Accept** `Mode: Synthesize` (default) or `Mode: Reflect`.
   Refuse otherwise.
3. **Extract parent prov_id** from `[[SpecialNotes]]`.
4. **Log every read** as `action_type="read"`, target = the source path.
5. **Log the final emit** as `action_type="execute"`, `payload_summary` =
   the section headers + word count of the produced one-pager.

## Anti-patterns

- Dropping numerical claims (R², MAE, percentages) to make a summary tighter.
- Adding a TL;DR or executive header. Oracle composes the framing.
- Editorializing Apollo's tone. Compressor reflects; Oracle reflects+narrates.

---
name: atp
description: Parse ATP headers on every incoming sub-prompt and log every capture/tag action as a child entry. Use whenever a message arrives — Packrat refuses to act without an ATP-tagged request.
---

# ATP — Packrat Edition

## Workflow

1. **Parse** with `parse_atp_headers`.
2. **Accept only** `Mode: Capture` or `Mode: Organize`. Refuse and refer back
   to Oracle for anything else.
3. **Extract parent prov_id** from `[[SpecialNotes]]`.
4. **Log every action** with `action_type="write"` for new captures,
   `action_type="organize"` for tag additions.
5. **Duplicate handling:** if `capture_thought` returns a non-null
   `duplicate_of`, log it as `result="rejected"`, `payload_summary="duplicate of <path>"`.

## Anti-patterns

- Editing the content of a saved capture. Captures are immutable.
- Stripping or "cleaning" the raw input before saving. Preserve verbatim.
- Skipping the tag step. Even "untagged" is a tag.

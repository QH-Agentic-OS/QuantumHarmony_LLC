#!/usr/bin/env python3
"""Claude Code hook glue: mirror every session event into the provenance service.

This is the deterministic leg of full-session ATP provenance. The
atp-provenance-logging skill documents the transport (the agent POSTs
$PROVENANCE_SERVICE_URL/mint and /log); previously that ran on voluntary
agent compliance, which produced end-of-turn batch reconstruction and roots
with zero children. These hooks execute the same documented contract at the
moment each event actually happens. They ADD a writer — no existing write
path (handshakes YAML, tool-server JSONL, MCP tools) is replaced.

Wiring (.claude/settings.json in this repo; hooks/hooks.json via
scripts/prove_hook.py in the marketplace plugin):
  SessionStart      -> session-start   mint root + bind 4 manifest layers
  UserPromptSubmit  -> user-prompt     ingest new transcript records
  PostToolUse       -> post-tool       ingest new transcript records
  Stop              -> stop            ingest new transcript records
  SubagentStop      -> subagent-stop   ingest the sub-agent's transcript

Capture mode (PROVENANCE_CAPTURE):
  transcript (default)  the hook forwards the harness's own transcript bytes
                        to POST /ingest/trajectory; Prove parses every record
                        into a step. The agent never chooses what is logged.
  summary               legacy behaviour: the hook composes one short child
                        log per event via POST /log.

State: <STATE_DIR>/<session_id>.json holds {root_prov_id, binding_id, cursors}.
SessionStart is idempotent — an existing state file is reused, never re-bound
(re-binding a layer NULLs everything beneath it and 422s later children).

Failure posture: fail-soft. Hooks always exit 0 so a provenance outage never
blocks the session; the outage is surfaced via systemMessage. Set
PROVENANCE_STRICT=1 for the skill's halt-and-alert posture: session-start
exits 2, and user-prompt exits 2 (refusing the prompt) when registration or
transcript capture fails.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from provenance_http import open_provenance_request

SERVICE = os.environ.get("PROVENANCE_SERVICE_URL", "http://localhost:8787").rstrip("/")
STRICT = os.environ.get("PROVENANCE_STRICT", "0") == "1"
CAPTURE = os.environ.get("PROVENANCE_CAPTURE", "transcript")
CHUNK_BYTES = 512 * 1024
# One record larger than CHUNK_BYTES gets a single larger read, kept well
# under the service's 1.5 MiB chunk / 2 MiB body limits after JSON escaping.
# A record larger than that is sent as its length and digest only.
LARGE_CHUNK_BYTES = 1024 * 1024
REPO = Path(__file__).resolve().parent
# Cursor state lives in PROVENANCE_STATE_DIR when set (the plugin points it at
# its persistent data dir, since its own folder is replaced on update);
# otherwise in this repo's .claude/.atp-session.
STATE_DIR = Path(
    os.environ.get("PROVENANCE_STATE_DIR") or (REPO / ".claude" / ".atp-session")
)

# Obvious credential shapes, stripped before anything leaves this process.
# The service redacts secret-named keys; this covers values pasted in prose.
_SECRET_RE = re.compile(
    r'(sk-[A-Za-z0-9_\-]{8,}|ghp_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}'
    r'|xox[baprs]-[A-Za-z0-9\-]{8,}|AKIA[0-9A-Z]{16}|Bearer\s+[A-Za-z0-9._\-]{12,})'
)


def _sanitize(text: str) -> str:
    return _SECRET_RE.sub("[REDACTED]", text or "")


# The same credential shapes, masked inside transcript bytes
# before they leave this process. Each match is replaced by the same number
# of '*' bytes, so offsets and Prove's consumed_to stay aligned with the file.
_SECRET_BYTES_RE = re.compile(_SECRET_RE.pattern.encode("ascii"))
# Prove rejects a chunk with more than INGEST_MAX_STEPS (500) records.
MAX_RECORDS = 400


def _mask(chunk: bytes) -> bytes:
    return _SECRET_BYTES_RE.sub(lambda m: b"*" * len(m.group(0)), chunk)


def _transcript_chunks(path: str, offset: int, budget: int, max_records: int = MAX_RECORDS):
    """Newline-terminated chunks from offset, capped by bytes and record count."""
    from trajectory import iter_file_chunks

    for chunk in iter_file_chunks(path, offset, budget):
        while chunk:
            cut, newlines = -1, 0
            while newlines < max_records:
                cut = chunk.find(b"\n", cut + 1)
                if cut < 0:
                    break
                newlines += 1
            piece = chunk if cut < 0 or cut == len(chunk) - 1 else chunk[: cut + 1]
            yield piece
            chunk = chunk[len(piece):]


# The service refuses /ingest/trajectory bodies over 2 MiB. Bodies are sent as
# UTF-8 (not \u escapes, which triple non-ASCII text); a chunk whose body
# still does not fit is sent in fewer records, and a single record that does
# not fit is sent as oversized_record.
MAX_REQUEST_BYTES = 2 * 1024 * 1024 - 4096


def _encode(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _post(path: str, payload: dict) -> dict | None:
    try:
        req = urllib.request.Request(
            f"{SERVICE}{path}",
            data=_encode(payload),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with open_provenance_request(req, timeout=2) as r:
            return json.loads(r.read())
    except (
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        OSError,
        ValueError,
    ):
        return None


def _post_status(path: str, payload: dict, timeout: float = 10) -> tuple[int, dict | None]:
    """Like _post, but keeps the status so 409 continuations can be followed."""
    try:
        req = urllib.request.Request(
            f"{SERVICE}{path}",
            data=_encode(payload),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with open_provenance_request(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read())
        except (ValueError, OSError):
            return error.code, None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return 0, None


def _warn(msg: str) -> None:
    print(json.dumps({"systemMessage": f"atp provenance: {msg}"}))


def _state_path(session_id: str) -> Path:
    return STATE_DIR / f"{session_id}.json"


def _load_state(session_id: str) -> dict | None:
    p = _state_path(session_id)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
    return None


def get_register_session(hook: dict) -> dict | None:
    """Bind 4 manifest layers + mint the session root. Idempotent via state file."""
    session_id = hook.get("session_id") or "unknown-session"
    existing = _load_state(session_id)
    if existing and existing.get("root_prov_id") and existing.get("binding_id"):
        return existing

    binding_id = f"claude-code-{session_id}"
    cwd = hook.get("cwd") or str(REPO)
    # Hash the instructions of the project being worked on, not of this folder.
    claude_md = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd) / "CLAUDE.md"
    instruction_hash = (
        hashlib.sha256(claude_md.read_bytes()).hexdigest()
        if claude_md.exists()
        else None
    )
    parent_ref = None
    layers = [
        ("declaration", {"identity": {"agent_id": "claude-code"}}),
        (
            "version",
            {
                "component_id": "claude-code-session",
                "build_inputs": {"instruction_hash": instruction_hash},
            },
        ),
        (
            "session",
            {
                "session_id": session_id,
                "scope": {"workspace": cwd},
                "execution_location": {"placement": "local"},
            },
        ),
        (
            "route",
            {
                "model": {"id": hook.get("model") or "claude-code"},
                "health": {"capacity_state": "not_polled", "last_verified": None},
            },
        ),
    ]
    for name, body in layers:
        payload = {
            "layer": name,
            "manifest_binding_id": binding_id,
            "body": body,
            "parent_ref": parent_ref,
        }
        if name == "declaration":
            payload["session_id"] = session_id
        resp = _post("/manifest/bind", payload)
        if not resp:
            return None
        parent_ref = resp.get("layer_hash")

    mint = _post(
        "/mint",
        {
            "agent_id": "claude-code",
            "actor": "claude-code",
            "model": hook.get("model"),
            "atp_context": f"claude-code session {session_id} in {cwd}",
            "tags": ["claude-code", "session", "hook-minted"],
        },
    )
    if not mint:
        return None
    state = {
        "root_prov_id": mint["prov_id"],
        "binding_id": binding_id,
        "session_id": session_id,
        "workspace_root": cwd,
        "trajectories": {},
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(session_id).write_text(json.dumps(state, indent=2))
    return state


def _log_child(state: dict, **fields) -> bool:
    payload = {
        "parent_prov_id": state["root_prov_id"],
        "manifest_binding_id": state["binding_id"],
        "agent_id": "claude-code",
        "actor": "claude-code",
        **fields,
    }
    return _post("/log", payload) is not None


def _save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    _state_path(state["session_id"]).write_text(json.dumps(state, indent=2))


_LAST_INGEST_ERROR: str | None = None


def payload_base(state: dict, trajectory_id: str, parent_agent_ref: str | None, model: str | None) -> dict:
    payload = {
        "parent_prov_id": state["root_prov_id"],
        "manifest_binding_id": state["binding_id"],
        "trajectory_id": trajectory_id,
        "harness": "claude_code_jsonl",
        "workspace_root": state.get("workspace_root"),
        "agent_id": "claude-code",
        "session_id": state["session_id"],
    }
    if parent_agent_ref:
        payload["parent_agent_ref"] = parent_agent_ref
    if model:
        payload["model"] = model
    return payload


def _send_oversized(state: dict, transcript_path: str, trajectory_id: str, cursor: dict, base: dict):
    """Record one transcript record too large to send as its length and digest.

    Returns True when Prove recorded it, False on failure, None while the
    record has no terminating newline yet. The digest is of the masked
    bytes, so ``trajectory.py chain`` over a masked copy still matches.
    """
    try:
        with open(transcript_path, "rb") as handle:
            handle.seek(cursor["offset"])
            parts = []
            while True:
                block = handle.read(LARGE_CHUNK_BYTES)
                if not block:
                    return None
                cut = block.find(b"\n")
                if cut >= 0:
                    parts.append(block[: cut + 1])
                    break
                parts.append(block)
    except OSError:
        return False
    record = _mask(b"".join(parts))
    payload = {
        **base,
        "offset": cursor["offset"],
        "prior_chain_sha256": cursor["chain"],
        "chunk": "",
        "oversized_record": {"bytes": len(record), "sha256": hashlib.sha256(record).hexdigest()},
    }
    status, body = _post_status("/ingest/trajectory", payload)
    if status != 200 or not body or body.get("consumed_to") != cursor["offset"] + len(record):
        global _LAST_INGEST_ERROR
        _LAST_INGEST_ERROR = (body or {}).get("error") if isinstance(body, dict) else None
        _save_state(state)
        return False
    _warn(f"a transcript record of {len(record)} bytes was recorded as its digest only")
    cursor.update(offset=body["consumed_to"], chain=body.get("chain_sha256"))
    _save_state(state)
    return True


def _main_tid(state: dict) -> str:
    """The main trajectory id (namespaced after a root change)."""
    return state.get("trajectory_id") or state["session_id"]


def _ingest_transcript(
    state: dict,
    transcript_path: str | None,
    trajectory_id: str,
    parent_agent_ref: str | None = None,
    model: str | None = None,
) -> bool:
    """Forward every unconsumed transcript byte to Prove. Returns False on failure.

    Offsets and the chain head live in the state file; on a 409 the service
    names the offset it expects and the hook resumes from there, so an outage
    loses nothing: the next hook simply sends a longer delta.
    """
    if not transcript_path or not Path(transcript_path).is_file():
        return True
    cursors = state.setdefault("trajectories", {})
    cursor = cursors.setdefault(trajectory_id, {"offset": 0, "chain": None})
    retried = False
    budget = CHUNK_BYTES
    while True:
        progressed = False
        for chunk in _transcript_chunks(transcript_path, cursor["offset"], budget):
            piece = _mask(chunk)

            def build(data: bytes) -> dict:
                return {
                    **payload_base(state, trajectory_id, parent_agent_ref, model),
                    "offset": cursor["offset"],
                    "prior_chain_sha256": cursor["chain"],
                    "chunk": data.decode("utf-8", errors="strict"),
                }

            payload = build(piece)
            while len(_encode(payload)) > MAX_REQUEST_BYTES and piece.count(b"\n") > 1:
                # Too large once encoded: send the first half of its records.
                cut = piece.rfind(b"\n", 0, len(piece) // 2)
                if cut < 0:
                    cut = piece.find(b"\n")
                piece = piece[: cut + 1]
                payload = build(piece)
            if len(_encode(payload)) > MAX_REQUEST_BYTES:
                sent = _send_oversized(state, transcript_path, trajectory_id, cursor, payload_base(
                    state, trajectory_id, parent_agent_ref, model))
                if not sent:
                    return sent is None  # None: the record is still being written
                progressed = True
                break  # restart from the cursor past the oversized record
            status, body = _post_status("/ingest/trajectory", payload)
            if status == 409 and body and "expected_offset" in body and not retried:
                cursor.update(offset=body["expected_offset"], chain=body.get("expected_prior_chain_sha256"))
                _save_state(state)
                retried = True
                progressed = True
                break  # restart iteration from the offset the service expects
            if status != 200 or not body:
                global _LAST_INGEST_ERROR
                _LAST_INGEST_ERROR = (body or {}).get("error") if isinstance(body, dict) else None
                _save_state(state)
                return False
            if body.get("consumed_to", cursor["offset"]) == cursor["offset"]:
                break  # nothing consumable yet (partial record)
            cursor.update(offset=body["consumed_to"], chain=body.get("chain_sha256"))
            _save_state(state)
            if len(piece) < len(chunk):
                progressed = True
                break  # only part of this chunk was sent: read on from the cursor
        if not progressed:
            try:
                remaining = Path(transcript_path).stat().st_size - cursor["offset"]
            except OSError:
                remaining = 0
            if remaining >= budget:
                if budget < LARGE_CHUNK_BYTES:
                    budget = LARGE_CHUNK_BYTES  # one oversized record: retry with a larger read
                    continue
                sent = _send_oversized(state, transcript_path, trajectory_id, cursor, payload_base(
                    state, trajectory_id, parent_agent_ref, model))
                if sent is None:
                    return True  # the record is still being written
                if not sent:
                    return False
                budget = CHUNK_BYTES
                continue
            return True


def _require_state(hook: dict) -> dict | None:
    """Load state; hooks can race SessionStart, so fall back to registering."""
    session_id = hook.get("session_id") or "unknown-session"
    return _load_state(session_id) or get_register_session(hook)


def cmd_session_start(hook: dict) -> int:
    state = get_register_session(hook)
    if state is None:
        _warn("service unreachable at session start; session not mirrored")
        return 2 if STRICT else 0
    return 0


def _capture(hook: dict, state: dict) -> bool:
    """Transcript-mode capture for any hook event in the main session."""
    ok = _ingest_transcript(state, hook.get("transcript_path"), _main_tid(state), model=hook.get("model"))
    if not ok and not state.get("trajectory_id") and (_LAST_INGEST_ERROR or "").startswith(
        "trajectory_id belongs to another root"
    ):
        # This session already has a trajectory under another
        # root in the same ledger (settings changed mid-session). Record this
        # root's capture under its own id instead of failing forever.
        state["trajectory_id"] = f"{state['session_id']}@{state['root_prov_id'][:12]}"
        _save_state(state)
        ok = _ingest_transcript(state, hook.get("transcript_path"), _main_tid(state), model=hook.get("model"))
    if not ok:
        _warn("transcript ingest failed; the next hook will resend from the last receipt")
    _retry_pending_subagents(state)
    return ok


def _retry_pending_subagents(state: dict) -> None:
    """Resend sub-agent transcripts whose SubagentStop ingest failed."""
    pending = state.get("pending_subagents") or {}
    for trajectory_id, path in list(pending.items()):
        if _ingest_transcript(state, path, trajectory_id, parent_agent_ref=_main_tid(state)):
            pending.pop(trajectory_id, None)
    if pending:
        state["pending_subagents"] = pending
    else:
        state.pop("pending_subagents", None)
    _save_state(state)


def _refuse(reason: str) -> int:
    """Strict mode blocks the prompt (UserPromptSubmit exit 2)."""
    print(f"atp provenance (strict): {reason}; prompt refused so no work goes unrecorded.",
          file=sys.stderr)
    return 2


def cmd_user_prompt(hook: dict) -> int:
    state = _require_state(hook)
    if state is None:
        if STRICT:
            return _refuse("could not register this session with Prove")
        _warn("service unreachable; prompt not mirrored")
        return 0
    if CAPTURE == "transcript":
        if not _capture(hook, state) and STRICT:
            return _refuse("Prove did not accept the session transcript")
        return 0
    prompt = _sanitize(hook.get("prompt") or "")
    ok = _log_child(
        state,
        phase="user_prompt",
        action_type="message",
        target="user",
        payload_summary=prompt[:280],
        input={"prompt": prompt[:2000]},
        tags=["conversation", "user"],
    )
    if not ok:
        _warn("log write failed; prompt not mirrored")
    return 0


def cmd_post_tool(hook: dict) -> int:
    state = _require_state(hook)
    if state is None:
        return 0  # stay quiet per-tool; session-start already warned
    if CAPTURE == "transcript":
        _capture(hook, state)
        return 0
    tool_name = hook.get("tool_name") or "unknown-tool"
    tool_input = hook.get("tool_input") or {}
    inp = (
        {k: _sanitize(str(v))[:200] for k, v in list(tool_input.items())[:12]}
        if isinstance(tool_input, dict)
        else {"args": _sanitize(str(tool_input))[:200]}
    )
    resp = hook.get("tool_response")
    status = "ok"
    if isinstance(resp, dict) and (resp.get("success") is False or "error" in resp):
        status = "error"
    _log_child(
        state,
        phase="tool_call",
        action_type="tool_call",
        target=tool_name,
        status=status,
        payload_summary=f"{tool_name} {next(iter(inp.values()), '')}"[:280],
        input=inp,
        tags=["conversation", "tool"],
    )
    return 0


def cmd_stop(hook: dict) -> int:
    # A continued Stop still captures (cursor ingest is
    # idempotent and never asks Claude to continue); only the legacy summary
    # path is skipped.
    if hook.get("stop_hook_active") and CAPTURE != "transcript":
        return 0
    state = _require_state(hook)
    if state is None:
        return 0
    if CAPTURE == "transcript":
        _capture(hook, state)
        return 0
    text = ""
    tp = hook.get("transcript_path")
    if tp and Path(tp).exists():
        try:
            with open(tp, encoding="utf-8") as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = rec.get("message") or {}
                    if rec.get("type") == "assistant" or msg.get("role") == "assistant":
                        content = msg.get("content")
                        if isinstance(content, list):
                            parts = [
                                c.get("text", "")
                                for c in content
                                if isinstance(c, dict) and c.get("type") == "text"
                            ]
                            if parts:
                                text = " ".join(parts)
                        elif isinstance(content, str) and content:
                            text = content
        except OSError as exc:
            # Fail-soft: the stop is still logged, just without the reply text.
            _warn(f"could not read the transcript at stop ({exc}); logging without the reply text")
    ok = _log_child(
        state,
        phase="atp_response",
        action_type="respond",
        target="user",
        payload_summary=_sanitize(text)[:280] or "(turn ended)",
        tags=["conversation", "atp", "response"],
    )
    if not ok:
        _warn("log write failed; response not mirrored")
    return 0


def cmd_subagent_stop(hook: dict) -> int:
    """Sub-agent traces land under the same root, linked to the parent session.

    Newer Claude Code versions give the sub-agent its own transcript
    (``agent_transcript_path``); older ones interleave sidechain records in the
    main transcript, which the main-session capture already picks up.
    """
    state = _require_state(hook)
    if state is None or CAPTURE != "transcript":
        return 0
    path = hook.get("agent_transcript_path")
    agent = re.sub(r"[^A-Za-z0-9._~@-]", "-", str(hook.get("agent_id") or "subagent"))[:60]
    if path:
        trajectory_id = f"{_main_tid(state)}:{agent}"
        ok = _ingest_transcript(
            state,
            path,
            trajectory_id,
            parent_agent_ref=_main_tid(state),
        )
        if not ok:
            state.setdefault("pending_subagents", {})[trajectory_id] = path
            _save_state(state)
            _warn("sub-agent transcript ingest failed; it will be resent on the next hook")
    _capture(hook, state)
    return 0


COMMANDS = {
    "session-start": cmd_session_start,
    "user-prompt": cmd_user_prompt,
    "post-tool": cmd_post_tool,
    "stop": cmd_stop,
    "subagent-stop": cmd_subagent_stop,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"usage: atp_hooks.py {{{'|'.join(COMMANDS)}}}", file=sys.stderr)
        return 0  # never block the session on bad wiring
    try:
        hook = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        hook = {}
    try:
        return COMMANDS[sys.argv[1]](hook)
    except Exception as exc:  # noqa: BLE001 — a hook crash must not block the session
        _warn(f"hook error ({sys.argv[1]}): {exc}")
        return 2 if STRICT else 0


if __name__ == "__main__":
    raise SystemExit(main())

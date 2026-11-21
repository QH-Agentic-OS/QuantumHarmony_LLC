#!/usr/bin/env python3
"""Claude Code hook glue: mirror every session event into the provenance service.

This is the deterministic leg of full-session ATP provenance. The
atp-provenance-logging skill documents the transport (the agent POSTs
$PROVENANCE_SERVICE_URL/mint and /log); previously that ran on voluntary
agent compliance, which produced end-of-turn batch reconstruction and roots
with zero children. These hooks execute the same documented contract at the
moment each event actually happens. They ADD a writer — no existing write
path (handshakes YAML, tool-server JSONL, MCP tools) is replaced.

Wiring (plugin build: hooks/hooks.json via scripts/prove_hook.py):
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

State: .claude/.atp-session/<session_id>.json holds {root_prov_id, binding_id}.
SessionStart is idempotent — an existing state file is reused, never re-bound
(re-binding a layer NULLs everything beneath it and 422s later children).

Failure posture: fail-soft. Hooks always exit 0 so a provenance outage never
blocks the session; the outage is surfaced via systemMessage. Set
PROVENANCE_STRICT=1 to make session-start exit 2 (blocking) instead —
the skill's halt-and-alert posture.
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
REPO = Path(__file__).resolve().parent
# Plugin build: the plugin folder is replaced on every update, so cursor state
# lives in PROVENANCE_STATE_DIR (set by scripts/prove_hook.py to the plugin's
# persistent data dir). Falls back to the Prove repo layout.
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


def _post(path: str, payload: dict) -> dict | None:
    try:
        req = urllib.request.Request(
            f"{SERVICE}{path}",
            data=json.dumps(payload).encode("utf-8"),
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
            data=json.dumps(payload).encode("utf-8"),
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
    from trajectory import iter_file_chunks

    cursors = state.setdefault("trajectories", {})
    cursor = cursors.setdefault(trajectory_id, {"offset": 0, "chain": None})
    retried = False
    while True:
        progressed = False
        for chunk in iter_file_chunks(transcript_path, cursor["offset"], CHUNK_BYTES):
            payload = {
                "parent_prov_id": state["root_prov_id"],
                "manifest_binding_id": state["binding_id"],
                "trajectory_id": trajectory_id,
                "harness": "claude_code_jsonl",
                "offset": cursor["offset"],
                "prior_chain_sha256": cursor["chain"],
                "chunk": chunk.decode("utf-8", errors="strict"),
                "workspace_root": state.get("workspace_root"),
                "agent_id": "claude-code",
                "session_id": state["session_id"],
            }
            if parent_agent_ref:
                payload["parent_agent_ref"] = parent_agent_ref
            if model:
                payload["model"] = model
            status, body = _post_status("/ingest/trajectory", payload)
            if status == 409 and body and "expected_offset" in body and not retried:
                cursor.update(offset=body["expected_offset"], chain=body.get("expected_prior_chain_sha256"))
                _save_state(state)
                retried = True
                progressed = True
                break  # restart iteration from the offset the service expects
            if status != 200 or not body:
                _save_state(state)
                return False
            if body.get("consumed_to", cursor["offset"]) == cursor["offset"]:
                break  # nothing consumable yet (partial record)
            cursor.update(offset=body["consumed_to"], chain=body.get("chain_sha256"))
            _save_state(state)
        if not progressed:
            try:
                remaining = Path(transcript_path).stat().st_size - cursor["offset"]
            except OSError:
                remaining = 0
            if remaining >= CHUNK_BYTES:
                _warn("a transcript record exceeds the ingest chunk budget; capture is paused at that record")
                return False
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


def _capture(hook: dict, state: dict) -> None:
    """Transcript-mode capture for any hook event in the main session."""
    session_id = state["session_id"]
    if not _ingest_transcript(state, hook.get("transcript_path"), session_id, model=hook.get("model")):
        _warn("transcript ingest failed; the next hook will resend from the last receipt")


def cmd_user_prompt(hook: dict) -> int:
    state = _require_state(hook)
    if state is None:
        _warn("service unreachable; prompt not mirrored")
        return 0
    if CAPTURE == "transcript":
        _capture(hook, state)
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
    if hook.get("stop_hook_active"):
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
        except OSError:
            pass
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
        ok = _ingest_transcript(
            state,
            path,
            f"{state['session_id']}:{agent}",
            parent_agent_ref=state["session_id"],
        )
        if not ok:
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

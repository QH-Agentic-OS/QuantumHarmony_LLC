#!/usr/bin/env python3
"""Explicit ATP provenance: mark a prompt, log steps, mark the response.

The plugin's hooks capture every step of a Claude Code session under one
session root. Inside such a session, `begin` logs an `atp_prompt` marker under
that root and prints the root's prov_id, so the prompt, every captured step
and the `atp_response` marker share one chain (one root per session). With no
captured session for this workspace (capture off, another harness, or
`--new-root`), `begin` binds and mints a root of its own instead:

    ID=$(python3 prove_log.py begin --agent claude-code --context "ATP: refactor auth")
    python3 prove_log.py log "$ID" --phase read_file --target src/auth.py --summary "read ok"
    python3 prove_log.py log "$ID" --phase execute_command --target "pytest" --status error --error "2 failed"
    python3 prove_log.py end "$ID" --summary "refactor done, tests green"
    python3 prove_log.py chain "$ID" > run.json     # import into the dashboard

Service: $PROVENANCE_SERVICE_URL, else the endpoint the plugin's hooks wrote
to ~/.prove/plugin-endpoint.json, else http://127.0.0.1:8787. A hosted Prove
also needs $PROV_API_TOKEN (sent only over https or to loopback); the plugin
never writes the token to disk.
Entries written here are agent-authored, so Prove marks them self-reported.
Exit status is non-zero on any failed write: halt and alert, per the skill.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
from provenance_http import open_provenance_request  # noqa: E402

def _endpoint() -> tuple[str, str]:
    """$PROVENANCE_SERVICE_URL, else the endpoint the plugin's hooks published."""
    if os.environ.get("PROVENANCE_SERVICE_URL"):
        return os.environ["PROVENANCE_SERVICE_URL"].rstrip("/"), os.environ.get("PROVENANCE_MODE", "")
    try:
        cfg = json.loads((Path.home() / ".prove" / "plugin-endpoint.json").read_text())
        return str(cfg["service_url"]).rstrip("/"), str(cfg.get("mode", ""))
    except (OSError, ValueError, KeyError, TypeError):
        return "http://127.0.0.1:8787", ""


SERVICE, MODE = _endpoint()
STATE = Path(os.environ.get("PROVENANCE_ATP_STATE_DIR") or Path.home() / ".prove" / "atp")
ACTION_TAGS = {"read_file": "read", "write_file": "write", "execute_command": "execute", "tool_call": "tool"}


class ProveError(RuntimeError):
    pass


def _loopback(url: str) -> bool:
    import ipaddress
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    try:
        return host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def call(method: str, path: str, payload: dict | None = None):
    if MODE == "offline" and not _loopback(SERVICE):
        raise ProveError(f"offline mode only talks to this machine; {SERVICE} is not loopback")
    if MODE == "hosted" and not (os.environ.get("PROV_API_TOKEN") or os.environ.get("PROV_API_TOKEN_FILE")):
        raise ProveError("hosted mode needs PROV_API_TOKEN (or PROV_API_TOKEN_FILE) in this shell")
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{SERVICE}{path}", data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with open_provenance_request(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise ProveError(f"{method} {path} -> {e.code} {detail}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise ProveError(f"provenance service unreachable at {SERVICE}: {e}") from None


def state_path(prov_id: str) -> Path:
    if not all(c in "0123456789abcdef-" for c in prov_id.lower()):
        raise ProveError("not a prov_id")
    return STATE / f"{prov_id}.json"


def active_session() -> dict | None:
    """The hooks' capture root for this workspace (or a parent folder), if any."""
    import hashlib

    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        key = hashlib.sha256(str(folder).encode()).hexdigest()[:20]
        try:
            info = json.loads((Path.home() / ".prove" / "active-sessions" / f"{key}.json").read_text())
        except (OSError, ValueError):
            continue
        if str(info.get("service_url", "")).rstrip("/") == SERVICE and info.get("root_prov_id"):
            return info
    return None


def begin(a) -> str:
    session = None if a.new_root else active_session()
    if session:
        root = session["root_prov_id"]
        STATE.mkdir(parents=True, exist_ok=True)
        state_path(root).write_text(json.dumps(
            {"binding_id": session["binding_id"], "agent": a.agent, "model": a.model}))
        a.target, a.summary = "atp_prompt", a.context
        log(root, a, phase="atp_prompt", tags=["atp", "prompt"])
        return root
    session_id = a.session or str(uuid.uuid4())
    binding = f"atp-{session_id}"
    parent_ref = None
    layers = [
        ("declaration", {"identity": {"agent_id": a.agent}}),
        ("version", {"component_id": "atp-provenance-logging", "build_inputs": {"instruction_hash": None}}),
        ("session", {"session_id": session_id, "scope": {"workspace": os.getcwd()},
                     "execution_location": {"placement": "local"}}),
        ("route", {"model": {"id": a.model or "unknown"}}),
    ]
    for name, body in layers:
        payload = {"layer": name, "manifest_binding_id": binding, "body": body, "parent_ref": parent_ref}
        if name == "declaration":
            payload["session_id"] = session_id
        parent_ref = call("POST", "/manifest/bind", payload)["layer_hash"]
    root = call("POST", "/mint", {
        "agent_id": a.agent, "actor": a.agent, "model": a.model, "manifest_binding_id": binding,
        "atp_context": a.context, "input": {"prompt": a.context},
        "output": {"summary": a.plan or ""}, "tags": ["atp", "prompt"],
    })
    STATE.mkdir(parents=True, exist_ok=True)
    state_path(root["prov_id"]).write_text(json.dumps(
        {"binding_id": binding, "agent": a.agent, "model": a.model}))
    return root["prov_id"]


def log(prov_id: str, a, phase: str | None = None, tags=None) -> str:
    st = json.loads(state_path(prov_id).read_text())
    phase = phase or a.phase
    payload = {
        "parent_prov_id": prov_id, "manifest_binding_id": st["binding_id"],
        "agent_id": st["agent"], "actor": a.actor or st["agent"], "model": st.get("model"),
        "phase": phase, "action_type": phase, "target": a.target or phase,
        "payload_summary": a.summary or "", "input": {"target": a.target} if a.target else {},
        "output": {"summary": a.summary or ""}, "status": a.status, "error": a.error,
        "tags": tags or [ACTION_TAGS.get(phase, phase)] + (["error"] if a.status == "error" else []),
    }
    return call("POST", "/log", payload).get("prov_id", "")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ATP provenance helper")
    ap.add_argument("command", choices=["begin", "log", "end", "chain", "verify"])
    ap.add_argument("prov_id", nargs="?")
    ap.add_argument("--agent", default="claude-code")
    ap.add_argument("--actor")
    ap.add_argument("--model")
    ap.add_argument("--session")
    ap.add_argument("--new-root", action="store_true",
                    help="mint a separate root even inside a captured session")
    ap.add_argument("--context", default="")
    ap.add_argument("--plan")
    ap.add_argument("--phase", default="tool_call")
    ap.add_argument("--target")
    ap.add_argument("--summary")
    ap.add_argument("--status", default="ok", choices=["ok", "error", "retry"])
    ap.add_argument("--error")
    a = ap.parse_args(argv)
    try:
        if a.command == "begin":
            print(begin(a))
            return 0
        if not a.prov_id:
            ap.error(f"{a.command} needs the root prov_id from begin")
        if a.command == "log":
            print(log(a.prov_id, a))
        elif a.command == "end":
            print(log(a.prov_id, a, phase="atp_response", tags=["atp", "response"]))
        elif a.command in ("chain", "verify"):
            print(json.dumps(call("GET", f"/{a.command}?parent_prov_id={quote(a.prov_id)}"), indent=2))
        return 0
    except (ProveError, OSError, KeyError, ValueError) as exc:
        print(f"PROVENANCE FAILURE: {exc}. Halt and alert the user.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

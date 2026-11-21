#!/usr/bin/env python3
"""Plugin entry point for the capture hooks (see hooks/hooks.json).

Reads the plugin's settings, picks the Prove service for the chosen mode,
starts the bundled local service when needed, then hands the hook event to
server/atp_hooks.py, which forwards the harness transcript to
POST /ingest/trajectory.

Settings arrive from Claude Code as CLAUDE_PLUGIN_OPTION_<KEY>:
  MODE         hosted | standalone (default) | offline
  SERVICE_URL  Prove base URL. Hosted: required, https. Standalone: optional,
               defaults to the bundled local service. Offline: ignored unless
               it is a loopback URL.
  API_TOKEN    bearer token for a hosted Prove (sent only in hosted mode)
  CAPTURE      true (default) / false — turn transcript capture off
  STRICT       false (default) / true — refuse prompts while Prove is down
               (UserPromptSubmit exit 2; SessionStart cannot block)
  AUTOSTART    true (default) / false — start the bundled local service
  LEDGER_PATH  local ledger file (default ~/.prove/provenance.db)

Fail-soft like the hooks it wraps: always exits 0 unless STRICT is on.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path(os.environ.get("PROV_DB") or Path.home() / ".prove" / "provenance.db")  # as prove_local
LOCAL_URL = "http://127.0.0.1:{port}"


def opt(key: str, default: str = "") -> str:
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{key}", "").strip() or default


def flag(key: str, default: bool) -> bool:
    raw = opt(key)
    if not raw:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def loopback(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def destination_key(url: str) -> str:
    """One key per ledger, whatever the spelling of its address.

    Loopback aliases (localhost, 127.0.0.1, ::1) and the default ledger path
    written out or left empty all name the same local ledger.
    """
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if loopback(url):
        ledger = opt("LEDGER_PATH") or str(DEFAULT_DB)
        return f"local:{port}|{Path(ledger).expanduser().resolve()}"
    return f"{parts.scheme}://{(parts.hostname or '').lower()}:{port}{parts.path.rstrip('/')}"


def refuse(reason: str) -> int:
    """Strict mode: UserPromptSubmit exit 2 blocks the prompt."""
    print(f"atp provenance (strict): {reason}; prompt refused so no work goes unrecorded.",
          file=sys.stderr)
    return 2


def warn(msg: str) -> None:
    print(json.dumps({"systemMessage": f"atp provenance: {msg}"}))


def resolve() -> tuple[str | None, str | None, str]:
    """Return (service_url, token, mode); url None means do not capture."""
    mode = opt("MODE", "standalone").lower()
    url = opt("SERVICE_URL").rstrip("/")
    token = opt("API_TOKEN")
    port = os.environ.get("PROV_PORT", "8787")
    if mode == "hosted":
        if not url:
            return None, None, mode
        if urlsplit(url).scheme != "https" and not loopback(url):
            raise ValueError("hosted mode needs an https service URL")
        return url, token or None, mode
    if mode == "offline":
        # Nothing may leave this machine: loopback only, never a token.
        if url and not loopback(url):
            raise ValueError(f"offline mode only talks to this machine; {url} is not loopback")
        return url or LOCAL_URL.format(port=port), None, mode
    if mode != "standalone":
        raise ValueError(f"unknown mode {mode!r} (hosted, standalone or offline)")
    return url or LOCAL_URL.format(port=port), None, mode


def readiness(url: str, token: str | None, mode: str) -> str | None:
    """None when Prove will accept writes, else why not.

    /health is public on a hosted Prove, so a hosted check also calls an
    authenticated route: a wrong, missing or rotated token must fail here.
    """
    import urllib.error
    import urllib.request

    sys.path.insert(0, str(ROOT / "server"))
    from provenance_http import open_provenance_request

    if token:
        os.environ["PROV_API_TOKEN"] = token
    else:
        os.environ.pop("PROV_API_TOKEN", None)
    os.environ.pop("PROV_API_TOKEN_FILE", None)
    try:
        with open_provenance_request(urllib.request.Request(f"{url}/health"), timeout=3) as r:
            if json.loads(r.read()).get("service") != "atp-provenance":
                return f"{url} is not a Prove service"
    except Exception:  # noqa: BLE001 — any failure means "not reachable"
        return f"Prove at {url} is unreachable"
    if mode != "hosted":
        return None
    try:
        with open_provenance_request(urllib.request.Request(f"{url}/runtime/metadata"), timeout=3):
            return None
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return f"Prove at {url} rejected the api_token"
        return f"Prove at {url} answered {exc.code}"
    except Exception:  # noqa: BLE001
        return f"Prove at {url} is unreachable"


class session_lock:
    """Exclusive interprocess lock on <state_dir>/<session>.lock (POSIX flock, Windows msvcrt)."""

    def __init__(self, state_dir: Path, session_id: str):
        safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in session_id)[:120]
        self.path = state_dir / f"{safe}.lock"
        self.handle = None

    def __enter__(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.handle = open(self.path, "a+b")
            if os.name == "posix":
                import fcntl

                fcntl.flock(self.handle, fcntl.LOCK_EX)
            else:  # pragma: no cover - Windows
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_LOCK, 1)
        except OSError as exc:
            warn(f"could not lock session state ({exc}); continuing without the lock")
        return self

    def __exit__(self, *exc):
        if self.handle:
            self.handle.close()  # releases the lock
        return False


ACTIVE_DIR = Path.home() / ".prove" / "active-sessions"


def active_key(cwd: str) -> str:
    return hashlib.sha256(str(Path(cwd).resolve()).encode()).hexdigest()[:20]


def forget_session(hook: dict, only_own: bool) -> None:
    """Drop this workspace's receipt so prove_log.py stops using it."""
    cwd = hook.get("cwd")
    if not cwd:
        return
    path = ACTIVE_DIR / f"{active_key(cwd)}.json"
    try:
        if only_own and json.loads(path.read_text()).get("session_id") != hook.get("session_id"):
            return  # another live session in this workspace owns it
        path.unlink()
    except (OSError, ValueError):
        pass  # nothing published, or already gone


def publish_session(hook: dict, state_dir: Path, url: str, mode: str) -> None:
    """Point prove_log.py at this session's capture root, keyed by workspace.

    ATP prompt/response markers then land under the same root as every
    captured step, so one export holds the whole session.
    """
    sid, cwd = hook.get("session_id"), hook.get("cwd")
    if not sid or not cwd:
        return
    try:
        state = json.loads((state_dir / f"{sid}.json").read_text())
        ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
        (ACTIVE_DIR / f"{active_key(cwd)}.json").write_text(json.dumps({
            "root_prov_id": state["root_prov_id"], "binding_id": state["binding_id"],
            "session_id": sid, "workspace": str(Path(cwd).resolve()), "service_url": url,
            "mode": mode,
        }) + "\n")
    except (OSError, ValueError, KeyError, TypeError):
        pass  # best effort: prove_log.py falls back to minting its own root


def autostart(url: str) -> None:
    parts = urlsplit(url)
    cmd = [sys.executable, "-I", str(ROOT / "scripts" / "prove_local.py"), "start",
           "--port", str(parts.port or 8787)]
    ledger = opt("LEDGER_PATH")
    if ledger:
        cmd += ["--db", ledger]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   stdin=subprocess.DEVNULL, timeout=12, check=False)


def main() -> int:
    event = sys.argv[1] if len(sys.argv) > 1 else ""
    strict = flag("STRICT", False)
    raw = sys.stdin.read()
    try:
        hook = json.loads(raw) if raw.strip() else {}
    except ValueError:
        hook = {}
    sys.stdin = io.StringIO(raw)  # atp_hooks reads the same payload
    if event == "session-end":
        forget_session(hook, only_own=True)
        return 0
    if not flag("CAPTURE", True):
        if event == "session-start":
            forget_session(hook, only_own=False)  # a stale receipt must not adopt this session
        return 0
    try:
        url, token, mode = resolve()
    except ValueError as exc:
        if event == "session-start":
            warn(f"{exc}; capture is off for this session")
        if strict and event == "user-prompt":
            return refuse(str(exc))
        return 2 if strict and event == "session-start" else 0
    if url is None:
        if event == "session-start":
            warn("hosted mode is selected but no service URL is set; capture is off")
        if strict and event == "user-prompt":
            return refuse("hosted mode is selected but no service URL is set")
        return 0

    if loopback(url):
        sys.path.insert(0, str(ROOT / "scripts"))
        import prove_local  # noqa: E402

        port = urlsplit(url).port or 8787
        if event == "session-start" and flag("AUTOSTART", True) and not prove_local.health(port):
            try:
                autostart(url)
            except (OSError, subprocess.SubprocessError) as exc:
                warn(f"could not start the local Prove service: {exc}")
        # Never record into a ledger other than the one selected in settings.
        wanted = str(Path(opt("LEDGER_PATH") or prove_local.DEFAULT_DB).expanduser().resolve())
        running = prove_local.running_ledger(port)
        if prove_local.health(port) and running != wanted and (running or opt("LEDGER_PATH")):
            if event == "session-start":
                where = running or "a ledger this plugin did not start"
                warn(f"the Prove on port {port} is using {where}, not {wanted}; capture is off. "
                     f"Stop it (prove_local.py stop --port {port}) and start a new session.")
            if strict and event == "user-prompt":
                return refuse(f"the Prove on port {port} is not using the selected ledger")
            return 0

    if strict and event == "user-prompt":
        problem = readiness(url, token, mode)
        if problem:
            return refuse(problem)

    os.environ["PROVENANCE_SERVICE_URL"] = url
    os.environ["PROVENANCE_STRICT"] = "1" if strict else "0"
    os.environ.pop("PROV_API_TOKEN_FILE", None)
    if token:
        os.environ["PROV_API_TOKEN"] = token
    else:
        os.environ.pop("PROV_API_TOKEN", None)
    data = os.environ.get("CLAUDE_PLUGIN_DATA") or str(Path.home() / ".prove")
    # Cursor state belongs to one ledger: namespace it by destination so a
    # changed service_url or ledger_path registers a fresh root.
    dest = hashlib.sha256(destination_key(url).encode()).hexdigest()[:16]
    os.environ["PROVENANCE_STATE_DIR"] = str(Path(data) / "atp-session" / dest)

    sys.path.insert(0, str(ROOT / "server"))
    import atp_hooks  # noqa: E402  (reads the environment set above)

    # One hook at a time per session: registration, cursor updates and the
    # receipt must see each other's state, or two hooks can mint two roots.
    with session_lock(Path(os.environ["PROVENANCE_STATE_DIR"]), hook.get("session_id") or "unknown-session"):
        rc = atp_hooks.main()
    if event in ("session-start", "user-prompt"):
        publish_session(hook, Path(os.environ["PROVENANCE_STATE_DIR"]), url, mode)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

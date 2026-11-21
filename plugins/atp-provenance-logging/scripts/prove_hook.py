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
  STRICT       false (default) / true — block the session if Prove is down
  AUTOSTART    true (default) / false — start the bundled local service
  LEDGER_PATH  local ledger file (default ~/.prove/provenance.db)

Fail-soft like the hooks it wraps: always exits 0 unless STRICT is on.
"""

from __future__ import annotations

import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
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
    if not flag("CAPTURE", True):
        return 0
    try:
        url, token, mode = resolve()
    except ValueError as exc:
        if event == "session-start":
            warn(f"{exc}; capture is off for this session")
        return 2 if strict and event == "session-start" else 0
    if url is None:
        if event == "session-start":
            warn("hosted mode is selected but no service URL is set; capture is off")
        return 0

    if event == "session-start" and loopback(url) and flag("AUTOSTART", True):
        sys.path.insert(0, str(ROOT / "scripts"))
        import prove_local  # noqa: E402

        port = urlsplit(url).port or 8787
        if not prove_local.health(port):
            try:
                autostart(url)
            except (OSError, subprocess.SubprocessError) as exc:
                warn(f"could not start the local Prove service: {exc}")

    os.environ["PROVENANCE_SERVICE_URL"] = url
    os.environ["PROVENANCE_STRICT"] = "1" if strict else "0"
    os.environ.pop("PROV_API_TOKEN_FILE", None)
    if token:
        os.environ["PROV_API_TOKEN"] = token
    else:
        os.environ.pop("PROV_API_TOKEN", None)
    data = os.environ.get("CLAUDE_PLUGIN_DATA") or str(Path.home() / ".prove")
    os.environ["PROVENANCE_STATE_DIR"] = str(Path(data) / "atp-session")

    sys.path.insert(0, str(ROOT / "server"))
    import atp_hooks  # noqa: E402  (reads the environment set above)

    return atp_hooks.main()


if __name__ == "__main__":
    raise SystemExit(main())

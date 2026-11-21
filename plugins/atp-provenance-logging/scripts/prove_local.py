#!/usr/bin/env python3
"""Run Prove on this machine: provenance service + Mission Control on one port.

Standalone and offline modes of the atp-provenance-logging plugin use this.
It needs only Python 3.11+ (stdlib) and never contacts the network: the
dashboard's React is vendored in ui/vendor/, and the service binds to
127.0.0.1 unless --allow-remote is given.

    python3 prove_local.py init                 create the ledger if missing
    python3 prove_local.py serve                foreground, Ctrl-C to stop
    python3 prove_local.py start | stop | status   background instance
    python3 prove_local.py upgrade --backup PATH   upgrade an older ledger
    python3 prove_local.py export PARENT_PROV_ID   print GET /chain JSON

Options (any command): --db PATH (default $PROV_DB or ~/.prove/provenance.db),
--port N (default $PROV_PORT or 8787), --host H (default 127.0.0.1).

Dashboard: http://127.0.0.1:8787/  (same origin as the API, so the default
service URL in the dashboard works without editing).
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SERVER_DIR = PLUGIN_ROOT / "server"
UI_DIR = PLUGIN_ROOT / "ui"
sys.path.insert(0, str(SERVER_DIR))

DEFAULT_DB = Path(os.environ.get("PROV_DB") or Path.home() / ".prove" / "provenance.db")
DEFAULT_PORT = int(os.environ.get("PROV_PORT", "8787"))
# One place for run files, whether started by the hooks or by hand.
RUN_DIR = Path.home() / ".prove" / "run"
# Loopback probes never go through an environment proxy.
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))

# Only these files are ever served; nothing else under the plugin is reachable.
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/atp-mission-control.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/vendor/react.production.min.js": (
        "vendor/react.production.min.js",
        "text/javascript; charset=utf-8",
    ),
    "/vendor/react-dom.production.min.js": (
        "vendor/react-dom.production.min.js",
        "text/javascript; charset=utf-8",
    ),
}
# Same-origin dashboard: no inline script, no network, no eval.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self' http://127.0.0.1:* http://localhost:*; "
    "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def health(port: int, host: str = "127.0.0.1", timeout: float = 1.0) -> dict | None:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        with _LOCAL.open(
            f"http://{probe_host}:{port}/health", timeout=timeout
        ) as r:
            body = json.loads(r.read())
            return body if body.get("service") == "atp-provenance" else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def init_ledger(db: Path) -> bool:
    """Create an empty current-schema ledger. Returns True if one was created."""
    from provenance_core import ProvenanceStore

    if db.exists():
        return False
    db.parent.mkdir(parents=True, exist_ok=True)
    ProvenanceStore(str(db)).initialize()
    return True


def make_handler():
    import provenance_service as service

    class Handler(service.Handler):
        server_version = "ProveLocal/2.0"

        def _send_asset(self, path):
            filename, content_type = ASSETS[path]
            body = (UI_DIR / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if content_type.startswith("text/html"):
                self.send_header("Content-Security-Policy", CSP)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            from urllib.parse import urlsplit

            path = urlsplit(self.path).path
            if path in ASSETS:
                return self._send_asset(path)
            return super().do_GET()

    return Handler, service


def serve(db: Path, host: str, port: int) -> None:
    from http.server import ThreadingHTTPServer

    if not db.is_file():
        if init_ledger(db):
            print(f"  created a new local ledger: {db}", file=sys.stderr)
    Handler, service = make_handler()
    service.DB_PATH = str(db)
    service.store().require_ready()
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError as err:
        if health(port, host):
            print(f"Prove is already running on port {port}; reusing it.", file=sys.stderr)
            return
        print(f"port {port} is in use by something else ({err}); try --port {port + 1}", file=sys.stderr)
        sys.exit(1)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print(f"Prove  ->  http://{shown}:{port}/   (ledger: {db})", flush=True)
    info = runfile(port)
    try:
        RUN_DIR.mkdir(parents=True, exist_ok=True)
        info.write_text(json.dumps({"pid": os.getpid(), "db": str(db)}))
    except OSError as err:
        # Best effort: without it the hooks just can't confirm which ledger this is.
        print(f"  note: could not write {info}: {err}", file=sys.stderr)
    def _term(*_):
        raise KeyboardInterrupt  # stop cleanly on `prove_local.py stop` too

    signal.signal(signal.SIGTERM, _term)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("  stopped.", file=sys.stderr)  # Ctrl-C is the normal way to stop
    finally:
        httpd.server_close()
        info.unlink(missing_ok=True)


def runfile(port: int) -> Path:
    return RUN_DIR / f"prove-{port}.json"


def running_ledger(port: int) -> str | None:
    """Ledger of the plugin-started Prove on this port, or None if unknown."""
    try:
        info = json.loads(runfile(port).read_text())
        os.kill(int(info["pid"]), 0)
        return str(Path(info["db"]).resolve())
    except (OSError, ValueError, KeyError, TypeError):
        return None


def pidfile(port: int) -> Path:
    return RUN_DIR / f"prove-{port}.pid"


def start(db: Path, host: str, port: int, wait: float = 5.0) -> int:
    if health(port, host):
        print(f"Prove already running: http://127.0.0.1:{port}/")
        return 0
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-I", str(Path(__file__).resolve()), "serve",
           "--db", str(db), "--host", host, "--port", str(port)]
    if not is_loopback(host):
        cmd.append("--allow-remote")
    # The child keeps its own handle to the log; the parent's copy is closed here.
    with open(RUN_DIR / f"prove-{port}.log", "ab") as log:
        kwargs = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL, "cwd": str(SERVER_DIR)}
        if os.name == "posix":
            kwargs["start_new_session"] = True
        else:  # pragma: no cover - Windows
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED | NEW_GROUP
        proc = subprocess.Popen(cmd, **kwargs)
    pidfile(port).write_text(str(proc.pid))
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if health(port, host, timeout=0.5):
            print(f"Prove started: http://127.0.0.1:{port}/  (ledger: {db})")
            return 0
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    print(f"Prove did not become healthy; see {RUN_DIR / f'prove-{port}.log'}", file=sys.stderr)
    return 1


def stop(port: int) -> int:
    pf = pidfile(port)
    if not pf.exists():
        print("no background Prove started by this plugin on that port")
        return 0
    try:
        os.kill(int(pf.read_text().strip()), signal.SIGTERM)
        print("stopped")
    except (ProcessLookupError, ValueError):
        print("not running (stale pid file removed)")
    pf.unlink(missing_ok=True)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("command", choices=["init", "serve", "start", "stop", "status", "upgrade", "export"])
    ap.add_argument("arg", nargs="?", help="parent_prov_id for export")
    ap.add_argument("--db", type=Path, default=DEFAULT_DB)
    ap.add_argument("--host", default=os.environ.get("PROV_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--backup", help="new absolute backup path (upgrade)")
    ap.add_argument("--allow-remote", action="store_true",
                    help="permit binding a non-loopback address (standalone mesh use)")
    a = ap.parse_args(argv)
    db = a.db.expanduser().resolve()

    if a.command in ("serve", "start") and not is_loopback(a.host) and not a.allow_remote:
        ap.error(f"refusing to bind {a.host}: Prove has no authentication in local mode. "
                 "Pass --allow-remote only on a network you trust.")
    if a.command == "init":
        print(f"created {db}" if init_ledger(db) else f"exists: {db}")
        return 0
    if a.command == "serve":
        serve(db, a.host, a.port)
        return 0
    if a.command == "start":
        return start(db, a.host, a.port)
    if a.command == "stop":
        return stop(a.port)
    if a.command == "status":
        h = health(a.port, a.host)
        print(json.dumps({"running": bool(h), "url": f"http://127.0.0.1:{a.port}/", "health": h}, indent=2))
        return 0 if h else 1
    if a.command == "upgrade":
        import provenance_schema
        from provenance_core import SCHEMA

        if not a.backup:
            ap.error("upgrade needs --backup /absolute/new/path.db")
        print(json.dumps(provenance_schema.upgrade(str(db), a.backup, SCHEMA), indent=2, default=str))
        return 0
    if a.command == "export":
        if not a.arg:
            ap.error("export needs a parent_prov_id")
        from urllib.parse import quote

        with _LOCAL.open(
            f"http://127.0.0.1:{a.port}/chain?parent_prov_id={quote(a.arg)}", timeout=10
        ) as r:
            sys.stdout.write(r.read().decode())
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

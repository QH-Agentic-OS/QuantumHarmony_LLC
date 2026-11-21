#!/usr/bin/env python3
"""
HTTP front-end for the ATP provenance store.

All provenance rules — manifest layer ordering, session-scoped bindings,
action chaining, redaction — live in ``provenance_core.ProvenanceStore``. This
module is the HTTP transport for them: it parses the request, calls one store
method, and sends back the ``(status, payload)`` it returns. The MCP front-end
in ``provenance_mcp.py`` calls the same store, so the two transports cannot
drift apart on what counts as a valid action.

CORS is wide open by design — the dashboard is served from a different port.
"""

import json
import os
import re
import sqlite3
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from provenance_core import (  # noqa: E402
    ProvenanceStore,
    get_collision_map,
    get_runtime_metadata,
)

DB_PATH = os.environ.get("PROV_DB", "provenance.db")
HOST = os.environ.get("PROV_HOST", "127.0.0.1")
PORT = int(os.environ.get("PROV_PORT", "8787"))

ROUTES = [
    "/health",
    "/mint",
    "/log",
    "/chain",
    "/verify",
    "/manifest/bind",
    "/manifest/layers",
    "/manifest/bindings",
    "/manifest/collisions",
    "/runtime/metadata",
    "/ingest/trajectory",
    "/capture/policy",
    "/v1/mint",
    "/v1/bind",
    "/v1/log",
    "/v1/chain",
    "/v1/verify",
]
MAX_BODY = 256 * 1024
# Transcript chunks are larger than single log entries. Kept at the worker
# proxy's limit so a chunk accepted here can also pass through the proxy.
INGEST_MAX_BODY = 2 * 1024 * 1024


class RequestError(ValueError):
    def __init__(self, status=422):
        self.status = status


def _strict_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON field")
        value[key] = item
    return value


def store() -> ProvenanceStore:
    """Store bound to the CURRENT module-level DB_PATH.

    Resolved per request rather than captured at import so tests (and anything
    else) can repoint ``provenance_service.DB_PATH`` at a temp database and
    have it take effect.
    """
    return ProvenanceStore(DB_PATH)


def db():
    """Open a connection to the configured database. Kept for callers that
    inspect the tables directly."""
    return store().connect()


def initialize_database():
    """Explicit operator/test setup; normal HTTP reads never create or migrate."""
    store().initialize()


def validate_ref_chain(conn, refs: dict):
    """Module-level alias for the store's L0→L3 linkage check."""
    return store().validate_ref_chain(conn, refs)


_HOST_PATTERN = re.compile(r"[A-Za-z0-9.\-]+(:[0-9]{1,5})?|\[[0-9A-Fa-f:.]+\](:[0-9]{1,5})?")
_ORIGIN_PATTERN = re.compile(r"https?://(" + _HOST_PATTERN.pattern + r")")


def _is_loopback_host(name):
    import ipaddress

    if name in ("localhost", ""):
        return name == "localhost"
    try:
        return ipaddress.ip_address(name.strip("[]")).is_loopback
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "ATPProvenance/0.1"

    def _owner_api_authorized(self):
        # Only the authenticated hosted handler admits a trusted v1 producer.
        return False

    # ── plumbing ──────────────────────────────────────────
    # The local service has no login, so a page open in the user's browser
    # must not be able to read or change it. Only the dashboard's own origins
    # get CORS; any other Origin (including "null") is refused, a cross-site
    # request without one is refused, and on a loopback bind the Host header
    # must be loopback too (DNS rebinding). Clients that send no Origin
    # (hooks, scripts, curl) are unaffected.
    def _host(self):
        """The Host header, or "" when it is not a plain host[:port]."""
        host = self.headers.get("Host", "")
        return host if _HOST_PATTERN.fullmatch(host) else ""

    def _allowed_origins(self):
        host = self._host()
        ui_port = os.environ.get("UI_PORT", "5175")
        extra = {
            o.strip().rstrip("/")
            for o in os.environ.get("PROV_ALLOWED_ORIGINS", "").split(",")
            if o.strip()
        }
        own = {f"http://{host}", f"https://{host}"} if host else set()
        return own | {
            f"http://localhost:{ui_port}",
            f"http://127.0.0.1:{ui_port}",
        } | extra

    def _matching_origin(self):
        """The allowlisted origin equal to this request's Origin, or None.

        The value returned comes from the allowlist, never from the request,
        so nothing a client sends is copied into a response header.
        """
        origin = self.headers.get("Origin")
        if origin is None:
            return None
        return next((o for o in self._allowed_origins() if o == origin and _ORIGIN_PATTERN.fullmatch(o)), None)

    def _request_trusted(self):
        bound = str(self.server.server_address[0])
        if _is_loopback_host(bound):
            name = urlparse(f"http://{self._host()}").hostname or ""
            if not _is_loopback_host(name):
                return False
        if self.headers.get("Origin") is not None:
            return self._matching_origin() is not None
        return self.headers.get("Sec-Fetch-Site", "none") in ("same-origin", "none")

    def _refuse_untrusted(self):
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _cors(self):
        origin = self._matching_origin()
        if origin is not None:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send(self, code, payload):
        body = json.dumps(payload, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        lengths = self.headers.get_all("Content-Length", [])
        if (
            len(lengths) != 1
            or len(lengths[0]) > 10
            or re.fullmatch(r"[0-9]+", lengths[0]) is None
            or self.headers.get("Transfer-Encoding")
        ):
            raise RequestError(400)
        length = int(lengths[0])
        limit = (
            INGEST_MAX_BODY
            if urlparse(self.path).path == "/ingest/trajectory"
            else MAX_BODY
        )
        if length > limit:
            raise RequestError(413)
        try:
            self.connection.settimeout(5)
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("truncated JSON")
            value = json.loads(
                raw,
                object_pairs_hook=_strict_object,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("nonfinite JSON")
                ),
            )
            if not isinstance(value, dict):
                raise ValueError("JSON object required")
            return value
        except (ValueError, UnicodeError, OSError, RecursionError):
            raise RequestError(422) from None

    def log_message(self, fmt, *args):
        print(f"  {self.address_string()} {fmt % args}")

    def do_OPTIONS(self):
        if not self._request_trusted():
            return self._refuse_untrusted()
        self.send_response(204)
        self._cors()
        self.end_headers()
        return None

    # ── routes ────────────────────────────────────────────
    def do_GET(self):
        if not self._request_trusted():
            return self._refuse_untrusted()
        try:
            return self._dispatch_get()
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return self._send(503, {"error": "provenance_unavailable"})

    def _dispatch_get(self):
        route = urlparse(self.path)
        query = parse_qs(route.query, keep_blank_values=True)

        if route.path.startswith("/v1/"):
            if not self._owner_api_authorized():
                return self._send(401, {"error": "unauthorized"})
            if route.path not in {"/v1/chain", "/v1/verify"}:
                return self._send(404, {"error": "not_found"})
            required = {"parent_prov_id", "principal_id", "tenant_id", "session_id"}
            allowed = required | (
                {"limit", "offset"} if route.path == "/v1/chain" else set()
            )
            if (
                not required <= query.keys()
                or not query.keys() <= allowed
                or any(len(v) != 1 for v in query.values())
            ):
                return self._send(422, {"error": "invalid_request"})
            owner = {
                key: query[key][0]
                for key in ("principal_id", "tenant_id", "session_id")
            }
            if route.path == "/v1/verify":
                return self._send(
                    *store().owned_verify(query["parent_prov_id"][0], owner)
                )
            try:
                values = (query.get("limit", ["100"])[0], query.get("offset", ["0"])[0])
                if any(
                    re.fullmatch(r"0|[1-9][0-9]{0,9}", value) is None
                    for value in values
                ):
                    raise ValueError()
                limit, offset = map(int, values)
            except ValueError:
                return self._send(422, {"error": "invalid_request"})
            return self._send(
                *store().owned_chain(
                    query["parent_prov_id"][0], owner, limit=limit, offset=offset
                )
            )

        def first(key):
            return (query.get(key) or [None])[0]

        if route.path == "/health":
            return self._send(*store().health())

        if route.path == "/manifest/layers":
            return self._send(
                *store().manifest_layers(
                    layer=first("layer"),
                    manifest_binding_id=first("manifest_binding_id"),
                )
            )

        if route.path == "/manifest/bindings":
            return self._send(
                *store().manifest_bindings(
                    manifest_binding_id=first("manifest_binding_id")
                )
            )

        if route.path == "/manifest/collisions":
            return self._send(200, get_collision_map())

        if route.path == "/runtime/metadata":
            return self._send(200, get_runtime_metadata())

        if route.path == "/chain":
            return self._send(*store().chain(first("parent_prov_id")))

        if route.path == "/verify":
            return self._send(*store().verify_chain(first("parent_prov_id")))

        return self._send(404, {"error": "not found", "routes": ROUTES})

    def do_POST(self):
        if not self._request_trusted():
            return self._refuse_untrusted()
        route = urlparse(self.path)
        owned = route.path.startswith("/v1/")
        if owned and not self._owner_api_authorized():
            return self._send(401, {"error": "unauthorized"})
        if owned and (
            route.path not in {"/v1/mint", "/v1/bind", "/v1/log"} or route.query
        ):
            return self._send(404, {"error": "not_found"})
        try:
            payload = self._read_json()
        except RequestError as error:
            return self._send(error.status, {"error": "invalid_request"})
        if owned:
            return self._send(
                *store().owned_mutation(route.path.rsplit("/", 1)[1], payload)
            )

        try:
            return self._legacy_post(route.path, payload)
        except (sqlite3.Error, ValueError, TypeError, KeyError):
            return self._send(503, {"error": "provenance_unavailable"})

    def _legacy_post(self, path, payload):

        if path == "/mint":
            status, result = store().mint(payload)
            if status == 200:
                print(f"  MINT  {result['prov_id']}")
            return self._send(status, result)

        if path == "/manifest/bind":
            status, result = store().bind_layer(payload)
            if status == 200:
                print(
                    f"  BIND  {result['layer']:<12} {result['layer_hash'][:12]}  "
                    f"binding={result['manifest_binding_id'][:12]}  "
                    f"parent={(result['parent_ref'] or '-')[:12]}"
                )
            return self._send(status, result)

        if path == "/ingest/trajectory":
            status, result = store().ingest_trajectory(payload)
            if status == 200 and result.get("steps"):
                print(
                    f"  INGEST {result['trajectory_id'][:16]}  chunk={result['chunk_no']}  "
                    f"steps={result['steps']}  to={result['consumed_to']}"
                )
            return self._send(status, result)

        if path == "/capture/policy":
            return self._send(*store().set_capture_policy(payload))

        if path == "/log":
            status, result = store().log_action(payload)
            if status == 200:
                print(
                    f"  LOG   {result['prov_id'][:8]}  "
                    f"parent={(result['parent_prov_id'] or '-')[:8]}  "
                    f"{payload.get('phase') or payload.get('action_type')}  "
                    f"binding={(result['manifest_binding_id'] or '-')[:8]} "
                    f"refs={result['layers_bound']}/4"
                )
            return self._send(status, result)

        return self._send(404, {"error": "not found"})


def probe(host: str, port: int, timeout: float = 1.0) -> str:
    """Is something on this port, and is it us? Returns 'ours' | 'foreign' | 'free'."""
    import socket
    import urllib.error
    import urllib.request

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        if sock.connect_ex(("127.0.0.1" if host == "0.0.0.0" else host, port)) != 0:
            return "free"
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=timeout
        ) as r:
            if json.loads(r.read()).get("service") == "atp-provenance":
                return "ours"
    except (urllib.error.URLError, json.JSONDecodeError, OSError, KeyError):
        # Something holds the port but does not answer /health like Prove.
        return "foreign"
    return "foreign"


def serve(host: str, port: int):
    """Bind and serve, converting Errno 48 into something actionable."""
    store().require_ready()
    print(
        f"  Selected ledger: {os.path.abspath(DB_PATH)} "
        "(PROV_DB environment; .env is not loaded)",
        file=sys.stderr,
    )
    try:
        httpd = ThreadingHTTPServer((host, port), Handler)
    except OSError as err:
        if err.errno not in (48, 98):  # EADDRINUSE on macOS / Linux
            raise
        state = probe(host, port)
        print(f"\n  ✗ port {port} is already in use.", file=sys.stderr)
        if state == "ours":
            print(
                "    Another atp-provenance instance is already serving it.",
                file=sys.stderr,
            )
            print(
                f"    Either use that one (it answers on http://localhost:{port}/health),",
                file=sys.stderr,
            )
            print(f"    or stop it:  lsof -ti:{port} | xargs kill", file=sys.stderr)
        else:
            print(
                "    Something else is holding it (not this service).", file=sys.stderr
            )
            print(f"    Inspect:  lsof -i :{port}", file=sys.stderr)
        print(
            f"    Or pick another port:  PROV_PORT={port + 1} python3 {os.path.basename(__file__)}\n",
            file=sys.stderr,
        )
        sys.exit(1)

    n = store().health()[1]["entries"]
    print(f"ATP Provenance Service  ->  http://{host}:{port}")
    print(f"  db: {os.path.abspath(DB_PATH)}  ({n} existing entries)")
    print("  routes: GET /health  POST /mint  POST /log  GET /chain?parent_prov_id=…")
    print("          GET /verify?parent_prov_id=…")
    print("          POST /manifest/bind  GET /manifest/layers  GET /manifest/bindings")
    print("          GET /manifest/collisions  GET /runtime/metadata")
    print("  CORS: open (required for the browser dashboard)\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped.")
    finally:
        httpd.server_close()  # release the socket instead of leaving it in TIME_WAIT


if __name__ == "__main__":
    serve(HOST, PORT)

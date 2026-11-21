"""Single-port hosted dashboard/API; only explicit dashboard assets are served."""

import base64
import binascii
import hmac
import os
from pathlib import Path
import secrets
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit

import provenance_service as service

# Plugin build: the network-free dashboard lives in ../ui (React vendored).
ROOT = Path(__file__).resolve().parent.parent / "ui"
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
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


def load_token(directory):
    """Keep the service-owned credential on persistent storage, never in logs."""
    supplied = os.environ.get("PROV_API_TOKEN")
    if supplied:
        return supplied
    path = directory / "provenance-access-token"
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        token = path.read_text().strip()
    else:
        token = secrets.token_urlsafe(32)
        with os.fdopen(fd, "w") as stream:
            stream.write(token + "\n")
    if len(token) < 32:
        raise ValueError("Hosted access token must contain at least 32 characters")
    return token


class Handler(service.Handler):
    def _owner_api_authorized(self):
        # do_GET/do_POST checked the service-owned credential before dispatch.
        return True

    def _cors(self):
        # Hosted UI and API share an origin. Do not grant cross-origin access.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")

    def authorized(self):
        values = self.headers.get_all("Authorization", [])
        auth = values[0] if len(values) == 1 else ""
        candidate = ""
        if auth.startswith("Bearer "):
            candidate = auth[7:]
        elif auth.startswith("Basic "):
            try:
                username, candidate = (
                    base64.b64decode(auth[6:], validate=True).decode().split(":", 1)
                )
                if username != "prove":
                    candidate = ""
            except (ValueError, UnicodeError, binascii.Error):
                candidate = ""
        if candidate and hmac.compare_digest(
            candidate.encode(), self.server.access_token.encode()
        ):
            return True
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Prove", charset="UTF-8"')
        self.send_header("Content-Length", "0")
        self._cors()
        self.end_headers()
        return False

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            # Check the database, but do not expose counts, paths, or records.
            status, _ = service.store().health()
            return self._send(
                status,
                {
                    "service": "atp-provenance",
                    "status": "ok" if status == 200 else "error",
                },
            )
        if path not in ASSETS and path not in service.ROUTES:
            return self._send(404, {"error": "not found"})
        if not self.authorized():
            return
        if path in ASSETS:
            filename, content_type = ASSETS[path]
            body = (ROOT / filename).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_POST(self):
        if self.authorized():
            super().do_POST()


def upgrade_if_requested(db_path):
    """Opt-in, backed-up ledger upgrade for hosts with no shell on the new build.

    Runs only when PROV_UPGRADE_BACKUP names a new absolute backup path. It
    never creates a ledger, never overwrites an existing backup, and leaves an
    already-current ledger (and the backup path) untouched.
    """
    backup = os.environ.get("PROV_UPGRADE_BACKUP")
    if not backup:
        return
    import provenance_schema
    from provenance_core import SCHEMA

    report = provenance_schema.upgrade(str(db_path), backup, SCHEMA)
    if report["changed"]:
        print(
            "Ledger upgraded to schema v1 after a verified backup; "
            "remove PROV_UPGRADE_BACKUP",
            flush=True,
        )


def main():
    db_path = Path(os.environ["PROV_DB"])
    if not db_path.is_absolute() or not db_path.parent.is_dir():
        raise ValueError(
            "PROV_DB must be an absolute path inside an existing persistent disk"
        )
    # Require explicit initialization/migration; a typo must not create an empty store.
    if not db_path.is_file():
        raise ValueError(
            "Initialize or migrate the persistent database before starting"
        )
    service.DB_PATH = str(db_path)
    upgrade_if_requested(db_path)
    service.store().require_ready()
    token = load_token(db_path.parent)
    service.store().health()
    with ThreadingHTTPServer(
        ("0.0.0.0", int(os.environ.get("PORT", "10000"))), Handler
    ) as server:
        server.access_token = token
        print("Prove hosted dashboard/API ready; authentication enabled", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()

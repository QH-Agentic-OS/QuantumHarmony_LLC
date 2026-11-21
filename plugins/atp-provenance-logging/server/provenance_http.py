"""HTTP compatibility client authentication; no production authority is implied."""

import ipaddress
import os
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never replay provenance writes or credentials to a redirected URL.
        return None


def open_provenance_request(request, *, timeout):
    """Use the operator's token and Python's normal certificate verification.

    Local development remains available without a token. A configured token
    requires HTTPS, except for explicit loopback development endpoints.
    """
    parsed = urlsplit(request.full_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError("Invalid provenance service URL")
    token = os.environ.get("PROV_API_TOKEN", "").strip()
    if not token and os.environ.get("PROV_API_TOKEN_FILE"):
        token = Path(os.environ["PROV_API_TOKEN_FILE"]).expanduser().read_text().strip()
        if not token:
            raise ValueError("Configured provenance token file is empty")
    if token:
        try:
            loopback = ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            loopback = parsed.hostname == "localhost"
        if parsed.scheme != "https" and not loopback:
            raise ValueError("Provenance bearer authentication requires HTTPS")
        if "\r" in token or "\n" in token:
            raise ValueError("Invalid provenance bearer token")
        request.add_unredirected_header("Authorization", f"Bearer {token}")
    # HTTPSHandler uses the default verified SSL context, including the
    # operator's SSL_CERT_FILE / SSL_CERT_DIR trust configuration.
    handlers = [_NoRedirect()]
    if _is_loopback(parsed.hostname):
        # Loopback traffic never goes through an environment proxy: a
        # local ledger must not leak through HTTP_PROXY.
        handlers.append(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener(*handlers).open(request, timeout=timeout)


def _is_loopback(hostname: str) -> bool:
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return hostname == "localhost"

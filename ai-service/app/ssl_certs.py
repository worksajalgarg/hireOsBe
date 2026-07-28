"""Configure TLS CA bundle early (macOS / custom Python builds)."""

from __future__ import annotations

import os


def configure_ssl_certs() -> None:
    """Point SSL env vars at certifi's CA bundle when not already set."""
    try:
        import certifi
    except ImportError:
        return

    ca_path = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_path)
    os.environ.setdefault("CURL_CA_BUNDLE", ca_path)

"""Configure TLS CA bundle early (macOS / custom Python builds)."""

from __future__ import annotations

import os
from pathlib import Path


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


def configure_huggingface_offline() -> None:
    """Prefer local Docling/HF model cache when available.

    Docling downloads layout/table models from Hugging Face on first use.
    Corporate proxies often return 403 for huggingface.co; if models are
    already cached, force offline mode so conversion works without network.
    Set HF_HUB_OFFLINE=0 explicitly to allow downloads (first-time setup).
    """
    if "HF_HUB_OFFLINE" in os.environ:
        return

    hub = Path.home() / ".cache" / "huggingface" / "hub"
    cached = any(
        (hub / name).exists()
        for name in (
            "models--docling-project--docling-layout-heron",
            "models--docling-project--docling-models",
        )
    )
    if cached:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

"""Thin helpers over the `fal_client` SDK.

Keeps credential resolution, CDN uploads, downloads and a couple of thin
wrappers in one place so the rest of the app never touches fal directly.
"""

from __future__ import annotations

import os
import urllib.request
from typing import Any, Callable

import fal_client

from . import config
from .store import Asset, Library

_USER_AGENT = f"{config.APP_NAME}/0.1 (+https://fal.ai)"
_DOWNLOAD_TIMEOUT = 180


class FalNotConfigured(RuntimeError):
    """Raised when a fal call is attempted without an API key."""


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #


_source = "None"


def resolve_key() -> str | None:
    """Return the active fal key without changing credentials."""
    key = os.environ.get("FAL_KEY")
    if key and key.strip():
        return key.strip()
    return configure()


def _secret_key() -> str | None:
    try:
        import streamlit as st

        value = st.secrets.get("FAL_KEY")  # type: ignore[union-attr]
    except Exception:
        return None
    return str(value).strip() if value else None


def configure() -> str | None:
    """Make sure `FAL_KEY` is exported for the SDK. Returns the active key."""
    global _source
    key = os.environ.get("FAL_KEY")
    if key and key.strip():
        if _source == "None":
            _source = "FAL_KEY environment variable"
        return key.strip()

    secret = _secret_key()
    if secret:
        os.environ["FAL_KEY"] = secret
        _source = "Streamlit secrets"
        return secret

    saved = config.load_config().get("fal_key")
    if saved and str(saved).strip():
        clean = str(saved).strip()
        os.environ["FAL_KEY"] = clean
        _source = "Saved in Vertigo settings"
        return clean

    _source = "None"
    return None


def has_key() -> bool:
    return resolve_key() is not None


def key_source() -> str:
    return _source


def save_key(key: str) -> None:
    global _source
    clean = key.strip()
    config.update_config(fal_key=clean)
    os.environ["FAL_KEY"] = clean
    _source = "Saved in Vertigo settings"


def clear_saved_key() -> None:
    global _source
    config.update_config(fal_key="")
    if _source == "Saved in Vertigo settings":
        os.environ.pop("FAL_KEY", None)
        _source = "None"


def key_hint(key: str | None) -> str:
    """A masked representation of the key for display."""
    if not key:
        return "Not configured"
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:4]}…{key[-4:]}"


# --------------------------------------------------------------------------- #
# CDN up/downloads
# --------------------------------------------------------------------------- #


def upload_file(path: str) -> str:
    """Upload a local file to the fal CDN and return its URL."""
    return fal_client.upload_file(path)


def upload_bytes(data: bytes, media_type: str, filename: str) -> str:
    return fal_client.upload(data, media_type or "application/octet-stream", filename)


def ensure_remote_url(asset: Asset, library: Library) -> str:
    """Return a fal CDN URL for an asset, uploading it once and caching it."""
    if asset.remote_url:
        return asset.remote_url
    path = library.file_path(asset)
    if not path or not path.exists():
        raise FileNotFoundError(f"Asset {asset.id} has no local file to upload")
    url = upload_file(str(path))
    library.update(asset.id, remote_url=url)
    return url


def download_bytes(url: str) -> bytes:
    """Download a remote file into memory."""
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_DOWNLOAD_TIMEOUT) as response:
        return response.read()


# --------------------------------------------------------------------------- #
# Inference
# --------------------------------------------------------------------------- #


def subscribe(
    endpoint: str,
    arguments: dict[str, Any],
    *,
    on_enqueue: Callable[[str], None] | None = None,
    on_queue_update: Callable[[Any], None] | None = None,
    interval: float = 1.0,
) -> dict[str, Any]:
    if not configure():
        raise FalNotConfigured(
            "No fal API key configured. Add one on the Settings page."
        )
    return fal_client.subscribe(
        endpoint,
        arguments=arguments,
        with_logs=True,
        interval=interval,
        on_enqueue=on_enqueue,
        on_queue_update=on_queue_update,
    )


def status(endpoint: str, request_id: str, *, with_logs: bool = True) -> Any:
    if not configure():
        raise FalNotConfigured("No fal API key configured.")
    return fal_client.status(endpoint, request_id, with_logs=with_logs)


def result(endpoint: str, request_id: str) -> dict[str, Any]:
    if not configure():
        raise FalNotConfigured("No fal API key configured.")
    return fal_client.result(endpoint, request_id)


def cancel(endpoint: str, request_id: str) -> None:
    try:
        fal_client.cancel(endpoint, request_id)
    except Exception:
        # Cancelling is best-effort; the job may already be terminal.
        pass


def redact(message: str) -> str:
    """Remove a configured key from error text before showing it to a user."""
    key = resolve_key()
    if key and key in message:
        message = message.replace(key, "***")
    return message

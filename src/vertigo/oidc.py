"""Telegram (OpenID Connect) sign-in for Vertigo.

Vertigo is normally protected by per-profile PINs. When OIDC is enabled the
outer gate becomes Telegram instead, and each Telegram account is mapped to a
Vertigo profile (created on first sign-in), so libraries stay separated.

Configuration comes from the environment so a systemd/launchd/Docker service can
hold it:

* ``VERTIGO_OIDC_ENABLED``       — ``1``/``true`` to require Telegram sign-in
* ``VERTIGO_OIDC_CLIENT_ID``     — the bot's numeric id from @BotFather
* ``VERTIGO_OIDC_CLIENT_SECRET`` — the Client Secret from @BotFather
* ``VERTIGO_OIDC_REDIRECT_URI``  — optional explicit callback URL
* ``VERTIGO_PUBLIC_URL``         — e.g. ``https://vertigo.example.com``
* ``VERTIGO_PORT``               — local port used for the callback fallback
* ``VERTIGO_SECRETS_DIR``        — where ``secrets.toml`` is written

Streamlit reads ``secrets.toml`` from the working directory, so Vertigo writes it
to ``<cwd>/.streamlit/`` for the running deployment (override with
``VERTIGO_SECRETS_DIR``) and *merges* with any existing file, so a hand-written
``FAL_KEY`` in secrets is never destroyed.
"""

from __future__ import annotations

import json
import os
import re
import secrets as _secrets
from pathlib import Path

from . import config

PROVIDER = "telegram"
METADATA_URL = "https://oauth.telegram.org/.well-known/openid-configuration"
DEFAULT_SCOPE = "openid profile"
DEFAULT_PORT = "8501"
_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def enabled() -> bool:
    """Return whether Telegram sign-in is configured and requested."""
    return _flag("VERTIGO_OIDC_ENABLED") and bool(client_id()) and bool(client_secret())


def client_id() -> str:
    return os.environ.get("VERTIGO_OIDC_CLIENT_ID", "").strip()


def client_secret() -> str:
    return os.environ.get("VERTIGO_OIDC_CLIENT_SECRET", "").strip()


def redirect_uri() -> str:
    explicit = os.environ.get("VERTIGO_OIDC_REDIRECT_URI", "").strip()
    if explicit:
        return explicit
    public = os.environ.get("VERTIGO_PUBLIC_URL", "").rstrip("/")
    if public:
        return f"{public}/oauth2callback"
    port = os.environ.get("VERTIGO_PORT", DEFAULT_PORT)
    return f"http://localhost:{port}/oauth2callback"


def cookie_secret() -> str:
    """Return a stable cookie-signing secret, generating one on first use."""
    existing = config.load_config().get("oidc_cookie_secret")
    if existing:
        return str(existing)
    value = _secrets.token_urlsafe(48)
    config.update_config(oidc_cookie_secret=value)
    return value


def secrets_dir() -> Path:
    """Directory holding Streamlit's ``secrets.toml`` for this deployment.

    Streamlit resolves its config relative to the process working directory, so
    a repo checkout, a Docker image and a service unit all stay in sync as long
    as they run from the same place. ``VERTIGO_SECRETS_DIR`` overrides it for
    read-only trees.
    """
    override = os.environ.get("VERTIGO_SECRETS_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    return Path.cwd() / ".streamlit"


def secrets_path() -> Path:
    return secrets_dir() / "secrets.toml"


def _managed_sections() -> dict[str, list[str]]:
    """TOML tables Vertigo owns, serialised as ``{table: [lines]}``."""
    return {
        "auth": [
            f"redirect_uri = {json.dumps(redirect_uri())}",
            f"cookie_secret = {json.dumps(cookie_secret())}",
        ],
        f"auth.{PROVIDER}": [
            f"client_id = {json.dumps(client_id())}",
            f"client_secret = {json.dumps(client_secret())}",
            f"server_metadata_url = {json.dumps(METADATA_URL)}",
            f"client_kwargs = {{ scope = {json.dumps(DEFAULT_SCOPE)} }}",
        ],
    }


def merge_secrets(existing: str) -> str:
    """Return ``existing`` with Vertigo's tables updated in place.

    Everything Vertigo does not manage (e.g. a top-level ``FAL_KEY``) is kept
    verbatim, so enabling Telegram sign-in never wipes a hand-written file.
    """
    managed = _managed_sections()
    preamble: list[str] = []
    order: list[str] = []
    bodies: dict[str, list[str]] = {}
    current: str | None = None

    for line in existing.splitlines():
        match = _SECTION_RE.match(line)
        if match:
            current = match.group(1).strip()
            if current not in bodies:
                order.append(current)
                bodies[current] = []
            bodies[current].append(line)
        elif current is None:
            preamble.append(line)
        else:
            bodies[current].append(line)

    for name in managed:
        if name not in bodies:
            order.append(name)

    lines = list(preamble)
    for name in order:
        block = [f"[{name}]", *managed[name]] if name in managed else bodies[name]
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(block)
    return "\n".join(lines).strip("\n") + "\n"


def render_secrets(existing: str = "") -> str:
    """Render ``secrets.toml`` content, preserving unrelated ``existing`` data."""
    body = merge_secrets(existing)
    banner = "# Generated by Vertigo for Telegram sign-in — keep it private."
    if banner in body:
        return body
    return f"{banner}\n\n{body}"


def write_secrets() -> Path | None:
    """Write Streamlit's ``secrets.toml`` when Telegram sign-in is enabled."""
    if not enabled():
        return None
    path = secrets_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        path.write_text(render_secrets(existing), encoding="utf-8")
        path.chmod(0o600)
    except OSError:
        # A read-only tree shouldn't stop the app: operators can set
        # VERTIGO_SECRETS_DIR or provide secrets.toml themselves.
        return None
    return path


# --------------------------------------------------------------------------- #
# Streamlit helpers
# --------------------------------------------------------------------------- #
def is_logged_in() -> bool:
    try:
        import streamlit as st

        return bool(st.user.is_logged_in)
    except Exception:  # noqa: BLE001
        return False


def subject() -> str:
    """Return the stable Telegram subject identifier."""
    try:
        import streamlit as st

        for key in ("sub", "id"):
            value = getattr(st.user, key, None)
            if value:
                return str(value)
    except Exception:  # noqa: BLE001
        return ""
    return ""


def display_name() -> str:
    try:
        import streamlit as st

        for key in ("name", "preferred_username", "given_name"):
            value = getattr(st.user, key, None)
            if value:
                return str(value)
    except Exception:  # noqa: BLE001
        return ""
    return ""


def username() -> str:
    try:
        import streamlit as st

        return str(getattr(st.user, "preferred_username", "") or "")
    except Exception:  # noqa: BLE001
        return ""

"""Simple per-profile authentication for Vertigo.

A small registry of family profiles, each protected by a PIN. This is profile
separation for a trusted local network — it keeps everyone's library apart, but
it is not a hardened security boundary (traffic is plain HTTP).

Credentials live in ``<VERTIGO_HOME>/users.json`` with salted PBKDF2 hashes.
Each profile's media lives under ``<VERTIGO_HOME>/users/<id>``.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import config

DEFAULT_PIN = "0000"
SEED_PROFILES = ["User 1", "User 2", "User 3"]
MIN_PIN_LENGTH = 4
MAX_PROFILES = 12
_PBKDF2_ITERATIONS = 200_000

# "Remember me" cookie + server-side session tokens.
COOKIE_NAME = "vertigo_session"
SESSION_DAYS = 30
MAX_SESSIONS = 500


class AuthError(Exception):
    """Raised for invalid profile operations.

    Carries a translation key and its parameters so the UI can render the
    message in the active language.
    """

    def __init__(self, key: str, **params: object) -> None:
        super().__init__(key)
        self.key = key
        self.params = params


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_pin(pin: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return base64.b64encode(digest).decode("ascii")


@dataclass
class User:
    id: str
    name: str
    telegram_id: str = ""
    pin_salt: str = ""
    pin_hash: str = ""
    is_admin: bool = False
    must_change_pin: bool = False
    locale: str = "en"
    created_at: str = field(default_factory=_now)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "User":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_lock = threading.RLock()


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #


def _load_raw() -> list[dict[str, Any]]:
    path = config.users_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    records = data.get("users", []) if isinstance(data, dict) else data
    return records if isinstance(records, list) else []


def _save(users: list[User]) -> None:
    config.ensure_base_dirs()
    payload = {
        "version": 1,
        "updated_at": _now(),
        "users": [user.to_dict() for user in users],
    }
    path = config.users_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


def list_users() -> list[User]:
    with _lock:
        return [User.from_dict(record) for record in _load_raw()]


def get_user(user_id: str | None) -> User | None:
    if not user_id:
        return None
    with _lock:
        for record in _load_raw():
            if record.get("id") == user_id:
                return User.from_dict(record)
    return None


def user_by_name(name: str) -> User | None:
    needle = name.strip().casefold()
    for user in list_users():
        if user.name.strip().casefold() == needle:
            return user
    return None


def user_by_telegram(telegram_id: str | None) -> User | None:
    """Return the profile linked to a Telegram subject id, if any."""
    if not telegram_id:
        return None
    needle = str(telegram_id)
    for user in list_users():
        if user.telegram_id == needle:
            return user
    return None


def ensure_telegram_user(telegram_id: str, name: str = "", username: str = "") -> User:
    """Return the profile for a Telegram account, creating it on first sign-in."""
    existing = user_by_telegram(telegram_id)
    if existing is not None:
        return existing
    cleaned = (name or username or f"Telegram {str(telegram_id)[-4:]}").strip()[:40]
    cleaned = cleaned or "Telegram user"
    with _lock:
        users = [User.from_dict(r) for r in _load_raw()]
        taken = {user.name.strip().casefold() for user in users}
        candidate = cleaned
        suffix = 2
        while candidate.casefold() in taken:
            candidate = f"{cleaned} {suffix}"
            suffix += 1
        user = User(
            id=uuid.uuid4().hex[:8],
            name=candidate,
            telegram_id=str(telegram_id),
            is_admin=not any(u.is_admin for u in users if u.telegram_id),
            must_change_pin=False,
        )
        users.append(user)
        _save(users)
        return user


def is_admin(user_id: str | None) -> bool:
    user = get_user(user_id)
    return bool(user and user.is_admin)


def error_text(exc: Exception) -> str:
    """Render an :class:`AuthError` in the active language."""
    from . import i18n

    key = getattr(exc, "key", None)
    if key:
        return i18n.t(key, **getattr(exc, "params", {}))
    return str(exc)


# --------------------------------------------------------------------------- #
# Credentials
# --------------------------------------------------------------------------- #


def authenticate(user_id: str, pin: str) -> bool:
    user = get_user(user_id)
    if user is None or not pin or not user.pin_salt or not user.pin_hash:
        return False
    try:
        salt = base64.b64decode(user.pin_salt)
    except (ValueError, TypeError):
        return False
    return secrets.compare_digest(user.pin_hash, _hash_pin(pin, salt))


def _validate_pin(pin: str) -> None:
    if len(pin) < MIN_PIN_LENGTH:
        raise AuthError("auth.pin_short", count=MIN_PIN_LENGTH)


def _validate_name(name: str, *, exclude_id: str | None = None) -> str:
    clean = name.strip()
    if not clean:
        raise AuthError("auth.name_empty")
    if len(clean) > 40:
        raise AuthError("auth.name_long")
    existing = user_by_name(clean)
    if existing is not None and existing.id != exclude_id:
        raise AuthError("auth.name_exists", name=clean)
    return clean


def set_pin(user_id: str, pin: str) -> None:
    _validate_pin(pin)
    with _lock:
        users = [User.from_dict(r) for r in _load_raw()]
        for user in users:
            if user.id == user_id:
                salt = secrets.token_bytes(16)
                user.pin_salt = base64.b64encode(salt).decode("ascii")
                user.pin_hash = _hash_pin(pin, salt)
                user.must_change_pin = False
                _save(users)
                revoke_user_sessions(user_id)
                return
    raise AuthError("auth.profile_not_found")


def rename_user(user_id: str, name: str) -> None:
    clean = _validate_name(name, exclude_id=user_id)
    with _lock:
        users = [User.from_dict(r) for r in _load_raw()]
        for user in users:
            if user.id == user_id:
                user.name = clean
                _save(users)
                return
    raise AuthError("auth.profile_not_found")


def set_locale(user_id: str, locale: str) -> None:
    """Persist a profile's interface language."""
    clean = str(locale).strip().lower() or "en"
    with _lock:
        users = [User.from_dict(r) for r in _load_raw()]
        for user in users:
            if user.id == user_id:
                user.locale = clean
                _save(users)
                return


def create_user(name: str, pin: str, *, is_admin: bool = False) -> User:
    clean = _validate_name(name)
    _validate_pin(pin)
    with _lock:
        users = [User.from_dict(r) for r in _load_raw()]
        if len(users) >= MAX_PROFILES:
            raise AuthError("auth.max_profiles", count=MAX_PROFILES)
        salt = secrets.token_bytes(16)
        user = User(
            id=uuid.uuid4().hex[:8],
            name=clean,
            pin_salt=base64.b64encode(salt).decode("ascii"),
            pin_hash=_hash_pin(pin, salt),
            is_admin=is_admin,
            must_change_pin=False,
        )
        users.append(user)
        _save(users)
        return user


def delete_user(user_id: str, *, remove_data: bool = False) -> None:
    with _lock:
        users = [User.from_dict(r) for r in _load_raw()]
        target = next((u for u in users if u.id == user_id), None)
        if target is None:
            raise AuthError("auth.profile_not_found")
        remaining = [u for u in users if u.id != user_id]
        if not remaining:
            raise AuthError("auth.last_profile")
        if target.is_admin and not any(u.is_admin for u in remaining):
            raise AuthError("auth.last_admin")
        _save(remaining)
        revoke_user_sessions(user_id)
    if remove_data:
        shutil.rmtree(config.user_home(user_id), ignore_errors=True)
    # Drop cached library/manager so the directory isn't recreated.
    from . import jobs, store

    store.drop_library(user_id)
    jobs.drop_manager(user_id)


# --------------------------------------------------------------------------- #
# Remembered sessions (cookie tokens)
# --------------------------------------------------------------------------- #


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _load_sessions() -> list[dict[str, Any]]:
    path = config.sessions_file()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    records = data.get("sessions", []) if isinstance(data, dict) else data
    return records if isinstance(records, list) else []


def _save_sessions(records: list[dict[str, Any]]) -> None:
    config.ensure_base_dirs()
    payload = {"version": 1, "updated_at": _now(), "sessions": records}
    path = config.sessions_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _purge_expired(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = time.time()
    return [r for r in records if float(r.get("expires_at", 0)) > now]


def create_session(user_id: str, *, days: int = SESSION_DAYS) -> str:
    """Create a long-lived remember-me token and return the raw value."""
    token = secrets.token_urlsafe(32)
    with _lock:
        records = _purge_expired(_load_sessions())
        records.append(
            {
                "token_hash": _hash_token(token),
                "user_id": user_id,
                "created_at": _now(),
                "expires_at": time.time() + days * 86_400,
            }
        )
        _save_sessions(records[-MAX_SESSIONS:])
    return token


def resolve_session(token: str | None) -> str | None:
    """Return the profile id for a valid remember-me token, else None."""
    if not token or not isinstance(token, str):
        return None
    digest = _hash_token(token)
    with _lock:
        records = _load_sessions()
        purged = _purge_expired(records)
        if len(purged) != len(records):
            _save_sessions(purged)
        for record in purged:
            if secrets.compare_digest(str(record.get("token_hash", "")), digest):
                user_id = record.get("user_id")
                return user_id if get_user(user_id) else None
    return None


def revoke_session(token: str | None) -> None:
    if not token or not isinstance(token, str):
        return
    digest = _hash_token(token)
    with _lock:
        records = _load_sessions()
        remaining = [
            r
            for r in records
            if not secrets.compare_digest(str(r.get("token_hash", "")), digest)
        ]
        if len(remaining) != len(records):
            _save_sessions(remaining)


def revoke_user_sessions(user_id: str) -> None:
    with _lock:
        records = _load_sessions()
        remaining = [r for r in records if r.get("user_id") != user_id]
        if len(remaining) != len(records):
            _save_sessions(remaining)


# --------------------------------------------------------------------------- #
# Seeding & migration
# --------------------------------------------------------------------------- #


def _has_legacy_data() -> bool:
    base = config.base_home()
    if (base / "library.json").exists() or (base / "jobs.json").exists():
        return True
    assets = base / "assets"
    return assets.is_dir() and any(assets.iterdir())


def _migrate_legacy(user_id: str) -> None:
    """Move a pre-profiles single-user library into the first profile."""
    base = config.base_home()
    destination = config.user_home(user_id)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("library.json", "jobs.json"):
        source = base / name
        if source.exists():
            shutil.move(str(source), str(destination / name))
    assets = base / "assets"
    if assets.is_dir() and any(assets.iterdir()):
        shutil.move(str(assets), str(destination / "assets"))


def ensure_users() -> None:
    """Create the default profiles on first run and migrate legacy data.

    Also recovers from a missing or unreadable registry so the app is never
    left with no way in.
    """
    config.ensure_base_dirs()
    if config.users_file().exists() and _load_raw():
        return
    with _lock:
        if config.users_file().exists() and _load_raw():
            return
        had_legacy = _has_legacy_data()
        users: list[User] = []
        for index, name in enumerate(SEED_PROFILES):
            salt = secrets.token_bytes(16)
            users.append(
                User(
                    id=uuid.uuid4().hex[:8],
                    name=name,
                    pin_salt=base64.b64encode(salt).decode("ascii"),
                    pin_hash=_hash_pin(DEFAULT_PIN, salt),
                    is_admin=index == 0,
                    must_change_pin=True,
                )
            )
        _save(users)
        if had_legacy:
            _migrate_legacy(users[0].id)

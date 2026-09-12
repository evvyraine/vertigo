"""A small, thread-safe, file-backed media library.

Assets are the unit of storage: generated images, traced vectors, speech,
transcripts and the reference images a user uploads. Binary content lives in
``<VERTIGO_HOME>/assets`` while metadata lives in ``library.json``.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import config

_EXT_BY_MEDIA = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/svg+xml": ".svg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/ogg": ".ogg",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
    "text/plain": ".txt",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _extension_for(media_type: str, name: str, fallback: str = ".bin") -> str:
    media = (media_type or "").split(";")[0].strip().lower()
    if media in _EXT_BY_MEDIA:
        return _EXT_BY_MEDIA[media]
    guessed = mimetypes.guess_extension(media) if media else None
    if guessed:
        return ".jpg" if guessed == ".jpe" else guessed
    suffix = Path(name).suffix
    return suffix if suffix else fallback


@dataclass
class Asset:
    """A single item in the library."""

    id: str
    kind: str
    name: str
    origin: str = config.ORIGIN_GENERATED
    path: str = ""
    media_type: str = ""
    remote_url: str = ""
    prompt: str = ""
    endpoint: str = ""
    parent_id: str | None = None
    size: int = 0
    created_at: str = field(default_factory=_now)
    meta: dict[str, Any] = field(default_factory=dict)

    # -- serialisation ----------------------------------------------------- #
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # -- conveniences ------------------------------------------------------ #
    @property
    def is_visual(self) -> bool:
        return self.kind in (config.KIND_IMAGE, config.KIND_VECTOR)

    @property
    def media_root(self) -> str:
        return (self.media_type or "").split(";")[0].strip().lower()

    @property
    def is_svg(self) -> bool:
        return self.media_root == "image/svg+xml" or self.name.lower().endswith(".svg")

    def has_remote(self) -> bool:
        return bool(self.remote_url)


class Library:
    """Thread-safe collection of assets with on-disk persistence."""

    def __init__(self, home: Path) -> None:
        self.home = Path(home)
        self.assets_dir = self.home / "assets"
        self.library_path = self.home / "library.json"
        self._lock = threading.RLock()
        self._assets: dict[str, Asset] = {}
        self.ensure_dirs()
        self._load()

    def ensure_dirs(self) -> None:
        self.home.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        path = self.library_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        records = data.get("assets", []) if isinstance(data, dict) else data
        for record in records:
            try:
                asset = Asset.from_dict(record)
            except (TypeError, ValueError):
                continue
            self._assets[asset.id] = asset

    def _persist_locked(self) -> None:
        payload = {
            "version": 1,
            "updated_at": _now(),
            "assets": [a.to_dict() for a in self._assets.values()],
        }
        self.ensure_dirs()
        tmp = self.library_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.library_path)

    # -- reads ------------------------------------------------------------- #
    def get(self, asset_id: str) -> Asset | None:
        with self._lock:
            return self._assets.get(asset_id)

    def all(self) -> list[Asset]:
        with self._lock:
            return list(self._assets.values())

    def filter(
        self,
        *,
        kinds: Iterable[str] | None = None,
        origins: Iterable[str] | None = None,
        search: str | None = None,
    ) -> list[Asset]:
        kind_set = set(kinds) if kinds else None
        origin_set = set(origins) if origins else None
        needle = (search or "").strip().lower()
        with self._lock:
            items = list(self._assets.values())
        result = []
        for asset in items:
            if kind_set and asset.kind not in kind_set:
                continue
            if origin_set and asset.origin not in origin_set:
                continue
            if needle:
                haystack = " ".join(
                    [asset.name, asset.prompt, asset.endpoint, asset.media_type]
                ).lower()
                if needle not in haystack:
                    continue
            result.append(asset)
        return result

    def newest_first(self, assets: Iterable[Asset] | None = None) -> list[Asset]:
        items = list(assets) if assets is not None else self.all()
        return sorted(items, key=lambda a: a.created_at, reverse=True)

    def recent(self, limit: int = 12, *, kinds: Iterable[str] | None = None) -> list[Asset]:
        return self.newest_first(self.filter(kinds=kinds))[:limit]

    def counts(self) -> dict[str, int]:
        counts = {"total": 0}
        for kind in config.KINDS:
            counts[kind] = 0
        with self._lock:
            items = list(self._assets.values())
        for asset in items:
            counts["total"] += 1
            counts[asset.kind] = counts.get(asset.kind, 0) + 1
        return counts

    def file_path(self, asset: Asset) -> Path:
        return (self.home / asset.path).resolve() if asset.path else Path()

    # -- writes ------------------------------------------------------------ #
    def add_file(
        self,
        data: bytes,
        *,
        kind: str,
        name: str,
        origin: str = config.ORIGIN_GENERATED,
        media_type: str = "",
        prompt: str = "",
        endpoint: str = "",
        parent_id: str | None = None,
        remote_url: str = "",
        meta: dict[str, Any] | None = None,
    ) -> Asset:
        """Write ``data`` to the assets folder and register it."""
        asset_id = uuid.uuid4().hex[:12]
        ext = _extension_for(media_type, name)
        filename = f"{asset_id}{ext}"
        self.ensure_dirs()
        destination = self.assets_dir / filename
        destination.write_bytes(data)

        asset = Asset(
            id=asset_id,
            kind=kind,
            name=name or filename,
            origin=origin,
            path=str(Path("assets") / filename),
            media_type=media_type or mimetypes.guess_type(name)[0] or "application/octet-stream",
            remote_url=remote_url,
            prompt=prompt,
            endpoint=endpoint,
            parent_id=parent_id,
            size=len(data),
            meta=dict(meta or {}),
        )
        with self._lock:
            self._assets[asset.id] = asset
            self._persist_locked()
        return asset

    def update(self, asset_id: str, **fields: Any) -> Asset | None:
        with self._lock:
            asset = self._assets.get(asset_id)
            if asset is None:
                return None
            for key, value in fields.items():
                if hasattr(asset, key):
                    setattr(asset, key, value)
            self._persist_locked()
            return asset

    def delete(self, asset_id: str, *, delete_file: bool = True) -> bool:
        with self._lock:
            asset = self._assets.pop(asset_id, None)
            if asset is None:
                return False
            self._persist_locked()
        if delete_file and asset.path:
            try:
                (self.home / asset.path).unlink(missing_ok=True)
            except OSError:
                pass
        return True

    def clear(self, *, keep_references: bool = True) -> int:
        with self._lock:
            if keep_references:
                doomed = [
                    a.id
                    for a in self._assets.values()
                    if a.origin != config.ORIGIN_REFERENCE
                ]
            else:
                doomed = list(self._assets)
        for asset_id in doomed:
            self.delete(asset_id)
        return len(doomed)

    # -- small helpers ----------------------------------------------------- #
    def bytes_of(self, asset: Asset) -> bytes:
        path = self.file_path(asset)
        if path and path.exists():
            return path.read_bytes()
        return b""

    def text_of(self, asset: Asset) -> str:
        try:
            return self.bytes_of(asset).decode("utf-8", errors="replace")
        except OSError:
            return ""


_libraries: dict[str, Library] = {}
_libraries_lock = threading.Lock()


def get_library(user_id: str) -> Library:
    """Return the library for a profile, creating it on first use."""
    with _libraries_lock:
        library = _libraries.get(user_id)
        if library is None:
            library = Library(config.user_home(user_id))
            _libraries[user_id] = library
        return library


def drop_library(user_id: str) -> None:
    """Forget a cached library (used when a profile is deleted)."""
    with _libraries_lock:
        _libraries.pop(user_id, None)

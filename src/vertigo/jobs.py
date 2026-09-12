"""Background generation queue.

Jobs are submitted to fal's queue and tracked by a small thread pool so the
Streamlit UI never blocks on a generation. Job state is persisted so an
in-flight job can be picked back up after a server restart. Completed outputs
are downloaded into the local library automatically.
"""

from __future__ import annotations

import json
import mimetypes
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import fal_client

from . import config, fal
from .store import Library, get_library

# How a job's result should be turned into library assets.
SAVE_IMAGES = "images"
SAVE_IMAGE = "image"
SAVE_AUDIO = "audio"
SAVE_TRANSCRIPT = "transcript"

ACTIVE_STATUSES = ("queued", "running")
TERMINAL_STATUSES = ("completed", "failed", "cancelled")

_STATUS_ICONS = {
    "queued": ":material/schedule:",
    "running": ":material/progress_activity:",
    "completed": ":material/check_circle:",
    "failed": ":material/error:",
    "cancelled": ":material/cancel:",
}

_STATUS_COLORS = {
    "queued": "orange",
    "running": "blue",
    "completed": "green",
    "failed": "red",
    "cancelled": "gray",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def status_icon(status: str) -> str:
    return _STATUS_ICONS.get(status, ":material/help:")


def status_color(status: str) -> str:
    return _STATUS_COLORS.get(status, "gray")


@dataclass
class Job:
    id: str
    kind: str  # image | vector | upscale | remove_bg | tts | stt
    label: str
    endpoint: str
    arguments: dict[str, Any]
    save_kind: str
    status: str = "queued"
    request_id: str | None = None
    logs: list[str] = field(default_factory=list)
    error: str | None = None
    asset_ids: list[str] = field(default_factory=list)
    parent_id: str | None = None
    summary: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE_STATUSES


class JobManager:
    """Process-wide manager for queued generations."""

    def __init__(self, library: Library, max_workers: int = 3) -> None:
        self.library = library
        self.jobs_path = library.home / "jobs.json"
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="vertigo-job"
        )
        self._load()
        self._resume_active()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        path = self.jobs_path
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        records = data.get("jobs", []) if isinstance(data, dict) else data
        for record in records:
            try:
                job = Job.from_dict(record)
            except (TypeError, ValueError):
                continue
            self._jobs[job.id] = job

    def _persist_locked(self) -> None:
        payload = {
            "version": 1,
            "updated_at": _now(),
            "jobs": [j.to_dict() for j in self._jobs.values()],
        }
        self.library.ensure_dirs()
        tmp = self.jobs_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self.jobs_path)

    # -- reads ------------------------------------------------------------- #
    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, job_ids: list[str] | None = None) -> list[Job]:
        with self._lock:
            if job_ids is None:
                jobs = list(self._jobs.values())
            else:
                jobs = [self._jobs[j] for j in job_ids if j in self._jobs]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def is_active(self, job_id: str) -> bool:
        job = self.get(job_id)
        return bool(job and job.active)

    def active_jobs(self, job_ids: list[str] | None = None) -> list[Job]:
        return [j for j in self.list_jobs(job_ids) if j.active]

    def counts(self) -> dict[str, int]:
        with self._lock:
            jobs = list(self._jobs.values())
        result = {"total": len(jobs), "active": 0}
        for job in jobs:
            if job.active:
                result["active"] += 1
        return result

    def clear_finished(self, job_ids: list[str] | None = None) -> int:
        with self._lock:
            ids = [
                j.id
                for j in self._jobs.values()
                if not j.active and (job_ids is None or j.id in job_ids)
            ]
            for job_id in ids:
                self._jobs.pop(job_id, None)
            if ids:
                self._persist_locked()
        return len(ids)

    # -- writes ------------------------------------------------------------ #
    def submit(
        self,
        *,
        kind: str,
        label: str,
        endpoint: str,
        arguments: dict[str, Any],
        save_kind: str,
        parent_id: str | None = None,
    ) -> str:
        job = Job(
            id=uuid.uuid4().hex[:12],
            kind=kind,
            label=label,
            endpoint=endpoint,
            arguments=arguments,
            save_kind=save_kind,
            parent_id=parent_id,
            status="queued",
        )
        with self._lock:
            self._jobs[job.id] = job
            self._persist_locked()
        self._executor.submit(self._run, job.id)
        return job.id

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or not job.active:
            return False
        if job.request_id:
            fal.cancel(job.endpoint, job.request_id)
        self._update(job_id, status="cancelled", finished_at=_now())
        return True

    # -- internals --------------------------------------------------------- #
    def _update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for key, value in fields.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = _now()
            self._persist_locked()

    def _append_logs(self, job_id: str, messages: list[str]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            for message in messages:
                if message and (not job.logs or job.logs[-1] != message):
                    job.logs.append(message)
            job.logs = job.logs[-300:]
            job.updated_at = _now()
            self._persist_locked()

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return
        self._update(job_id, status="running", started_at=_now())

        def on_enqueue(request_id: str) -> None:
            self._update(job_id, request_id=request_id)

        def on_queue_update(update: Any) -> None:
            if isinstance(update, fal_client.InProgress):
                messages = [
                    str(log.get("message", ""))
                    for log in (update.logs or [])
                    if log.get("message")
                ]
                if messages:
                    self._append_logs(job_id, messages)

        try:
            result = fal.subscribe(
                job.endpoint,
                job.arguments,
                on_enqueue=on_enqueue,
                on_queue_update=on_queue_update,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the user
            self._fail(job_id, exc)
            return
        self._finish(job_id, result)

    def _resume_active(self) -> None:
        with self._lock:
            pending = [j.id for j in self._jobs.values() if j.active]
        for job_id in pending:
            self._executor.submit(self._resume_one, job_id)

    def _resume_one(self, job_id: str) -> None:
        job = self.get(job_id)
        if job is None or not job.active:
            return
        if not job.request_id:
            self._run(job_id)
            return

        self._update(job_id, status="running")
        try:
            while True:
                if (self.get(job_id) or job).status == "cancelled":
                    return
                state = fal.status(job.endpoint, job.request_id)
                if isinstance(state, fal_client.Completed):
                    if getattr(state, "error", None):
                        raise RuntimeError(state.error)
                    result = fal.result(job.endpoint, job.request_id)
                    self._finish(job_id, result)
                    return
                time.sleep(2.0)
        except Exception as exc:  # noqa: BLE001
            self._fail(job_id, exc)

    def _fail(self, job_id: str, exc: Exception) -> None:
        job = self.get(job_id)
        if job is not None and job.status == "cancelled":
            return
        message = fal.redact(f"{type(exc).__name__}: {exc}")
        self._update(job_id, status="failed", error=message, finished_at=_now())

    def _finish(self, job_id: str, result: Any) -> None:
        job = self.get(job_id)
        if job is None or job.status == "cancelled":
            return
        try:
            asset_ids, summary = self._save_result(job, result)
        except Exception as exc:  # noqa: BLE001 - saving can fail independently
            self._fail(job_id, exc)
            return
        self._update(
            job_id,
            status="completed",
            asset_ids=asset_ids,
            summary=summary,
            finished_at=_now(),
        )

    # -- result -> library ------------------------------------------------- #
    def _save_result(self, job: Job, result: Any) -> tuple[list[str], str]:
        data = result if isinstance(result, dict) else {}
        asset_ids: list[str] = []
        summary = ""

        if job.save_kind == SAVE_IMAGES:
            images = data.get("images") or []
            for index, item in enumerate(images):
                asset_id = self._save_remote(job, item, index=index)
                if asset_id:
                    asset_ids.append(asset_id)
            summary = str(data.get("description") or "")
        elif job.save_kind == SAVE_IMAGE:
            asset_id = self._save_remote(job, data.get("image"), index=0)
            if asset_id:
                asset_ids.append(asset_id)
        elif job.save_kind == SAVE_AUDIO:
            asset_id = self._save_remote(job, data.get("audio"), index=0)
            if asset_id:
                asset_ids.append(asset_id)
        elif job.save_kind == SAVE_TRANSCRIPT:
            asset_id = self._save_transcript(job, data)
            if asset_id:
                asset_ids.append(asset_id)
            summary = str(data.get("language_code") or "")

        if not asset_ids:
            raise RuntimeError("The model finished but returned no usable output.")
        return asset_ids, summary

    def _save_remote(self, job: Job, item: Any, *, index: int) -> str | None:
        if not item:
            return None
        if isinstance(item, str):
            item = {"url": item}
        url = item.get("url")
        if not url:
            return None

        media_type = item.get("content_type") or item.get("mime_type") or ""
        fallback_name = Path(urlparse(url).path).name or f"{job.label}-{index + 1}"
        name = item.get("file_name") or fallback_name
        if not media_type:
            media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"

        data = fal.download_bytes(url)
        kind = _kind_for(job, media_type, name)
        meta = {
            "job_id": job.id,
            "request_id": job.request_id,
            "category": job.kind,
            "width": item.get("width"),
            "height": item.get("height"),
        }
        meta = {k: v for k, v in meta.items() if v is not None}

        asset = self.library.add_file(
            data,
            kind=kind,
            name=name,
            origin=config.ORIGIN_GENERATED,
            media_type=media_type,
            prompt=str(job.arguments.get("prompt", "")),
            endpoint=job.endpoint,
            parent_id=job.parent_id,
            remote_url=url,
            meta=meta,
        )
        return asset.id

    def _save_transcript(self, job: Job, data: dict[str, Any]) -> str | None:
        text = str(data.get("text") or "").strip()
        if not text:
            return None
        words = data.get("words") or []
        try:
            words = list(words)[:50000]
        except TypeError:
            words = []
        meta = {
            "job_id": job.id,
            "request_id": job.request_id,
            "category": job.kind,
            "language_code": data.get("language_code"),
            "language_probability": data.get("language_probability"),
            "word_count": len([w for w in words if isinstance(w, dict) and w.get("type") == "word"]),
            "words": words,
        }
        if job.parent_id:
            source = self.library.get(job.parent_id)
            if source is not None:
                meta["audio_name"] = source.name

        asset = self.library.add_file(
            text.encode("utf-8"),
            kind=config.KIND_TEXT,
            name=f"Transcript — {job.label}.txt",
            origin=config.ORIGIN_GENERATED,
            media_type="text/plain; charset=utf-8",
            endpoint=job.endpoint,
            meta={k: v for k, v in meta.items() if v is not None},
        )
        return asset.id


def _kind_for(job: Job, media_type: str, name: str) -> str:
    media = (media_type or "").split(";")[0].strip().lower()
    if media == "image/svg+xml" or name.lower().endswith(".svg"):
        return config.KIND_VECTOR
    if job.kind == "vector":
        return config.KIND_VECTOR
    if media.startswith("audio/"):
        return config.KIND_AUDIO
    if media.startswith("image/"):
        return config.KIND_IMAGE
    return config.KIND_IMAGE


_managers: dict[str, JobManager] = {}
_managers_lock = threading.Lock()


def get_manager(user_id: str) -> JobManager:
    """Return the job manager for a profile, creating it on first use."""
    with _managers_lock:
        manager = _managers.get(user_id)
        if manager is None:
            manager = JobManager(get_library(user_id))
            _managers[user_id] = manager
        return manager


def drop_manager(user_id: str) -> None:
    """Forget a cached job manager (used when a profile is deleted)."""
    with _managers_lock:
        _managers.pop(user_id, None)

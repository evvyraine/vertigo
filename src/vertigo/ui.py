"""Shared Streamlit UI helpers used across the Vertigo pages."""

from __future__ import annotations

import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from typing import Any, Iterable

import streamlit as st

from . import auth, config, fal, i18n
from .jobs import Job, JobManager, get_manager, status_color, status_icon
from .store import Asset, Library, get_library


# --------------------------------------------------------------------------- #
# Cookie bridge
# --------------------------------------------------------------------------- #

# `st.html` content is not iframed, so a small script runs on the app origin
# where it can write `document.cookie`. Values are read back through
# `st.context.cookies` on the next full page load.
_COOKIE_SCRIPT = """
(function () {
  const items = %s;
  for (const p of items) {
    if (p.value === null || p.value === undefined || p.value === "") {
      document.cookie = p.name + "=; path=/; max-age=0; SameSite=Lax";
    } else {
      document.cookie =
        p.name + "=" + encodeURIComponent(p.value) +
        "; path=/; max-age=" + (p.maxAge || 0) + "; SameSite=Lax";
    }
  }
})();
"""


def read_cookie(name: str) -> str | None:
    """Read a cookie from the initial request."""
    try:
        value = st.context.cookies.get(name)
    except Exception:
        return None
    return value if isinstance(value, str) and value else None


def queue_cookie(name: str, value: str, max_age: int = 0) -> None:
    pending = st.session_state.setdefault("_cookie_queue", [])
    pending.append({"name": name, "value": value, "maxAge": max_age})


def cookie_token() -> str | None:
    """Read the remember-me token from the initial request's cookies."""
    return read_cookie(auth.COOKIE_NAME)


def remember_session(user_id: str) -> None:
    """Queue a remember-me cookie for the signed-in profile."""
    token = auth.create_session(user_id)
    # Keep the token in session state too: the cookie is only readable from the
    # initial request, not from subsequent WebSocket reruns.
    st.session_state["_session_token"] = token
    queue_cookie(auth.COOKIE_NAME, token, auth.SESSION_DAYS * 86_400)


def forget_session_cookie() -> None:
    """Revoke the current token server-side and queue a cookie clear."""
    token = st.session_state.pop("_session_token", None) or cookie_token()
    if token:
        auth.revoke_session(token)
    queue_cookie(auth.COOKIE_NAME, "", 0)


def render_cookie_bridge() -> None:
    """Apply queued cookie writes, if any (fire-and-forget script)."""
    pending = st.session_state.pop("_cookie_queue", None)
    if not pending:
        return
    encoded = json.dumps(pending).replace("</", "<\\/")
    st.html(
        f"<script>{_COOKIE_SCRIPT % encoded}</script>",
        unsafe_allow_javascript=True,
    )


# --------------------------------------------------------------------------- #
# Language
# --------------------------------------------------------------------------- #


def current_language() -> str:
    """Resolve the interface language: explicit choice → profile → cookie → browser."""
    chosen = st.session_state.get("lang")
    if chosen:
        return i18n.normalize(chosen)

    user_id = st.session_state.get("user_id")
    if user_id:
        user = auth.get_user(user_id)
        if user and user.locale:
            return i18n.normalize(user.locale)

    from_cookie = read_cookie(i18n.LANG_COOKIE)
    if from_cookie:
        return i18n.normalize(from_cookie)

    try:
        return i18n.normalize(st.context.locale)
    except Exception:
        return i18n.DEFAULT_LANGUAGE


def set_language(code: str) -> None:
    """Switch language, persist it to the profile and cookie, and rerun."""
    clean = i18n.normalize(code)
    st.session_state["lang"] = clean
    i18n.set_language(clean)
    user_id = st.session_state.get("user_id")
    if user_id:
        auth.set_locale(user_id, clean)
    queue_cookie(i18n.LANG_COOKIE, clean, 365 * 86_400)
    st.rerun()


def language_switch(label: str | None = None) -> None:
    """Compact language picker. The widget key changes with the language so it
    always reflects the resolved value without stale session state."""
    current = i18n.get_language()
    choice = st.segmented_control(
        label or i18n.t("language.label"),
        options=list(i18n.LANGUAGES),
        default=current,
        format_func=i18n.language_label,
        key=f"lang_switch_{current}",
        label_visibility="collapsed" if label == "" else "visible",
    )
    if choice and choice != current:
        set_language(choice)


# --------------------------------------------------------------------------- #
# Profile scope
# --------------------------------------------------------------------------- #


def current_user_id() -> str:
    """Return the signed-in profile id, stopping the page if there is none."""
    user_id = st.session_state.get("user_id")
    if not user_id:
        st.error(i18n.t("error.not_signed_in"), icon=":material/lock:")
        st.stop()
    return user_id


def current_library() -> Library:
    """The media library belonging to the signed-in profile."""
    return get_library(current_user_id())


def current_manager() -> JobManager:
    """The generation queue belonging to the signed-in profile."""
    return get_manager(current_user_id())


_PROFILE_MEDIA_KEYS = ("studio_refs", "studio_jobs", "enhance_jobs", "speech_jobs")
_PROFILE_UPLOAD_KEYS = (
    "studio_upload_index",
    "studio_trace_source_index",
    "rmbg_source_index",
    "upscale_source_index",
    "stt_source_index",
)
_PROFILE_TRANSIENT_KEYS = (
    "delete_asset_ids",
    "wipe_assets",
    "remove_user_id",
    "_clear_library_selection",
    "library_table",
    "lib_page",
)


def reset_profile_session() -> None:
    """Drop per-profile selections so nothing leaks across a profile switch."""
    for key in _PROFILE_MEDIA_KEYS:
        st.session_state[key] = []
    for key in _PROFILE_UPLOAD_KEYS:
        st.session_state[key] = {}
    for key in _PROFILE_TRANSIENT_KEYS:
        st.session_state.pop(key, None)


# --------------------------------------------------------------------------- #
# Formatting
# --------------------------------------------------------------------------- #


def humanize_bytes(size: int) -> str:
    if not size:
        return "—"
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def relative_time(iso: str) -> str:
    try:
        moment = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or ""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - moment).total_seconds()
    if seconds < 45:
        return i18n.t("time.just_now")
    if seconds < 3600:
        return i18n.t("time.min_ago", n=int(seconds // 60))
    if seconds < 86400:
        return i18n.t("time.hours_ago", n=int(seconds // 3600))
    if seconds < 604800:
        return i18n.t("time.days_ago", n=int(seconds // 86400))
    return moment.strftime(i18n.t("time.date_format"))


def srt_from_words(words: Iterable[dict[str, Any]]) -> str:
    """Build a SubRip subtitle file from word timings when available."""

    def stamp(seconds: float) -> str:
        millis = int(round((seconds % 1) * 1000))
        total = int(seconds)
        return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d},{millis:03d}"

    lines: list[str] = []
    current: list[str] = []
    start: float | None = None
    last_end = 0.0

    def flush(index: int) -> None:
        nonlocal current, start
        if current and start is not None:
            text = " ".join(current).strip()
            if text:
                lines.append(f"{index}\n{stamp(start)} --> {stamp(last_end)}\n{text}\n")
        current = []
        start = None

    index = 1
    for word in words:
        if not isinstance(word, dict):
            continue
        text = str(word.get("text") or "")
        if word.get("type") == "spacing" or not text.strip():
            continue
        if start is None:
            start = float(word.get("start") or 0)
        current.append(text.strip())
        last_end = float(word.get("end") or last_end)
        if len(" ".join(current)) >= 42 or text.rstrip().endswith((".", "!", "?")):
            flush(index)
            index += 1
    flush(index)
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# API key state
# --------------------------------------------------------------------------- #


def key_ready(*, inline: bool = True) -> bool:
    """Return True when a fal key is available, otherwise show guidance."""
    if fal.has_key():
        return True
    if not inline:
        return False
    st.warning(
        i18n.t("error.no_key_inline", url=config.FAL_DASHBOARD_URL),
        icon=":material/key:",
    )
    try:
        st.page_link(
            "app_pages/settings.py",
            label=i18n.t("common.open_settings"),
            icon=":material/settings:",
        )
    except Exception:  # pragma: no cover - navigation fallback
        st.caption(i18n.t("common.open_settings"))
    return False


# --------------------------------------------------------------------------- #
# Asset rendering
# --------------------------------------------------------------------------- #


THUMB_SIZE = (96, 96)


@st.cache_data(show_spinner=False, max_entries=1024)
def _thumbnail_data_url(path: str, is_svg: bool, size: int) -> str | None:
    """Small inline preview for a visual asset.

    ``ImageColumn`` needs a URL or data URL (local paths aren't supported), so
    images are downscaled with Pillow and base64-encoded. Cached by path+size.
    """
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    except OSError:
        return None

    if is_svg:
        return "data:image/svg+xml;base64," + base64.b64encode(data).decode("ascii")

    try:
        from PIL import Image
    except Exception:  # pragma: no cover - Pillow ships with Streamlit
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.thumbnail(THUMB_SIZE)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")
            buffer = io.BytesIO()
            image.save(buffer, format="WEBP", quality=72, method=4)
    except Exception:  # noqa: BLE001 - an unreadable image shouldn't break the page
        return None
    return "data:image/webp;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def thumbnail_data_url(asset: Asset, library: Library) -> str | None:
    """A data-URL thumbnail for a visual asset, or None."""
    if not asset.is_visual:
        return None
    return _thumbnail_data_url(str(library.file_path(asset)), asset.is_svg, asset.size)


def asset_image(asset: Asset, library: Library, *, width: "int | str" = "stretch") -> None:
    """Render a visual asset, handling SVG and raster images alike."""
    if asset.kind == config.KIND_TEXT:
        st.text(library.text_of(asset)[:6000])
        return
    path = library.file_path(asset)
    if not path or not path.exists():
        st.caption(i18n.t("error.missing_file"))
        return
    if asset.is_svg:
        try:
            st.image(path.read_text(encoding="utf-8"), width=width)
        except (OSError, UnicodeDecodeError):
            st.caption(i18n.t("error.render_svg"))
    else:
        st.image(str(path), width=width)


def asset_media(asset: Asset, library: Library) -> bytes:
    return library.bytes_of(asset)


def download_asset_button(
    asset: Asset,
    library: Library,
    *,
    key: str,
    label: str | None = None,
    type: str = "secondary",
) -> None:
    data = library.bytes_of(asset)
    if not data:
        return
    name = asset.name
    if asset.is_svg and not name.lower().endswith(".svg"):
        name = f"{name}.svg"
    st.download_button(
        label or i18n.t("common.download"),
        data=data,
        file_name=name,
        mime=asset.media_type or "application/octet-stream",
        key=key,
        icon=":material/download:",
        type=type,
    )


def asset_caption(asset: Asset) -> str:
    bits = [relative_time(asset.created_at)]
    if asset.meta.get("width") and asset.meta.get("height"):
        bits.append(f"{asset.meta['width']}×{asset.meta['height']}")
    elif asset.size:
        bits.append(humanize_bytes(asset.size))
    return " · ".join(bits)


def asset_grid(
    assets: list[Asset],
    library: Library,
    *,
    columns: int = 3,
    empty_message: str | None = None,
) -> None:
    if not assets:
        st.caption(empty_message or i18n.t("common.asset_empty"))
        return
    grid = st.columns(columns, gap="small", wrap=False)
    for index, asset in enumerate(assets):
        with grid[index % columns]:
            with st.container(border=True, height="stretch"):
                asset_image(asset, library)
                st.caption(asset.name)
                st.caption(asset_caption(asset))


# --------------------------------------------------------------------------- #
# Uploads & pickers
# --------------------------------------------------------------------------- #


def ingest_uploads(
    uploaded: Any, *, index_key: str, origin: str, kind: str = config.KIND_IMAGE
) -> list[str]:
    """Persist uploaded files, de-duplicating them across reruns."""
    processed: dict[str, str] = st.session_state.setdefault(index_key, {})
    library = current_library()
    if uploaded is None:
        files: list[Any] = []
    elif isinstance(uploaded, list):
        files = uploaded
    else:
        files = [uploaded]

    new_ids: list[str] = []
    for file in files:
        data = file.getvalue()
        digest = hashlib.sha1(data).hexdigest()
        existing = processed.get(digest)
        if existing and library.get(existing):
            continue
        asset = library.add_file(
            data,
            kind=kind,
            name=file.name,
            origin=origin,
            media_type=getattr(file, "type", "") or "application/octet-stream",
            meta={"uploaded": True},
        )
        processed[digest] = asset.id
        new_ids.append(asset.id)
    return new_ids


def _library_choices(library: Library, kinds: Iterable[str]) -> dict[str, str]:
    assets = library.newest_first(library.filter(kinds=kinds))
    return {f"{a.name} · {relative_time(a.created_at)}": a.id for a in assets}


def image_picker(library: Library, *, key: str, label: str | None = None, kinds=None) -> Asset | None:
    """A single-image picker combining an uploader and the library."""
    kinds = kinds or [config.KIND_IMAGE]
    uploaded = st.file_uploader(
        label or i18n.t("common.source_image"),
        type=config.IMAGE_UPLOAD_TYPES,
        key=f"{key}_upload",
    )
    new_ids = ingest_uploads(
        uploaded, index_key=f"{key}_index", origin=config.ORIGIN_REFERENCE
    )
    options = _library_choices(library, kinds)
    if not options:
        st.caption(i18n.t("common.upload_image_hint"))
        return None
    if new_ids and new_ids[0] in options.values():
        st.session_state[key] = next(k for k, v in options.items() if v == new_ids[0])
    choice = st.selectbox(i18n.t("common.choose_from_library"), list(options), key=key)
    return library.get(options[choice])


def audio_picker(library: Library, *, key: str, label: str | None = None) -> Asset | None:
    """A single-audio picker combining an uploader and the library."""
    uploaded = st.file_uploader(
        label or i18n.t("speech.audio"),
        type=config.AUDIO_UPLOAD_TYPES,
        key=f"{key}_upload",
    )
    new_ids = ingest_uploads(
        uploaded,
        index_key=f"{key}_index",
        origin=config.ORIGIN_UPLOADED,
        kind=config.KIND_AUDIO,
    )
    options = _library_choices(library, [config.KIND_AUDIO])
    if not options:
        st.caption(i18n.t("common.upload_audio_hint"))
        return None
    if new_ids and new_ids[0] in options.values():
        st.session_state[key] = next(k for k, v in options.items() if v == new_ids[0])
    choice = st.selectbox(i18n.t("common.choose_from_library"), list(options), key=key)
    return library.get(options[choice])


def transcript_srt(asset: Asset) -> str | None:
    words = asset.meta.get("words")
    if not words:
        return None
    return srt_from_words(words) or None


# --------------------------------------------------------------------------- #
# Job rendering
# --------------------------------------------------------------------------- #


def _render_job(job: Job, library: Library, on_asset: "Any | None" = None) -> None:
    manager = current_manager()
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            st.markdown(f"{status_icon(job.status)} **{job.label}**")
            st.badge(i18n.t(f"status.{job.status}"), color=status_color(job.status))
            st.caption(relative_time(job.created_at))
        st.caption(f"`{job.endpoint}`")

        if job.active:
            st.caption(f":blue[:material/progress_activity:] {i18n.t(f'status.{job.status}')}…")
        elif job.status == "failed":
            st.error(job.error or i18n.t("jobs.failed"), icon=":material/error:")

        if job.logs and job.active:
            with st.expander(i18n.t("common.logs"), icon=":material/terminal:"):
                st.code("\n".join(job.logs[-40:]), language=None)

        if job.status == "completed":
            assets = [a for a in (library.get(i) for i in job.asset_ids) if a]
            if job.summary:
                st.caption(job.summary)

            for asset in assets:
                if asset.kind == config.KIND_AUDIO:
                    st.audio(
                        library.bytes_of(asset),
                        format=asset.media_root or "audio/mpeg",
                    )
                    with st.container(horizontal=True):
                        download_asset_button(asset, library, key=f"jdl_{job.id}_{asset.id}")
                        if on_asset:
                            on_asset(asset, job)

            for asset in assets:
                if asset.kind != config.KIND_TEXT:
                    continue
                st.text_area(
                    i18n.t("common.transcript"),
                    value=library.text_of(asset),
                    height=220,
                    key=f"jtxt_{job.id}_{asset.id}",
                    label_visibility="collapsed",
                )
                with st.container(horizontal=True):
                    download_asset_button(asset, library, key=f"jdl_{job.id}_{asset.id}")
                    srt = transcript_srt(asset)
                    if srt:
                        st.download_button(
                            i18n.t("library.subtitles"),
                            data=srt,
                            file_name=f"{asset.name.rsplit('.', 1)[0]}.srt",
                            mime="text/plain",
                            key=f"jsrt_{job.id}_{asset.id}",
                            icon=":material/subtitles:",
                        )

            visuals = [a for a in assets if a.is_visual]
            if visuals:
                columns = st.columns(min(len(visuals), 4), wrap=False)
                for index, asset in enumerate(visuals):
                    with columns[index % len(columns)]:
                        asset_image(asset, library)
                        with st.container(horizontal=True):
                            download_asset_button(
                                asset, library, key=f"jdl_{job.id}_{asset.id}"
                            )
                        if on_asset:
                            on_asset(asset, job)

        with st.container(horizontal=True):
            if job.active:
                if st.button(
                    i18n.t("jobs.cancel"),
                    key=f"cancel_{job.id}",
                    icon=":material/stop_circle:",
                ):
                    manager.cancel(job.id)
                    st.rerun()
            else:
                if st.button(
                    i18n.t("jobs.dismiss"),
                    key=f"dismiss_{job.id}",
                    icon=":material/close:",
                ):
                    manager.clear_finished([job.id])
                    st.rerun()


def render_jobs(
    job_ids: list[str],
    *,
    title: str | None = None,
    on_asset: "Any | None" = None,
) -> None:
    """Render a list of jobs (newest first) with live output previews."""
    manager = current_manager()
    library = current_library()
    jobs = manager.list_jobs(job_ids)
    if title:
        st.subheader(title, icon=":material/queue:")
    if not jobs:
        st.caption(i18n.t("jobs.none"))
        return
    for job in jobs:
        _render_job(job, library, on_asset)


@st.fragment(run_every=2)
def _live_jobs(job_ids: list[str], title: str | None, on_asset: "Any | None") -> None:
    render_jobs(job_ids, title=title, on_asset=on_asset)
    if not current_manager().active_jobs(job_ids):
        # Everything finished — hand back to a static render.
        st.rerun()


def jobs_panel(
    job_ids: list[str],
    *,
    title: str | None = None,
    on_asset: "Any | None" = None,
) -> None:
    """Auto-refreshing job panel that stops polling once everything settles."""
    if not job_ids:
        return
    resolved = title if title is not None else i18n.t("jobs.session")
    if current_manager().active_jobs(job_ids):
        _live_jobs(job_ids, resolved, on_asset)
    else:
        render_jobs(job_ids, title=resolved, on_asset=on_asset)

"""Library — a sortable, searchable table of every asset.

The library is presented as a dataframe: Streamlit's native table brings
column sorting, full-text search and resizing for free, and an ``ImageColumn``
renders thumbnails inline. Row selections are stable across client-side sorting
(they reference original row positions), so the selection panel can safely
download, reuse or delete the right assets.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from vertigo import config, i18n, ui
from vertigo.store import Asset

library = ui.current_library()

THUMB_LIMIT = 400

KIND_FILTERS: dict[str, list[str] | None] = {
    "all": None,
    "images": [config.KIND_IMAGE],
    "vectors": [config.KIND_VECTOR],
    "audio": [config.KIND_AUDIO],
    "text": [config.KIND_TEXT],
}

ORIGINS: dict[str, list[str] | None] = {
    "all": None,
    "generated": [config.ORIGIN_GENERATED],
    "uploaded": [config.ORIGIN_UPLOADED],
    "references": [config.ORIGIN_REFERENCE],
}


# --------------------------------------------------------------------------- #
# Thumbnails & helpers
# --------------------------------------------------------------------------- #


def _parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _detail_text(asset: Asset) -> str:
    candidates = [asset.prompt, asset.meta.get("description"), asset.meta.get("audio_name")]
    if asset.kind == config.KIND_TEXT:
        text = library.text_of(asset)
        candidates.insert(0, text[:220] + ("…" if len(text) > 220 else ""))
    for candidate in candidates:
        if candidate:
            return str(candidate)
    return ""


def _referenceable(asset: Asset) -> bool:
    return asset.kind in (config.KIND_IMAGE, config.KIND_VECTOR) and not asset.is_svg


def _clear_selection() -> None:
    # Deferred: a widget's session state can't be reassigned after it renders.
    st.session_state["_clear_library_selection"] = True
    st.rerun()


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #


@st.dialog(i18n.t("library.confirm_delete"))
def _confirm_delete(asset_ids: list[str]) -> None:
    assets = [a for a in (library.get(i) for i in asset_ids) if a is not None]
    if not assets:
        st.session_state.pop("delete_asset_ids", None)
        st.rerun()

    if len(assets) == 1:
        st.write(i18n.t("library.delete_single", name=assets[0].name))
    else:
        st.write(i18n.t("library.delete_multi", count=len(assets)))
        st.caption(", ".join(a.name for a in assets[:10]))

    with st.container(horizontal=True):
        if st.button(
            i18n.t("common.delete"),
            type="primary",
            icon=":material/delete:",
            key="confirm_del",
        ):
            for asset in assets:
                library.delete(asset.id)
            st.session_state.pop("delete_asset_ids", None)
            st.session_state["_clear_library_selection"] = True
            st.toast(i18n.t("toast.deleted", count=len(assets)), icon=":material/delete:")
            st.rerun()
        if st.button(i18n.t("common.cancel"), key="cancel_del"):
            st.session_state.pop("delete_asset_ids", None)
            st.rerun()


@st.dialog(i18n.t("library.rename_title"))
def _confirm_rename(asset_id: str) -> None:
    asset = library.get(asset_id)
    if asset is None:
        st.session_state.pop("rename_asset_id", None)
        st.rerun()
    assert asset is not None
    new_name = st.text_input(
        i18n.t("library.rename_label"), value=asset.name, key="rename_input"
    )
    with st.container(horizontal=True):
        if st.button(
            i18n.t("common.save"),
            type="primary",
            icon=":material/save:",
            key="rename_save",
        ):
            clean = new_name.strip()
            if clean:
                if not Path(clean).suffix:
                    clean = f"{clean}{Path(asset.name).suffix}"
                library.update(asset_id, name=clean)
                st.session_state.pop("rename_asset_id", None)
                st.toast(i18n.t("toast.renamed", name=clean), icon=":material/check_circle:")
                st.rerun()
        if st.button(i18n.t("common.cancel"), key="rename_cancel"):
            st.session_state.pop("rename_asset_id", None)
            st.rerun()


def _add_references(assets: list[Asset]) -> None:
    refs = st.session_state.setdefault("studio_refs", [])
    added = 0
    for asset in assets:
        if _referenceable(asset) and asset.id not in refs:
            refs.append(asset.id)
            added += 1
    if added:
        st.toast(i18n.t("toast.ref_added", count=added), icon=":material/edit_note:")
        _clear_selection()
    else:
        st.toast(i18n.t("toast.ref_nothing"), icon=":material/info:")


# --------------------------------------------------------------------------- #
# Selection panel
# --------------------------------------------------------------------------- #


def _render_single(asset: Asset) -> None:
    with st.container(border=True):
        preview, meta = st.columns([1, 1], gap="large")

        with preview:
            if asset.kind == config.KIND_AUDIO:
                st.audio(library.bytes_of(asset), format=asset.media_root or "audio/mpeg")
            elif asset.kind == config.KIND_TEXT:
                st.text_area(
                    i18n.t("common.transcript"),
                    value=library.text_of(asset),
                    height=240,
                    key=f"lib_text_{asset.id}",
                    label_visibility="collapsed",
                )
            else:
                ui.asset_image(asset, library)

        with meta:
            st.markdown(f"**{asset.name}**")
            st.caption(ui.asset_caption(asset))
            details = {
                i18n.t("metadata.kind"): i18n.t(f"kind.{asset.kind}"),
                i18n.t("metadata.source"): i18n.t(f"origin.{asset.origin}"),
                i18n.t("metadata.media_type"): asset.media_type or "—",
                i18n.t("metadata.size"): ui.humanize_bytes(asset.size),
                i18n.t("metadata.created"): asset.created_at,
                i18n.t("metadata.model"): asset.endpoint or "—",
            }
            st.write(details)
            if asset.prompt:
                st.caption(i18n.t("library.prompt_prefix", prompt=asset.prompt))

            with st.container(horizontal=True):
                ui.download_asset_button(asset, library, key=f"lib_dl_{asset.id}")
                if _referenceable(asset):
                    if st.button(
                        i18n.t("library.reference"),
                        key=f"lib_ref_{asset.id}",
                        icon=":material/edit_note:",
                    ):
                        _add_references([asset])
                if st.button(
                    i18n.t("library.rename"),
                    key=f"lib_rename_{asset.id}",
                    icon=":material/edit:",
                ):
                    st.session_state["rename_asset_id"] = asset.id
                    st.rerun()
                if asset.kind == config.KIND_TEXT:
                    srt = ui.transcript_srt(asset)
                    if srt:
                        st.download_button(
                            i18n.t("library.subtitles"),
                            data=srt,
                            file_name=f"{asset.name.rsplit('.', 1)[0]}.srt",
                            mime="text/plain",
                            key=f"lib_srt_{asset.id}",
                            icon=":material/subtitles:",
                        )
                if st.button(
                    i18n.t("common.delete"),
                    key=f"lib_del_{asset.id}",
                    icon=":material/delete:",
                ):
                    st.session_state["delete_asset_ids"] = [asset.id]
                    st.rerun()


def _render_many(assets: list[Asset]) -> None:
    with st.container(border=True):
        st.markdown(i18n.t("library.selected_n", count=len(assets)))
        st.caption(", ".join(a.name for a in assets[:12]) + ("…" if len(assets) > 12 else ""))
        referenceable = [a for a in assets if _referenceable(a)]
        with st.container(horizontal=True):
            if st.button(
                i18n.t("library.add_refs", count=len(referenceable)),
                key="lib_bulk_ref",
                icon=":material/edit_note:",
                disabled=not referenceable,
            ):
                _add_references(referenceable)
            if st.button(
                i18n.t("library.delete_n", count=len(assets)),
                key="lib_bulk_del",
                icon=":material/delete:",
            ):
                st.session_state["delete_asset_ids"] = [a.id for a in assets]
                st.rerun()


def _render_selection(selected: list[Asset]) -> None:
    if not selected:
        st.caption(i18n.t("library.select_hint"))
        return
    if len(selected) == 1:
        _render_single(selected[0])
    else:
        _render_many(selected)


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #

if st.session_state.pop("_clear_library_selection", False):
    st.session_state["library_table"] = {"selection": {"rows": []}}

if st.session_state.get("delete_asset_ids"):
    _confirm_delete(st.session_state["delete_asset_ids"])

if st.session_state.get("rename_asset_id"):
    _confirm_rename(st.session_state["rename_asset_id"])

filters = st.columns([2, 1, 2])
with filters[0]:
    kind_choice = st.segmented_control(
        i18n.t("library.column.type"),
        list(KIND_FILTERS),
        default="all",
        format_func=lambda key: i18n.t(f"filter.{key}"),
        key="lib_kind",
    )
with filters[1]:
    origin_choice = st.selectbox(
        i18n.t("library.column.source"),
        list(ORIGINS),
        format_func=lambda key: i18n.t(f"origin_filter.{key}"),
        key="lib_origin",
    )
with filters[2]:
    search = st.text_input(
        i18n.t("library.search"),
        placeholder=i18n.t("library.search_placeholder"),
        key="lib_search",
        icon=":material/search:",
    )

assets = library.newest_first(
    library.filter(
        kinds=KIND_FILTERS.get(kind_choice or "all"),
        origins=ORIGINS.get(origin_choice or "all"),
        search=search,
    )
)

if not assets:
    st.info(i18n.t("library.nothing"), icon=":material/folder_open:")
    st.stop()

rows: list[dict[str, Any]] = []
thumbnails = THUMB_LIMIT
for asset in assets:
    preview = None
    if asset.is_visual and thumbnails > 0:
        preview = ui.thumbnail_data_url(asset, library)
        thumbnails -= 1
    rows.append(
        {
            "Preview": preview,
            "Name": asset.name,
            "Type": i18n.t(f"kind.{asset.kind}"),
            "Source": i18n.t(f"origin.{asset.origin}"),
            "Prompt / content": _detail_text(asset),
            "Model": asset.endpoint or "—",
            "Created": _parse_datetime(asset.created_at),
            "Size": ui.humanize_bytes(asset.size),
        }
    )

st.caption(i18n.t("library.count", count=len(assets)))
state = st.dataframe(
    rows,
    key="library_table",
    hide_index=True,
    height=560,
    on_select="rerun",
    selection_mode="multi-row",
    column_order=("Preview", "Name", "Type", "Created", "Prompt / content", "Size"),
    column_config={
        "Preview": st.column_config.ImageColumn(i18n.t("library.column.preview"), width="small"),
        "Name": st.column_config.TextColumn(i18n.t("library.column.name"), width="medium"),
        "Type": st.column_config.TextColumn(i18n.t("library.column.type"), width="small"),
        "Source": st.column_config.TextColumn(i18n.t("library.column.source"), width="small"),
        "Prompt / content": st.column_config.TextColumn(
            i18n.t("library.column.prompt"), width="large"
        ),
        "Model": st.column_config.TextColumn(i18n.t("library.column.model"), width="medium"),
        "Created": st.column_config.DatetimeColumn(
            i18n.t("library.column.created"),
            width="small",
            format=i18n.t("library.date_format"),
        ),
        "Size": st.column_config.TextColumn(i18n.t("library.column.size"), width="small"),
    },
    placeholder="—",
)

positions = list(state.selection.rows) if state is not None else []
selected = [assets[i] for i in positions if 0 <= i < len(assets)]

st.subheader(i18n.t("library.selection"), icon=":material/checklist:")
_render_selection(selected)

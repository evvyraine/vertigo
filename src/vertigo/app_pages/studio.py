"""Image studio — text-to-image, reference-guided editing and vectorisation."""

from __future__ import annotations

from typing import Any

import streamlit as st

from vertigo import config, fal, i18n, ui
from vertigo.jobs import SAVE_IMAGE, SAVE_IMAGES, Job
from vertigo.store import Asset

library = ui.current_library()
manager = ui.current_manager()

VISUAL_KINDS = [config.KIND_IMAGE, config.KIND_VECTOR]
TAB_GENERATE = "generate"
TAB_VECTOR = "vector"


# --------------------------------------------------------------------------- #
# References
# --------------------------------------------------------------------------- #


def _reference_tray() -> list[str]:
    refs: list[str] = list(st.session_state.studio_refs)

    uploaded = st.file_uploader(
        i18n.t("studio.refs.add"),
        type=config.IMAGE_UPLOAD_TYPES,
        accept_multiple_files=True,
        key="studio_ref_uploader",
        help=i18n.t("studio.refs.help"),
    )
    for asset_id in ui.ingest_uploads(
        uploaded, index_key="studio_upload_index", origin=config.ORIGIN_REFERENCE
    ):
        if asset_id not in refs:
            refs.append(asset_id)

    with st.popover(i18n.t("studio.refs.from_library"), icon=":material/photo_library:"):
        candidates = [
            asset
            for asset in library.newest_first(library.filter(kinds=[config.KIND_IMAGE]))
            if asset.id not in refs
        ][:60]
        if candidates:
            rows = [
                {
                    "Preview": ui.thumbnail_data_url(asset, library),
                    "Name": asset.name,
                    "Added": ui.relative_time(asset.created_at),
                }
                for asset in candidates
            ]
            state = st.dataframe(
                rows,
                key="studio_ref_table",
                hide_index=True,
                height=240,
                on_select="rerun",
                selection_mode="multi-row",
                column_order=("Preview", "Name", "Added"),
                column_config={
                    "Preview": st.column_config.ImageColumn("", width="small"),
                    "Name": st.column_config.TextColumn(
                        i18n.t("library.column.name"), width="medium"
                    ),
                    "Added": st.column_config.TextColumn(
                        i18n.t("library.column.created"), width="small"
                    ),
                },
            )
            if st.button(i18n.t("studio.refs.add_selected"), key="studio_ref_add"):
                picked = list(state.selection.rows) if state is not None else []
                for index in picked:
                    if 0 <= index < len(candidates):
                        refs.append(candidates[index].id)
                st.session_state.studio_refs = refs
                st.rerun()
        else:
            st.caption(i18n.t("studio.refs.none_library"))

    refs = [r for r in refs if library.get(r)]
    st.session_state.studio_refs = refs

    if refs:
        st.caption(i18n.t("studio.refs.count", count=len(refs)))
        columns = st.columns(6, gap="small")
        for index, asset_id in enumerate(list(refs)):
            asset = library.get(asset_id)
            if asset is None:
                continue
            with columns[index % 6]:
                ui.asset_image(asset, library)
                if st.button(
                    i18n.t("studio.refs.remove"),
                    key=f"studio_rm_{asset_id}",
                    icon=":material/close:",
                    label_visibility="collapsed",
                ):
                    st.session_state.studio_refs = [r for r in refs if r != asset_id]
                    st.rerun()
    else:
        st.caption(i18n.t("studio.refs.none"))
    return list(st.session_state.studio_refs)


# --------------------------------------------------------------------------- #
# Generate & edit
# --------------------------------------------------------------------------- #


def _image_arguments(model: dict[str, Any], prompt: str, params: dict[str, Any]) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "prompt": prompt.strip(),
        "num_images": int(params["num_images"]),
    }
    if model["engine"] == "openai":
        arguments.update(
            image_size=params["image_size"],
            quality=params["quality"],
            background=params["background"],
            output_format=params["output_format"],
        )
    else:
        arguments.update(
            aspect_ratio=params["aspect_ratio"],
            resolution=params["resolution"],
            safety_tolerance=params["safety_tolerance"],
            output_format=params["output_format"],
        )
    return arguments


def _image_parameters(model: dict[str, Any]) -> dict[str, Any]:
    """Compact parameter grid (two columns) so the studio fits without scrolling."""
    params: dict[str, Any] = {}
    if model["engine"] == "openai":
        left, right = st.columns(2, gap="small")
        with left:
            size_labels = [label for label, _ in config.GPT_IMAGE_SIZES]
            size_label = st.selectbox(
                i18n.t("param.image_size"),
                size_labels,
                index=0,
                key=f"studio_size_{model['id']}",
            )
            params["image_size"] = dict(config.GPT_IMAGE_SIZES)[size_label]
            params["quality"] = st.selectbox(
                i18n.t("param.quality"),
                config.GPT_QUALITIES,
                index=config.GPT_QUALITIES.index("high"),
                key=f"studio_quality_{model['id']}",
            )
        with right:
            params["background"] = st.selectbox(
                i18n.t("param.background"),
                config.GPT_BACKGROUNDS,
                index=0,
                key=f"studio_bg_{model['id']}",
            )
            params["output_format"] = st.selectbox(
                i18n.t("param.format"),
                config.IMAGE_OUTPUT_FORMATS,
                index=0,
                key=f"studio_fmt_{model['id']}",
            )
    else:
        left, right = st.columns(2, gap="small")
        with left:
            params["aspect_ratio"] = st.selectbox(
                i18n.t("param.aspect_ratio"),
                config.NANO_ASPECT_RATIOS,
                index=0,
                key=f"studio_ar_{model['id']}",
            )
            params["resolution"] = st.selectbox(
                i18n.t("param.resolution"),
                config.NANO_RESOLUTIONS,
                index=config.NANO_RESOLUTIONS.index("1K"),
                key=f"studio_res_{model['id']}",
            )
        with right:
            params["safety_tolerance"] = st.selectbox(
                i18n.t("param.safety"),
                config.SAFETY_TOLERANCES,
                index=config.SAFETY_TOLERANCES.index("4"),
                key=f"studio_safety_{model['id']}",
            )
            params["output_format"] = st.selectbox(
                i18n.t("param.format"),
                config.IMAGE_OUTPUT_FORMATS,
                index=0,
                key=f"studio_fmt_{model['id']}",
            )
    params["num_images"] = st.slider(
        i18n.t("param.images"),
        min_value=1,
        max_value=min(4, int(model["max_images"])),
        value=1,
        key=f"studio_num_{model['id']}",
    )
    return params


def _resolve_references(refs: list[str]) -> tuple[list[str], str | None]:
    urls: list[str] = []
    for asset_id in refs:
        asset = library.get(asset_id)
        if asset is None:
            continue
        try:
            urls.append(fal.ensure_remote_url(asset, library))
        except Exception as exc:  # noqa: BLE001 - surface to the user
            st.error(i18n.t("error.prepare_asset", name=asset.name, error=exc))
            return [], None
    return urls, (refs[0] if urls else None)


def _queue_image(model: dict[str, Any], prompt: str, refs: list[str], params: dict[str, Any]) -> None:
    arguments = _image_arguments(model, prompt, params)
    max_refs = int(model["max_refs"])
    if len(refs) > max_refs:
        st.toast(
            i18n.t("toast.max_refs", model=model["label"], count=max_refs),
            icon=":material/info:",
        )
        refs = refs[:max_refs]
    urls, parent_id = _resolve_references(refs)
    if refs and not urls:
        return  # reference preparation failed
    if urls:
        arguments["image_urls"] = urls
        endpoint = model["edit"]
        label = i18n.t("jobs.label.edit", model=model["label"])
    else:
        endpoint = model["t2i"]
        label = i18n.t("jobs.label.generation", model=model["label"])

    job_id = manager.submit(
        kind="image",
        label=label,
        endpoint=endpoint,
        arguments=arguments,
        save_kind=SAVE_IMAGES,
        parent_id=parent_id,
    )
    st.session_state.studio_jobs.insert(0, job_id)
    st.toast(i18n.t("toast.queued"), icon=":material/queue:")


def _studio_asset_actions(asset: Asset, job: Job) -> None:
    if asset.kind not in VISUAL_KINDS:
        return
    if st.button(
        i18n.t("studio.edit_reuse"),
        key=f"studio_edit_{job.id}_{asset.id}",
        icon=":material/edit_note:",
        help=i18n.t("studio.edit_reuse_help"),
    ):
        current = [r for r in st.session_state.studio_refs if r != asset.id]
        st.session_state.studio_refs = [asset.id, *current]
        st.toast(i18n.t("toast.base_added"), icon=":material/edit_note:")
        st.rerun()


def _render_generate() -> None:
    left, right = st.columns([2, 3], gap="large")

    with left:
        model_id = st.selectbox(
            i18n.t("studio.model"),
            [m["id"] for m in config.IMAGE_MODELS],
            format_func=lambda value: config.model_by_id(value)["label"],
            key="studio_model",
            help="\n\n".join(
                i18n.t(f"models.{m['id']}.tagline") for m in config.IMAGE_MODELS
            ),
        )
        model = config.model_by_id(model_id)

        prompt = st.text_area(
            i18n.t("studio.prompt"),
            height=100,
            key="studio_prompt",
            placeholder=i18n.t("studio.prompt_placeholder"),
        )
        refs = _reference_tray()

        with st.expander(i18n.t("studio.parameters"), expanded=False):
            params = _image_parameters(model)
            endpoint = model["edit"] if refs else model["t2i"]
            st.caption(i18n.t(f"models.{model['id']}.pricing"))
            st.caption(i18n.t("studio.endpoint_edit", endpoint=endpoint))

        ready = fal.has_key() and bool(prompt.strip())
        if st.button(
            i18n.t("studio.generate"),
            type="primary",
            icon=":material/auto_awesome:",
            disabled=not ready,
            key="studio_generate",
        ):
            _queue_image(model, prompt, refs, params)

    with right:
        ui.jobs_panel(
            st.session_state.studio_jobs,
            on_asset=_studio_asset_actions,
        )


# --------------------------------------------------------------------------- #
# Vectors
# --------------------------------------------------------------------------- #


def _render_vectors() -> None:
    mode = st.segmented_control(
        i18n.t("studio.vector.mode"),
        ["generate", "trace"],
        default="generate",
        format_func=lambda value: i18n.t(f"studio.vector.{value}_mode"),
        key="studio_vector_mode",
    )
    left, right = st.columns([2, 3], gap="large")

    with left:
        if mode == "trace":
            st.caption(i18n.t("studio.vector.trace_help"))
            asset = ui.image_picker(
                library, key="studio_trace_source", label=i18n.t("studio.vector.image_to_trace")
            )
            if st.button(
                i18n.t("studio.vector.trace"),
                type="primary",
                icon=":material/polyline:",
                disabled=not (fal.has_key() and asset),
                key="studio_trace_go",
            ):
                if asset is not None:
                    try:
                        url = fal.ensure_remote_url(asset, library)
                    except Exception as exc:  # noqa: BLE001
                        st.error(i18n.t("error.prepare_asset", name=asset.name, error=exc))
                    else:
                        job_id = manager.submit(
                            kind="vector",
                            label=i18n.t("jobs.label.vectorize", name=asset.name),
                            endpoint=config.VECTOR_ENDPOINT_TRACE,
                            arguments={"image_url": url},
                            save_kind=SAVE_IMAGE,
                            parent_id=asset.id,
                        )
                        st.session_state.studio_jobs.insert(0, job_id)
                        st.toast(i18n.t("toast.tracing"), icon=":material/queue:")
        else:
            prompt = st.text_area(
                i18n.t("studio.prompt"),
                height=100,
                key="studio_vector_prompt",
                placeholder=i18n.t("studio.prompt_placeholder"),
            )
            style_labels = [label for label, _ in config.VECTOR_STYLES]
            style_label = st.selectbox(
                i18n.t("studio.vector.style"), style_labels, key="studio_vector_style"
            )
            size_labels = list(config.VECTOR_SIZE_MAP)
            size_label = st.selectbox(
                i18n.t("studio.vector.size"),
                size_labels,
                index=size_labels.index("Square (1024²)"),
                key="studio_vector_size",
            )
            st.caption(i18n.t("studio.vector.generate_caption"))
            st.caption(i18n.t("studio.vector.pricing"))
            if st.button(
                i18n.t("studio.vector.generate"),
                type="primary",
                icon=":material/polyline:",
                disabled=not (fal.has_key() and prompt.strip()),
                key="studio_vector_go",
            ):
                job_id = manager.submit(
                    kind="vector",
                    label=i18n.t("jobs.label.vector"),
                    endpoint=config.VECTOR_ENDPOINT_T2V,
                    arguments={
                        "prompt": prompt.strip(),
                        "style": dict(config.VECTOR_STYLES)[style_label],
                        "image_size": config.VECTOR_SIZE_MAP[size_label],
                    },
                    save_kind=SAVE_IMAGES,
                )
                st.session_state.studio_jobs.insert(0, job_id)
                st.toast(i18n.t("toast.queued_vector"), icon=":material/queue:")

    with right:
        ui.jobs_panel(
            st.session_state.studio_jobs,
            title=i18n.t("studio.vector.jobs"),
            on_asset=_studio_asset_actions,
        )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #

ui.key_ready()

mode = st.segmented_control(
    "studio_mode",
    [TAB_GENERATE, TAB_VECTOR],
    default=TAB_GENERATE,
    format_func=lambda value: i18n.t(f"studio.mode_{value}"),
    key="studio_mode",
    label_visibility="collapsed",
)

if mode == TAB_VECTOR:
    _render_vectors()
else:
    _render_generate()

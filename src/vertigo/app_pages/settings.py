"""Settings — profile, fal connection, data and family profiles."""

from __future__ import annotations

import streamlit as st

from vertigo import auth, config, fal, i18n, ui
from vertigo.store import get_library

library = ui.current_library()
manager = ui.current_manager()
user = auth.get_user(ui.current_user_id())
is_admin = bool(user and user.is_admin)


@st.dialog(i18n.t("settings.delete_all"))
def _confirm_wipe() -> None:
    st.write(i18n.t("settings.wipe_caption"))
    confirm = st.text_input(i18n.t("settings.wipe_confirm"), key="wipe_confirm")
    with st.container(horizontal=True):
        if st.button(
            i18n.t("settings.delete_all"),
            type="primary",
            icon=":material/delete_forever:",
            disabled=confirm.strip().upper() != "DELETE",
            key="wipe_go",
        ):
            library.clear(keep_references=False)
            st.session_state.pop("wipe_assets", None)
            st.toast(i18n.t("toast.wiped"), icon=":material/delete_forever:")
            st.rerun()
        if st.button(i18n.t("common.cancel"), key="wipe_cancel"):
            st.session_state.pop("wipe_assets", None)
            st.rerun()


@st.dialog(i18n.t("settings.remove_profile_title"))
def _confirm_remove(user_id: str) -> None:
    target = auth.get_user(user_id)
    if target is None:
        st.session_state.pop("remove_user_id", None)
        st.rerun()
    assert target is not None
    st.write(i18n.t("settings.remove_profile_body", name=target.name))
    remove_data = st.checkbox(i18n.t("settings.remove_profile_data"), value=True)
    with st.container(horizontal=True):
        if st.button(
            i18n.t("settings.remove_profile"),
            type="primary",
            icon=":material/delete:",
            key="remove_user_go",
        ):
            try:
                auth.delete_user(user_id, remove_data=remove_data)
            except auth.AuthError as exc:
                st.error(auth.error_text(exc))
            else:
                st.session_state.pop("remove_user_id", None)
                st.toast(i18n.t("toast.profile_removed"), icon=":material/delete:")
                st.rerun()
        if st.button(i18n.t("common.cancel"), key="remove_user_cancel"):
            st.session_state.pop("remove_user_id", None)
            st.rerun()


if st.session_state.get("wipe_assets"):
    _confirm_wipe()

if st.session_state.get("remove_user_id"):
    _confirm_remove(st.session_state["remove_user_id"])


# --------------------------------------------------------------------------- #
# Profile
# --------------------------------------------------------------------------- #


def _render_profile() -> None:
    with st.container(border=True):
        info, actions = st.columns([2, 3], vertical_alignment="center")
        with info:
            badges = []
            if is_admin:
                badges.append(f":blue-badge[{i18n.t('settings.admin')}]")
            if user.must_change_pin:
                badges.append(f":orange-badge[{i18n.t('settings.badge_default_pin')}]")
            st.markdown(f"**{user.name}** " + " ".join(badges))
            st.caption(f"`{user.id}`")

        name_column, pin_column, out_column = actions.columns(3, gap="small")

        with name_column, st.popover(
            i18n.t("settings.edit_name"),
            icon=":material/edit:",
            width="stretch",
        ):
            with st.form("profile_name_form", border=False):
                new_name = st.text_input(
                    i18n.t("settings.display_name"), value=user.name
                )
                if st.form_submit_button(
                    i18n.t("settings.save_name"),
                    icon=":material/save:",
                    type="primary",
                    width="stretch",
                ):
                    try:
                        auth.rename_user(user.id, new_name)
                    except auth.AuthError as exc:
                        st.error(auth.error_text(exc))
                    else:
                        st.session_state["user_name"] = new_name.strip()
                        st.toast(
                            i18n.t("toast.name_updated"), icon=":material/check_circle:"
                        )
                        st.rerun()

        with pin_column, st.popover(
            i18n.t("settings.edit_pin"),
            icon=":material/key:",
            width="stretch",
        ):
            with st.form("profile_pin_form", clear_on_submit=True, border=False):
                current_pin = st.text_input(i18n.t("settings.current_pin"), type="password")
                new_pin = st.text_input(i18n.t("settings.new_pin"), type="password")
                confirm_pin = st.text_input(i18n.t("settings.confirm_pin"), type="password")
                if st.form_submit_button(
                    i18n.t("settings.change_pin"),
                    icon=":material/key:",
                    type="primary",
                    width="stretch",
                ):
                    if not auth.authenticate(user.id, current_pin):
                        st.error(i18n.t("settings.pin_wrong"))
                    elif new_pin != confirm_pin:
                        st.error(i18n.t("settings.pin_mismatch"))
                    else:
                        try:
                            auth.set_pin(user.id, new_pin)
                        except auth.AuthError as exc:
                            st.error(auth.error_text(exc))
                        else:
                            st.toast(
                                i18n.t("toast.pin_updated"),
                                icon=":material/check_circle:",
                            )
                            st.rerun()

        with out_column:
            if st.button(
                i18n.t("common.sign_out"),
                icon=":material/logout:",
                key="settings_sign_out",
                width="stretch",
            ):
                ui.forget_session_cookie()
                ui.reset_profile_session()
                st.session_state["_logged_out"] = True
                st.session_state.pop("user_id", None)
                st.session_state.pop("user_name", None)
                st.rerun()

    if user.must_change_pin:
        st.warning(i18n.t("settings.default_pin_warning"), icon=":material/key:")


# --------------------------------------------------------------------------- #
# fal.ai connection
# --------------------------------------------------------------------------- #


def _render_connection() -> None:
    if fal.has_key():
        st.success(
            i18n.t(
                "settings.connected",
                source=fal.key_source(),
                hint=fal.key_hint(fal.resolve_key()),
            ),
            icon=":material/check_circle:",
        )
    else:
        st.warning(i18n.t("settings.no_key"), icon=":material/key:")

    if not is_admin:
        st.caption(i18n.t("settings.admin_only_fal"))
        return

    with st.container(border=True):
        with st.form("fal_key_form", clear_on_submit=True, border=False):
            has_saved = fal.key_source() == "Saved in Vertigo settings"
            ratios = [2, 1, 1] if has_saved else [2, 1]
            cells = st.columns(ratios, gap="small", vertical_alignment="bottom")
            with cells[0]:
                entered = st.text_input(
                    i18n.t("settings.fal_key"),
                    type="password",
                    placeholder="key_id:key_secret",
                )
            with cells[1]:
                save = st.form_submit_button(
                    i18n.t("settings.save_key"),
                    icon=":material/save:",
                    type="primary",
                    width="stretch",
                )
            remove = False
            if has_saved:
                with cells[2]:
                    remove = st.form_submit_button(
                        i18n.t("settings.remove_saved_key"),
                        icon=":material/delete:",
                        width="stretch",
                    )

        if save:
            if entered.strip():
                fal.save_key(entered)
                st.toast(i18n.t("toast.key_saved"), icon=":material/check_circle:")
                st.rerun()
            else:
                st.error(i18n.t("error.enter_key"))
        elif remove:
            fal.clear_saved_key()
            st.toast(i18n.t("toast.key_removed"))
            st.rerun()

        st.caption(i18n.t("settings.fal_caption", url=config.FAL_DASHBOARD_URL))


# --------------------------------------------------------------------------- #
# Storage, queue & danger zone
# --------------------------------------------------------------------------- #


def _render_data() -> None:
    with st.container(border=True):
        st.markdown(f"**{i18n.t('settings.storage')}**")
        st.caption(i18n.t("settings.storage_dir", path=library.home))
        counts = library.counts()
        metrics = st.columns(4)
        for column, kind in zip(metrics, config.KINDS):
            column.metric(i18n.t(f"kind.{kind}"), counts.get(kind, 0))
        total_size = sum(asset.size for asset in library.all())
        st.caption(
            i18n.t(
                "settings.storage_usage",
                count=counts["total"],
                size=ui.humanize_bytes(total_size),
            )
        )

    with st.container(border=True):
        st.markdown(f"**{i18n.t('settings.queue')}**")
        queue = manager.counts()
        st.caption(
            i18n.t("settings.queue_caption", total=queue["total"], active=queue["active"])
        )
        if queue["total"]:
            if st.button(i18n.t("settings.clear_finished"), icon=":material/delete_sweep:"):
                removed = manager.clear_finished()
                st.toast(i18n.t("toast.jobs_cleared", count=removed))
                st.rerun()

    st.html(
        """
        <style>
        .st-key-settings_danger,
        .st-key-settings_danger [data-testid="stVerticalBlockBorderWrapper"] {
            border-color: rgba(220, 38, 38, 0.55) !important;
            background-color: rgba(220, 38, 38, 0.06) !important;
        }
        .st-key-settings_danger strong {
            color: light-dark(#b91c1c, #fca5a5) !important;
        }
        .st-key-settings_danger [data-testid="stBaseButton-primary"],
        .st-key-settings_danger button[kind="primary"] {
            background-color: #dc2626 !important;
            border-color: #dc2626 !important;
        }
        .st-key-settings_danger [data-testid="stBaseButton-primary"]:hover,
        .st-key-settings_danger button[kind="primary"]:hover {
            background-color: #b91c1c !important;
            border-color: #b91c1c !important;
        }
        </style>
        """
    )
    with st.container(border=True, key="settings_danger"):
        st.markdown(f"**{i18n.t('settings.danger')}**")
        st.caption(i18n.t("settings.clear_generated_caption"))
        if st.button(i18n.t("settings.clear_generated"), icon=":material/delete_sweep:"):
            removed = library.clear(keep_references=True)
            st.toast(i18n.t("toast.assets_cleared", count=removed))
            st.rerun()

        st.space("small")
        st.caption(i18n.t("settings.delete_all_caption"))
        if st.button(
            i18n.t("settings.delete_all"),
            type="primary",
            icon=":material/delete_forever:",
        ):
            st.session_state["wipe_assets"] = True
            st.rerun()


# --------------------------------------------------------------------------- #
# Family profiles (admin)
# --------------------------------------------------------------------------- #


def _render_family() -> None:
    members = auth.list_users()
    name_col = i18n.t("settings.column.name")
    role_col = i18n.t("settings.column.role")
    assets_col = i18n.t("settings.column.assets")
    actions_col = i18n.t("settings.column.actions")

    rows = []
    for member in members:
        roles = []
        if member.is_admin:
            roles.append(i18n.t("settings.badge_admin"))
        if member.must_change_pin:
            roles.append(i18n.t("settings.badge_default_pin"))
        if member.id == user.id:
            roles.append(i18n.t("settings.badge_you"))
        rows.append(
            {
                name_col: member.name,
                role_col: " · ".join(roles),
                assets_col: get_library(member.id).counts()["total"],
                actions_col: (
                    ""
                    if member.id == user.id
                    else f":material/delete: {i18n.t('settings.remove_profile')}"
                ),
            }
        )

    def _request_remove() -> None:
        click = st.session_state.get("settings_remove_click")
        if click is None:
            return
        row = click["row"]
        if 0 <= row < len(members) and members[row].id != user.id:
            st.session_state["remove_user_id"] = members[row].id

    caption_col, add_col = st.columns([3, 1], gap="medium", vertical_alignment="center")
    with caption_col:
        st.caption(i18n.t("settings.family_caption"))
    with add_col:
        with st.popover(
            i18n.t("settings.add_profile"),
            icon=":material/person_add:",
            width="stretch",
        ):
            with st.form("add_profile_form", clear_on_submit=True, border=False):
                name = st.text_input(
                    i18n.t("settings.new_profile_name"),
                    placeholder=i18n.t("settings.new_profile_name_placeholder"),
                )
                pin = st.text_input(
                    i18n.t("settings.new_profile_pin"),
                    type="password",
                    placeholder=i18n.t("settings.new_profile_pin_placeholder"),
                )
                add = st.form_submit_button(
                    i18n.t("settings.add_profile"),
                    icon=":material/person_add:",
                    type="primary",
                    width="stretch",
                )
            if add:
                try:
                    auth.create_user(name, pin)
                except auth.AuthError as exc:
                    st.error(auth.error_text(exc))
                else:
                    st.toast(
                        i18n.t("toast.profile_added", name=name.strip()),
                        icon=":material/person_add:",
                    )
                    st.rerun()

    st.dataframe(
        rows,
        hide_index=True,
        width="stretch",
        key="settings_profiles_table",
        column_config={
            name_col: st.column_config.TextColumn(name_col, width="medium"),
            role_col: st.column_config.TextColumn(role_col, width="medium"),
            assets_col: st.column_config.NumberColumn(assets_col, width="small"),
            actions_col: st.column_config.ButtonColumn(
                actions_col,
                type="secondary",
                on_click=_request_remove,
                key="settings_remove_click",
            ),
        },
    )


# --------------------------------------------------------------------------- #
# About
# --------------------------------------------------------------------------- #


def _render_about() -> None:
    st.write(
        i18n.t(
            "settings.about_text",
            app=config.APP_NAME,
            tagline=config.TAGLINE,
            url=config.FAL_MODELS_URL,
        )
    )
    st.caption(
        "Models: GPT Image 2.5 · Nano Banana 2 · Recraft V3 · Ideogram · Topaz · "
        "ElevenLabs Multilingual v2 · ElevenLabs Scribe v2"
    )


# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

TAB_KEYS = ["profile", "connection", "data"]
if is_admin:
    TAB_KEYS.append("family")
TAB_KEYS.append("about")

panels = dict(
    zip(TAB_KEYS, st.tabs([i18n.t(f"settings.tab.{key}") for key in TAB_KEYS]))
)

with panels["profile"]:
    _render_profile()

with panels["connection"]:
    _render_connection()

with panels["data"]:
    _render_data()

if is_admin:
    with panels["family"]:
        _render_family()

with panels["about"]:
    _render_about()

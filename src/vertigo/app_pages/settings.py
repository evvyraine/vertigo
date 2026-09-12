"""Settings — profile, per-user storage, the fal connection and family profiles."""

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

st.subheader(i18n.t("settings.profile"), icon=":material/person:")
st.caption(
    i18n.t("settings.signed_in", name=user.name)
    + (f" · {i18n.t('settings.admin')}" if is_admin else "")
    + f" · `{user.id}`"
)
if user.must_change_pin:
    st.warning(i18n.t("settings.default_pin_warning"), icon=":material/key:")

profile_name, profile_pin = st.columns(2, gap="large")

with profile_name, st.form("profile_name_form"):
    new_name = st.text_input(i18n.t("settings.display_name"), value=user.name)
    if st.form_submit_button(i18n.t("settings.save_name"), icon=":material/save:"):
        try:
            auth.rename_user(user.id, new_name)
        except auth.AuthError as exc:
            st.error(auth.error_text(exc))
        else:
            st.session_state["user_name"] = new_name.strip()
            st.toast(i18n.t("toast.name_updated"), icon=":material/check_circle:")
            st.rerun()

with profile_pin, st.form("profile_pin_form", clear_on_submit=True):
    current_pin = st.text_input(i18n.t("settings.current_pin"), type="password")
    new_pin = st.text_input(i18n.t("settings.new_pin"), type="password")
    confirm_pin = st.text_input(i18n.t("settings.confirm_pin"), type="password")
    if st.form_submit_button(i18n.t("settings.change_pin"), icon=":material/key:"):
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
                st.toast(i18n.t("toast.pin_updated"), icon=":material/check_circle:")
                st.rerun()

if st.button(i18n.t("common.sign_out"), icon=":material/logout:"):
    ui.forget_session_cookie()
    ui.reset_profile_session()
    st.session_state["_logged_out"] = True
    st.session_state.pop("user_id", None)
    st.session_state.pop("user_name", None)
    st.rerun()


# --------------------------------------------------------------------------- #
# fal.ai connection
# --------------------------------------------------------------------------- #

st.subheader(i18n.t("settings.fal"), icon=":material/key:")

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

if is_admin:
    with st.form("fal_key_form", clear_on_submit=True):
        entered = st.text_input(
            i18n.t("settings.fal_key"),
            type="password",
            placeholder="key_id:key_secret",
        )
        submitted = st.form_submit_button(i18n.t("settings.save_key"), icon=":material/save:")
    if submitted:
        if entered.strip():
            fal.save_key(entered)
            st.toast(i18n.t("toast.key_saved"), icon=":material/check_circle:")
            st.rerun()
        else:
            st.error(i18n.t("error.enter_key"))

    st.caption(i18n.t("settings.fal_caption", url=config.FAL_DASHBOARD_URL))
    if fal.key_source() == "Saved in Vertigo settings":
        if st.button(i18n.t("settings.remove_saved_key"), icon=":material/delete:"):
            fal.clear_saved_key()
            st.toast(i18n.t("toast.key_removed"))
            st.rerun()
else:
    st.caption(i18n.t("settings.admin_only_fal"))


# --------------------------------------------------------------------------- #
# Per-user storage & queue
# --------------------------------------------------------------------------- #

st.subheader(i18n.t("settings.storage"), icon=":material/folder_open:")
st.write(i18n.t("settings.storage_dir", path=library.home))
st.caption(i18n.t("settings.storage_caption"))

counts = library.counts()
metrics = st.columns(4)
for column, kind in zip(metrics, config.KINDS):
    column.metric(i18n.t(f"kind.{kind}"), counts.get(kind, 0))
total_size = sum(asset.size for asset in library.all())
st.caption(
    i18n.t("settings.storage_usage", count=counts["total"], size=ui.humanize_bytes(total_size))
)

st.subheader(i18n.t("settings.queue"), icon=":material/queue:")
queue = manager.counts()
st.caption(
    i18n.t("settings.queue_caption", total=queue["total"], active=queue["active"])
)
if queue["total"]:
    if st.button(i18n.t("settings.clear_finished"), icon=":material/delete_sweep:"):
        removed = manager.clear_finished()
        st.toast(i18n.t("toast.jobs_cleared", count=removed))
        st.rerun()

st.subheader(i18n.t("settings.danger"), icon=":material/warning:")
with st.container(border=True):
    st.markdown(f"**{i18n.t('settings.clear_generated')}**")
    st.caption(i18n.t("settings.clear_generated_caption"))
    if st.button(i18n.t("settings.clear_generated"), icon=":material/delete_sweep:"):
        removed = library.clear(keep_references=True)
        st.toast(i18n.t("toast.assets_cleared", count=removed))
        st.rerun()

    st.space("small")
    st.markdown(f"**{i18n.t('settings.delete_all')}**")
    st.caption(i18n.t("settings.delete_all_caption"))
    if st.button(i18n.t("settings.delete_all"), icon=":material/delete_forever:"):
        st.session_state["wipe_assets"] = True
        st.rerun()


# --------------------------------------------------------------------------- #
# Family profiles (admin)
# --------------------------------------------------------------------------- #

if is_admin:
    st.subheader(i18n.t("settings.family"), icon=":material/group:")
    st.caption(i18n.t("settings.family_caption"))

    for member in auth.list_users():
        member_library = get_library(member.id)
        with st.container(border=True):
            info, size_col, action = st.columns([3, 1, 1], vertical_alignment="center")
            with info:
                badges = []
                if member.is_admin:
                    badges.append(f":blue-badge[{i18n.t('settings.badge_admin')}]")
                if member.must_change_pin:
                    badges.append(f":orange-badge[{i18n.t('settings.badge_default_pin')}]")
                if member.id == user.id:
                    badges.append(f":gray-badge[{i18n.t('settings.badge_you')}]")
                st.markdown(f"**{member.name}** " + " ".join(badges))
                st.caption(f"`{member.id}` · {ui.relative_time(member.created_at)}")
            size_col.caption(i18n.t("settings.assets_count", count=member_library.counts()["total"]))
            if member.id != user.id:
                if action.button(
                    i18n.t("settings.remove_profile"),
                    key=f"remove_profile_{member.id}",
                    icon=":material/delete:",
                ):
                    st.session_state["remove_user_id"] = member.id
                    st.rerun()

    with st.form("add_profile_form", clear_on_submit=True):
        columns = st.columns([2, 2, 1], vertical_alignment="bottom")
        name = columns[0].text_input(
            i18n.t("settings.new_profile_name"),
            placeholder=i18n.t("settings.new_profile_name_placeholder"),
        )
        pin = columns[1].text_input(
            i18n.t("settings.new_profile_pin"),
            type="password",
            placeholder=i18n.t("settings.new_profile_pin_placeholder"),
        )
        add = columns[2].form_submit_button(
            i18n.t("settings.add_profile"), icon=":material/person_add:"
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


# --------------------------------------------------------------------------- #
# About
# --------------------------------------------------------------------------- #

st.subheader(i18n.t("settings.about"), icon=":material/cyclone:")
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

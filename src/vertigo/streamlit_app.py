"""Vertigo — Streamlit entry point, profile gate and navigation.

Run with ``uv run vertigo`` or ``uv run streamlit run src/vertigo/streamlit_app.py``.
"""

from __future__ import annotations

import time

import streamlit as st

from vertigo import auth, fal, i18n, oidc, pwa, ui

st.set_page_config(
    page_title="Vertigo",
    page_icon=":material/cyclone:",
    layout="wide",
    initial_sidebar_state="expanded",
)

pwa.install_pwa()
fal.configure()
auth.ensure_users()

for key in ("studio_refs", "studio_jobs", "enhance_jobs", "speech_jobs"):
    st.session_state.setdefault(key, [])

# Resolve the interface language before anything renders.
i18n.set_language(ui.current_language())

# Apply queued cookie writes from the previous run (fire-and-forget script).
ui.render_cookie_bridge()


def _telegram_login_screen() -> None:
    """Render the Telegram sign-in screen when OIDC is enabled."""
    _, middle, _ = st.columns([1, 1.3, 1])
    with middle:
        st.markdown("## :material/cyclone: Vertigo")
        st.caption("Sign in with Telegram to continue.")
        ui.language_switch("")
        try:
            if st.button(
                "Sign in with Telegram",
                type="primary",
                icon=":material/send:",
                key="telegram_sign_in",
            ):
                st.login(oidc.PROVIDER)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Telegram sign-in is not configured yet: {exc}")
        st.caption("Access is limited to approved Telegram accounts.")
    st.stop()


# Telegram is the outer gate when enabled; each account maps to a profile.
if oidc.enabled():
    if not oidc.is_logged_in():
        _telegram_login_screen()
    _member = auth.get_user(st.session_state.get("user_id"))
    if _member is None or _member.telegram_id != oidc.subject():
        ui.reset_profile_session()
        _member = auth.ensure_telegram_user(
            oidc.subject(), oidc.display_name(), oidc.username()
        )
        st.session_state["user_id"] = _member.id
        st.session_state["user_name"] = _member.name
        st.session_state["lang"] = ui.current_language()
        i18n.set_language(ui.current_language())
        st.rerun()

# Auto sign-in from a remember-me cookie. Skipped right after an explicit
# sign-out so the stale cookie in this request can't log the user back in.
if (
    not oidc.enabled()
    and auth.get_user(st.session_state.get("user_id")) is None
    and not st.session_state.get("_logged_out")
):
    cookie = ui.cookie_token()
    member = auth.get_user(auth.resolve_session(cookie))
    if member is not None:
        ui.reset_profile_session()
        if cookie:
            st.session_state["_session_token"] = cookie
        st.session_state["user_id"] = member.id
        st.session_state["user_name"] = member.name
        i18n.set_language(ui.current_language())
        st.rerun()


def _login_screen() -> None:
    """Render the profile picker and PIN prompt."""
    _, middle, _ = st.columns([1, 1.3, 1])
    with middle:
        st.markdown(f"## :material/cyclone: {i18n.t('login.title')}")
        st.caption(i18n.t("login.subtitle"))
        ui.language_switch("")

        users = auth.list_users()
        if not users:
            st.error(i18n.t("login.no_profiles"))
            return

        options = {member.name: member.id for member in users}
        with st.form("login_form"):
            choice = st.selectbox(i18n.t("login.profile"), list(options))
            pin = st.text_input(i18n.t("login.pin"), type="password")
            remember = st.checkbox(i18n.t("login.remember"), value=True)
            submitted = st.form_submit_button(
                i18n.t("login.sign_in"), type="primary", icon=":material/login:"
            )

        if submitted:
            user_id = options[choice]
            if auth.authenticate(user_id, pin):
                ui.reset_profile_session()
                st.session_state.pop("_logged_out", None)
                st.session_state["user_id"] = user_id
                st.session_state["user_name"] = choice
                # Carry a language chosen before sign-in into the profile.
                resolved_lang = ui.current_language()
                st.session_state["lang"] = resolved_lang
                auth.set_locale(user_id, resolved_lang)
                i18n.set_language(resolved_lang)
                if remember:
                    ui.remember_session(user_id)
                else:
                    ui.forget_session_cookie()
                st.rerun()
            else:
                time.sleep(0.6)
                st.error(i18n.t("login.wrong_pin"), icon=":material/error:")

        st.caption(i18n.t("login.default_pin_hint"))


if auth.get_user(st.session_state.get("user_id")) is None:
    # Not signed in, or the signed-in profile was deleted from another tab.
    ui.reset_profile_session()
    st.session_state.pop("user_id", None)
    st.session_state.pop("user_name", None)
    if oidc.enabled():
        _telegram_login_screen()
    else:
        _login_screen()
    st.stop()

PAGE_DEFS = [
    {
        "path": "app_pages/home.py",
        "title": i18n.t("nav.home"),
        "icon": ":material/cyclone:",
        "section": "",
        "subtitle": i18n.t("subtitle.home"),
    },
    {
        "path": "app_pages/studio.py",
        "title": i18n.t("nav.studio"),
        "icon": ":material/auto_awesome:",
        "section": i18n.t("section.create"),
        "subtitle": i18n.t("subtitle.studio"),
    },
    {
        "path": "app_pages/enhance.py",
        "title": i18n.t("nav.enhance"),
        "icon": ":material/high_quality:",
        "section": i18n.t("section.create"),
        "subtitle": i18n.t("subtitle.enhance"),
    },
    {
        "path": "app_pages/speech.py",
        "title": i18n.t("nav.speech"),
        "icon": ":material/record_voice_over:",
        "section": i18n.t("section.create"),
        "subtitle": i18n.t("subtitle.speech"),
    },
    {
        "path": "app_pages/library.py",
        "title": i18n.t("nav.library"),
        "icon": ":material/photo_library:",
        "section": i18n.t("section.manage"),
        "subtitle": i18n.t("subtitle.library"),
    },
    {
        "path": "app_pages/settings.py",
        "title": i18n.t("nav.settings"),
        "icon": ":material/settings:",
        "section": i18n.t("section.manage"),
        "subtitle": i18n.t("subtitle.settings"),
    },
]

_sections: dict[str, list[st.Page]] = {}
for definition in PAGE_DEFS:
    _sections.setdefault(definition["section"], []).append(
        st.Page(definition["path"], title=definition["title"], icon=definition["icon"])
    )

page = st.navigation(_sections, position="sidebar")

with st.sidebar:
    st.space("small")
    st.caption(
        i18n.t("sidebar.signed_in", name=st.session_state.get("user_name", ""))
        + "  ·  "
        + i18n.t("sidebar.jobs", count=ui.current_manager().counts()["total"])
    )
    if st.button(
        i18n.t("common.sign_out"), key="sidebar_sign_out", icon=":material/logout:"
    ):
        ui.reset_profile_session()
        if oidc.enabled():
            st.logout()
        else:
            ui.forget_session_cookie()
            st.session_state["_logged_out"] = True
            st.session_state.pop("user_id", None)
            st.session_state.pop("user_name", None)
            st.rerun()
    ui.language_switch()
    if not fal.has_key():
        st.caption(i18n.t("sidebar.no_key"))

st.title(page.title, icon=page.icon)
_subtitle = next((d["subtitle"] for d in PAGE_DEFS if d["title"] == page.title), None)
if _subtitle:
    st.caption(_subtitle)

page.run()

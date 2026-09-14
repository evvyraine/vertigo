"""Smoke tests for the pieces that don't need a Streamlit runtime.

They cover the on-disk library, profile auth, translations, slug naming and the
``secrets.toml`` merge that self-hosters depend on. Run with ``uv run pytest``.
"""

from __future__ import annotations

import pytest

from vertigo import auth, config, i18n, naming, oidc
from vertigo.store import Library


@pytest.fixture(autouse=True)
def vertigo_home(tmp_path, monkeypatch):
    """Point every test at a throwaway data directory."""
    monkeypatch.setenv("VERTIGO_HOME", str(tmp_path))
    for name in (
        "VERTIGO_OIDC_ENABLED",
        "VERTIGO_OIDC_CLIENT_ID",
        "VERTIGO_OIDC_CLIENT_SECRET",
        "VERTIGO_PUBLIC_URL",
        "VERTIGO_SECRETS_DIR",
        "FAL_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_base_home_follows_env(vertigo_home):
    assert config.base_home() == vertigo_home


def test_library_roundtrip(tmp_path):
    home = tmp_path / "library"
    library = Library(home)
    asset = library.add_file(
        b"hello world",
        kind=config.KIND_TEXT,
        name="note.txt",
        media_type="text/plain",
    )

    assert library.text_of(asset) == "hello world"
    assert library.counts()["total"] == 1
    # A fresh instance reads the persisted metadata back from disk.
    assert Library(home).get(asset.id).name == "note.txt"

    assert library.delete(asset.id) is True
    assert Library(home).get(asset.id) is None
    assert not library.file_path(asset).exists()


def test_seed_profiles_and_pin_auth(vertigo_home):
    auth.ensure_users()
    users = auth.list_users()
    assert len(users) == 3
    assert users[0].is_admin is True

    first = users[0].id
    assert auth.authenticate(first, auth.DEFAULT_PIN) is True
    assert auth.authenticate(first, "9999") is False

    auth.set_pin(first, "2468")
    assert auth.authenticate(first, "2468") is True
    assert auth.authenticate(first, auth.DEFAULT_PIN) is False


def test_telegram_user_is_stable(vertigo_home):
    created = auth.ensure_telegram_user("42", "Ada", "ada")
    assert created.telegram_id == "42"
    again = auth.ensure_telegram_user("42", "Ada", "ada")
    assert again.id == created.id
    assert auth.user_by_telegram("42").id == created.id


def test_translations_switch():
    i18n.set_language("ru")
    assert i18n.t("nav.home") == "Главная"
    i18n.set_language("en")
    assert i18n.t("nav.home") == "Home"
    assert i18n.t("missing.key") == "missing.key"


def test_slugify_transliterates_cyrillic():
    assert naming.slugify("Привет, мир!") == "privet-mir"
    assert naming.slugify("") == "output"


def test_secrets_merge_preserves_unrelated_keys(monkeypatch):
    monkeypatch.setenv("VERTIGO_PUBLIC_URL", "https://vertigo.example.com")
    monkeypatch.setenv("VERTIGO_OIDC_CLIENT_ID", "123")
    monkeypatch.setenv("VERTIGO_OIDC_CLIENT_SECRET", "shh")

    existing = 'FAL_KEY = "my-fal-key"\n\n[auth]\nredirect_uri = "old"\ncookie_secret = "old"\n'
    merged = oidc.render_secrets(existing)

    assert 'FAL_KEY = "my-fal-key"' in merged
    assert "https://vertigo.example.com/oauth2callback" in merged
    assert 'client_id = "123"' in merged
    assert "old" not in merged
    # Rendering again is a no-op, so restarts don't churn the file.
    assert oidc.render_secrets(merged) == merged


def test_write_secrets_respects_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("VERTIGO_OIDC_ENABLED", "1")
    monkeypatch.setenv("VERTIGO_OIDC_CLIENT_ID", "1")
    monkeypatch.setenv("VERTIGO_OIDC_CLIENT_SECRET", "x")

    path = oidc.write_secrets()
    assert path == tmp_path / ".streamlit" / "secrets.toml"
    assert path.exists()
    assert oidc.secrets_path() == path


def test_write_secrets_noop_when_disabled(vertigo_home):
    assert oidc.write_secrets() is None

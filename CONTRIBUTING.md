# Contributing to Vertigo

Thanks for helping out! Vertigo is a small Streamlit app, so the loop is quick.

## Getting set up

```bash
git clone https://github.com/evvyraine/vertigo.git
cd vertigo
uv sync                 # installs the app + dev tools into .venv
uv run pytest -q        # run the smoke tests
uv run vertigo          # launch it
```

You need a fal.ai key to exercise the generation features, but the tests and the
Settings page work without one.

## Project layout

```
src/vertigo/
├── streamlit_app.py   # entry point: profile gate, navigation
├── config.py          # paths, settings, model catalogue
├── auth.py            # profiles, PINs, remember-me sessions
├── oidc.py            # optional Telegram sign-in
├── store.py           # file-backed media library
├── jobs.py            # background generation queue
├── fal.py             # fal.ai client helpers
├── i18n.py            # English + Russian strings
├── ui.py              # shared Streamlit widgets
└── app_pages/         # one module per page
```

## Guidelines

- Keep changes consistent with the surrounding code style; the project uses
  `from __future__ import annotations` and type hints throughout.
- Add or update strings in **both** languages in `i18n.py`.
- Avoid adding hard dependencies when the standard library will do.
- Run `uv run pytest -q` before opening a pull request.

## Adding a translation

`i18n.py` holds one dict per language under `TRANSLATIONS`. Add the key to the
English table, then to the Russian one, and use `i18n.t("your.key")` in the UI.

## Reporting bugs

Open an issue with your OS, Python version, the command you ran, and the full
traceback or Streamlit log output. Never paste a real `FAL_KEY` or Telegram
`client_secret`.

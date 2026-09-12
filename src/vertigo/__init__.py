"""Vertigo — a self-hosted generative media powerhouse built on fal.ai.

Vertigo packages fal.ai's image, vector, upscaling, speech and transcription
models into a single Streamlit application with a durable local library.
"""

from __future__ import annotations

__version__ = "0.1.0"


def main() -> None:
    """Launch the Vertigo Streamlit app.

    Extra command line arguments are forwarded to ``streamlit run`` so callers
    can override server settings, e.g. ``vertigo --server.port 8600``.
    """
    import sys
    from pathlib import Path

    from streamlit.web import cli as stcli

    app = Path(__file__).with_name("streamlit_app.py")
    if not app.exists():  # pragma: no cover - defensive
        raise SystemExit(f"Could not find the Streamlit app at {app}")

    # The custom theme lives in `.streamlit/config.toml`, which Streamlit reads
    # from the working directory. Run from the project root (or via the launchd
    # service, whose WorkingDirectory is the project) for the styled look.
    sys.argv = ["streamlit", "run", str(app), *sys.argv[1:]]
    raise SystemExit(stcli.main())

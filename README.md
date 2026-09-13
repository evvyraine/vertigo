# Vertigo

Self-hosted generative media on [fal.ai](https://fal.ai) — a family-friendly
Streamlit app with per-profile libraries, in English and Russian.

## Install

```bash
uv sync
export FAL_KEY="your-key-here"    # or add it later in Settings
uv run vertigo
```

Runs on <http://localhost:8501>; extra flags are forwarded, e.g.
`uv run vertigo --server.port 8600`.

## What it does

- **Images** — generate with GPT Image 2.5 / Nano Banana 2, edit with references.
- **Vectors** — Recraft vector art, or trace an image into a real SVG.
- **Enhance** — upscale (Recraft, Topaz) and remove backgrounds (Ideogram).
- **Speech** — ElevenLabs text-to-speech and Scribe transcription (with `.srt`).
- **Library** — generations run in the background and are saved locally to
  browse, rename, reuse and delete.

## Profiles & sign-in

The first run creates three profiles (`User 1`–`User 3`, PIN `0000`), each with
an isolated library under `~/.vertigo/users/<id>/`. Change names and PINs in
**Settings**; set `VERTIGO_HOME` to relocate all data.

Telegram sign-in can replace the PIN gate: each account is mapped to a profile
(created on first sign-in). Set `VERTIGO_OIDC_ENABLED=1` with
`VERTIGO_OIDC_CLIENT_ID` and `VERTIGO_OIDC_CLIENT_SECRET` from @BotFather, plus
`VERTIGO_PUBLIC_URL`, and register `${VERTIGO_PUBLIC_URL}/oauth2callback` as an
allowed URL in @BotFather.

## License

MIT — see [LICENSE](LICENSE).

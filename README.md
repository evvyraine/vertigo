# Vertigo

Self-hosted generative media platform on [fal.ai](https://fal.ai) — a family-friendly
Streamlit app with per-profile libraries, in English and Russian.

## Features

- **Images** — generate with GPT Image 2.5 / Nano Banana 2, edit with any number of
  references, and keep editing any result.
- **Vectors** — generate vector art with Recraft, or trace an image to a real SVG.
- **Enhance** — upscale (Recraft, Topaz) and remove backgrounds (Ideogram).
- **Speech** — text-to-speech (ElevenLabs) and transcription (Scribe v2, with `.srt`).
- **Queue & library** — generations run in the background; results are saved to a
  durable local library you can browse, rename, reuse and delete.
- **Profiles** — up to 12 PIN-protected profiles with isolated libraries, plus
  "remember me" sessions.

## Setup

```bash
uv sync
export FAL_KEY="your-key-here"    # or add it later in Settings
uv run vertigo
```

Streamlit runs on <http://localhost:8501>. Extra flags are forwarded:
`uv run vertigo --server.port 8600`.

## Pages

| Page | Purpose |
| --- | --- |
| **Home** | Stats, recent work, quick links. |
| **Image studio** | Generate, edit with references, vectorise. |
| **Enhance** | Upscale and remove backgrounds. |
| **Speech** | Text-to-speech and transcription. |
| **Library** | Browse, filter, rename, download, delete. |
| **Settings** | Profile, storage, queue, fal key, family profiles. |

## Profiles

On first run three profiles are created (`User 1`–`User 3`, PIN `0000`; the first is
the administrator). Everyone gets an isolated library under
`~/.vertigo/users/<id>/` and can generate at the same time. Change names and PINs in
**Settings**. Set `VERTIGO_HOME` to relocate all data.

## Models

GPT Image 2.5 · Nano Banana 2 · Recraft V3 · Recraft Vectorize · Ideogram
remove-background · Recraft/Topaz upscale · ElevenLabs Multilingual v2 · ElevenLabs
Scribe v2. The catalogue lives in [`src/vertigo/config.py`](src/vertigo/config.py).

## Theming

Inter Tight with soft, low-contrast surfaces and generous radii. Light and dark
variants are defined in [`.streamlit/config.toml`](.streamlit/config.toml) and can be
switched from the Streamlit settings menu. Launch from the project root so the config
is picked up.

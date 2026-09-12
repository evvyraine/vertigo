# Vertigo

**A self-hosted generative media powerhouse.** Vertigo wraps [fal.ai](https://fal.ai)'s
image, vector, upscaling and speech models in a single Streamlit app with a durable
local library, so you can generate, edit, enhance and transcribe in one place.

Every generation is submitted to fal's queue and processed in the background. Outputs
are downloaded into your own library, where they can be reused as references,
downloaded, or deleted.

## Features

- **Image generation & editing** — GPT Image 2.5 and Nano Banana 2, with text-to-image,
  reference-guided editing, and any number of reference images (uploaded or pulled from
  the library). Continue editing any output by adding another prompt or more references.
- **Vectors** — generate vector-style illustration with Recraft V3, or trace a raster
  image into a true `.svg` with Recraft Vectorize.
- **Upscale & remove backgrounds** — Recraft Creative Upscale, Topaz generative upscale,
  and Ideogram background removal (transparent PNG).
- **Speech** — ElevenLabs Multilingual v2 text-to-speech and Scribe v2 transcription with
  word timings, speaker labels, and `.srt` export.
- **A real queue** — jobs run in a thread pool, survive page reruns (and server restarts
  when a fal request id exists), and stream status/logs back into the page live.
- **A shared library** — generated and uploaded assets are stored on disk with metadata;
  browse, filter, search, download, reuse and delete them.
- **Family profiles** — up to 12 profiles behind a PIN, each with a fully isolated
  library, history and queue on the same host. One shared fal key.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- A fal API key — create one at [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys)

## Setup

```bash
uv sync
export FAL_KEY="your-key-here"
```

Alternatively, put `FAL_KEY` in a `.env` file, in `.streamlit/secrets.toml`, or paste it
into the in-app **Settings** page (saved to `~/.vertigo/config.json`).

## Run

```bash
uv run vertigo
```

This launches Streamlit (defaults to <http://localhost:8501>). Pass Streamlit flags
through, for example:

```bash
uv run vertigo --server.port 8600
```

You can also run the app directly:

```bash
uv run streamlit run src/vertigo/streamlit_app.py
```

## Profiles & access

On first run Vertigo creates three profiles — **User 1**, **User 2**, **User 3** —
all with the default PIN `0000`. Pick a profile on the sign-in screen and enter its
PIN. Rename profiles and set real PINs in **Settings → Your profile**; the first
profile is the administrator and can also add or remove profiles and manage the shared
fal key.

Everything a profile makes is isolated: their own `assets/`, `library.json`, and
`jobs.json` under `~/.vertigo/users/<id>/`. Profiles can generate at the same time.
If you upgrade from the earlier single-user version, the existing library is moved into
the first profile automatically.

**Remember me** keeps you signed in for 30 days using a `vertigo_session` cookie. The
cookie only holds a random token; the token itself is stored hashed in
`~/.vertigo/sessions.json`, and signing out or changing your PIN revokes it.

**Languages** — the interface ships in English and Russian. Switch any time from the
sidebar (or the sign-in screen); the choice is saved to your profile, so it follows
you to another device, and it is also mirrored to a `vertigo_lang` cookie for the
sign-in screen. Translation strings live in
[`src/vertigo/i18n.py`](src/vertigo/i18n.py) and are easy to extend.

> This is convenience-grade auth for a trusted local network. PINs are salted and
> PBKDF2-hashed on disk, but traffic is plain HTTP — don't expose it to the internet.

## Pages

| Page | What it does |
| --- | --- |
| **Home** | Library stats, recent work, and quick links. |
| **Image studio** | Generate, edit with references, and create/trace vectors. |
| **Enhance** | Upscale images and remove backgrounds. |
| **Speech** | Text-to-speech and audio transcription. |
| **Library** | Browse, filter, search, download, reuse and delete assets. |
| **Settings** | Connect fal.ai, inspect storage, and manage the queue. |

## Models

| Capability | Endpoint |
| --- | --- |
| Text to image | `openai/gpt-image-2.5/sunburst/text-to-image` |
| Image edit | `openai/gpt-image-2.5/sunburst/edit` |
| Text to image | `fal-ai/nano-banana-2` |
| Image edit | `fal-ai/nano-banana-2/edit` |
| Text to vector art | `fal-ai/recraft/v3/text-to-image` |
| Trace to SVG | `fal-ai/recraft/vectorize` |
| Remove background | `fal-ai/ideogram/remove-background` |
| Creative upscale | `fal-ai/recraft/upscale/creative` |
| Generative upscale | `fal-ai/topaz/upscale/image` |
| Text to speech | `fal-ai/elevenlabs/tts/multilingual-v2` |
| Speech to text | `fal-ai/elevenlabs/speech-to-text/scribe-v2` |

The catalogue lives in [`src/vertigo/config.py`](src/vertigo/config.py) and is easy to
extend with additional fal endpoints.

## Storage

By default everything lives in `~/.vertigo`, split between shared settings and
per-profile libraries:

```
~/.vertigo/
├── config.json         # shared settings (fal key)
├── users.json          # profiles + salted PIN hashes
├── sessions.json       # "remember me" token hashes
└── users/
    ├── <profile-id>/
    │   ├── assets/     # that profile's downloaded/generated media
    │   ├── library.json
    │   └── jobs.json
    └── <profile-id>/
        └── …
```

Set `VERTIGO_HOME` to relocate the whole data directory:

```bash
VERTIGO_HOME=./data uv run vertigo
```

## How it works

```
streamlit_app.py        # profile gate, navigation + shared state
app_pages/              # one script per page (Home, Studio, Enhance, Speech, Library, Settings)
auth.py                 # profile registry, PIN hashing, legacy migration
i18n.py                 # English/Russian interface translations
config.py               # paths, model catalogue, settings
store.py                # per-profile, thread-safe, file-backed asset library
fal.py                  # credential resolution + fal-client wrappers
jobs.py                 # per-profile background queue, persistence, restart recovery
ui.py                   # shared Streamlit helpers
```

Generations are submitted with `fal_client.subscribe` inside a small thread pool. Each
`Job` records its fal request id, status, logs and output asset ids; results are
downloaded and registered in the library automatically. Because job state is persisted,
an in-flight job can be re-attached after a restart using its request id.

## Theming

The interface uses **Inter Tight** with generous corner radii and soft, low-contrast
surfaces. Both `[theme.light]` and `[theme.dark]` are defined in
[`.streamlit/config.toml`](.streamlit/config.toml), so you can switch between them from
the Streamlit settings menu (⋮ → Settings → Theme):

- Light — soft-gray surface (`#f3f4f6`) instead of off-white, white cards.
- Dark — very dark gray surface (`#17181c`) instead of off-black.

Streamlit reads `.streamlit/config.toml` from the working directory, so launch from the
project root (or via the background service, whose working directory is the project).

## Notes

- `<10 MB` reference images work best; fal accepts HTTPS URLs, so Vertigo uploads local
  files to the fal CDN once and caches the URL on the asset.
- Costs vary by model — each page shows current per-model pricing from the fal catalogue.
- Profiles share one process but not their data: each keeps its own library and queue,
  and can generate concurrently under the same fal key.

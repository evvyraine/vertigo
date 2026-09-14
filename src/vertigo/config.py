"""Paths, persisted settings and the model catalogue for Vertigo.

Everything here is plain data and small helpers. Nothing imports Streamlit at
module import time so the same catalogue is usable from background threads.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

APP_NAME = "Vertigo"
TAGLINE = "A self-hosted generative media powerhouse"
FAL_DASHBOARD_URL = "https://fal.ai/dashboard/keys"
FAL_MODELS_URL = "https://fal.ai/models"

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def base_home() -> Path:
    """Return the root directory for all Vertigo data.

    Each profile keeps its own library under ``<base>/users/<user_id>`` while
    shared settings (the fal key and the user registry) live at the root.
    """
    return Path(os.environ.get("VERTIGO_HOME", Path.home() / ".vertigo")).expanduser()


def user_home(user_id: str) -> Path:
    """Return the isolated data directory for a single profile."""
    return base_home() / "users" / user_id


def config_file() -> Path:
    """Shared settings file (holds the global fal key)."""
    return base_home() / "config.json"


def users_file() -> Path:
    """The user registry shared by every profile."""
    return base_home() / "users.json"


def sessions_file() -> Path:
    """The "remember me" session token store."""
    return base_home() / "sessions.json"


def ensure_base_dirs() -> None:
    base_home().mkdir(parents=True, exist_ok=True)


#: Static assets shipped inside the package (icons, brand mark).
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGO_FILE = STATIC_DIR / "brand" / "logo.png"


_config_lock = threading.Lock()


def load_config() -> dict[str, Any]:
    """Read the small JSON settings file, tolerating a missing/corrupt file."""
    try:
        raw = config_file().read_text(encoding="utf-8")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_config(data: dict[str, Any]) -> None:
    ensure_base_dirs()
    with _config_lock:
        tmp = config_file().with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, config_file())


def update_config(**values: Any) -> dict[str, Any]:
    data = load_config()
    data.update(values)
    save_config(data)
    return data


# --------------------------------------------------------------------------- #
# Library vocabulary
# --------------------------------------------------------------------------- #

KIND_IMAGE = "image"
KIND_VECTOR = "vector"
KIND_AUDIO = "audio"
KIND_TEXT = "text"

KINDS = (KIND_IMAGE, KIND_VECTOR, KIND_AUDIO, KIND_TEXT)

ORIGIN_GENERATED = "generated"
ORIGIN_UPLOADED = "uploaded"
ORIGIN_REFERENCE = "reference"

ORIGINS = (ORIGIN_GENERATED, ORIGIN_UPLOADED, ORIGIN_REFERENCE)

KIND_LABELS = {
    KIND_IMAGE: "Image",
    KIND_VECTOR: "Vector",
    KIND_AUDIO: "Audio",
    KIND_TEXT: "Text",
}

KIND_ICONS = {
    KIND_IMAGE: ":material/image:",
    KIND_VECTOR: ":material/polyline:",
    KIND_AUDIO: ":material/graphic_eq:",
    KIND_TEXT: ":material/article:",
}

IMAGE_UPLOAD_TYPES = ["png", "jpg", "jpeg", "webp", "gif", "bmp"]
AUDIO_UPLOAD_TYPES = ["mp3", "wav", "m4a", "aac", "ogg", "flac", "webm", "mp4"]

# --------------------------------------------------------------------------- #
# Image generation + editing models
# --------------------------------------------------------------------------- #

IMAGE_MODELS: list[dict[str, Any]] = [
    {
        "id": "gpt-image-2.5",
        "label": "GPT Image 2.5",
        "tagline": "Precision detail, typography and tight, surgical edits.",
        "t2i": "openai/gpt-image-2.5/sunburst/text-to-image",
        "edit": "openai/gpt-image-2.5/sunburst/edit",
        "max_refs": 16,
        "max_images": 10,
        "engine": "openai",
        "pricing": "Priced per image token — roughly $0.02–$0.25 per image.",
        "supports_background": True,
        "supports_quality": True,
    },
    {
        "id": "nano-banana-2",
        "label": "Nano Banana 2",
        "tagline": "Google's fast generation and multi-reference editor, up to 4K.",
        "t2i": "fal-ai/nano-banana-2",
        "edit": "fal-ai/nano-banana-2/edit",
        "max_refs": 14,
        "max_images": 4,
        "engine": "gemini",
        "pricing": "$0.08 per image ($0.12 at 2K, $0.16 at 4K).",
        "supports_background": False,
        "supports_quality": False,
    },
]

IMAGE_MODELS_BY_ID = {m["id"]: m for m in IMAGE_MODELS}

GPT_IMAGE_SIZES = [
    ("Auto", "auto"),
    ("Square (1024²)", "square_hd"),
    ("Landscape 4:3", "landscape_4_3"),
    ("Landscape 16:9", "landscape_16_9"),
    ("Portrait 4:3", "portrait_4_3"),
    ("Portrait 16:9", "portrait_16_9"),
]

GPT_QUALITIES = ["auto", "low", "medium", "high", "xhigh", "max"]

GPT_BACKGROUNDS = ["auto", "transparent", "opaque"]

IMAGE_OUTPUT_FORMATS = ["png", "jpeg", "webp"]

NANO_ASPECT_RATIOS = [
    "auto",
    "21:9",
    "16:9",
    "3:2",
    "4:3",
    "5:4",
    "1:1",
    "4:5",
    "3:4",
    "2:3",
    "9:16",
    "4:1",
    "1:4",
    "8:1",
    "1:8",
]

NANO_RESOLUTIONS = ["0.5K", "1K", "2K", "4K"]

SAFETY_TOLERANCES = ["1", "2", "3", "4", "5", "6"]

# --------------------------------------------------------------------------- #
# Vector models
# --------------------------------------------------------------------------- #

VECTOR_ENDPOINT_T2V = "fal-ai/recraft/v3/text-to-image"
VECTOR_ENDPOINT_TRACE = "fal-ai/recraft/vectorize"

VECTOR_STYLES = [
    ("Vector illustration", "vector_illustration"),
    ("Bold stroke", "vector_illustration/bold_stroke"),
    ("Line art", "vector_illustration/line_art"),
    ("Line circuit", "vector_illustration/line_circuit"),
    ("Engraving", "vector_illustration/engraving"),
    ("Linocut", "vector_illustration/linocut"),
    ("Mosaic", "vector_illustration/mosaic"),
    ("Colored stencil", "vector_illustration/colored_stencil"),
    ("Cutout", "vector_illustration/cutout"),
    ("Contour pop art", "vector_illustration/contour_pop_art"),
    ("Editorial", "vector_illustration/editorial"),
    ("Emotional flat", "vector_illustration/emotional_flat"),
    ("Infographical", "vector_illustration/infographical"),
    ("Marker outline", "vector_illustration/marker_outline"),
    ("Naivector", "vector_illustration/naivector"),
    ("Roundish flat", "vector_illustration/roundish_flat"),
    ("Segmented colors", "vector_illustration/segmented_colors"),
    ("Sharp contrast", "vector_illustration/sharp_contrast"),
    ("Thin line", "vector_illustration/thin"),
    ("Vector photo", "vector_illustration/vector_photo"),
    ("Vivid shapes", "vector_illustration/vivid_shapes"),
    ("Digital — pixel art", "digital_illustration/pixel_art"),
    ("Digital — hand drawn", "digital_illustration/hand_drawn"),
    ("Digital — pop art", "digital_illustration/pop_art"),
]

VECTOR_SIZE_MAP = {
    "Square (1024²)": "square_hd",
    "Landscape 4:3": "landscape_4_3",
    "Landscape 16:9": "landscape_16_9",
    "Portrait 4:3": "portrait_4_3",
    "Portrait 16:9": "portrait_16_9",
}

# --------------------------------------------------------------------------- #
# Enhancement models
# --------------------------------------------------------------------------- #

REMOVE_BG_ENDPOINT = "fal-ai/ideogram/remove-background"
REMOVE_BG_PRICING = "$0.01 per image."

UPSCALE_MODELS: list[dict[str, Any]] = [
    {
        "id": "recraft-creative",
        "label": "Recraft — Creative upscale",
        "endpoint": "fal-ai/recraft/upscale/creative",
        "tagline": "Adds crisp, imagined detail while keeping the subject faithful.",
        "pricing": "$0.25 per image.",
        "engine": "recraft",
    },
    {
        "id": "topaz-generative",
        "label": "Topaz — generative upscale",
        "endpoint": "fal-ai/topaz/upscale/image",
        "tagline": "Topaz enhancer with generative models, face recovery and cleanup.",
        "pricing": "From $0.08 per image depending on output size.",
        "engine": "topaz",
    },
]

TOPAZ_MODELS = [
    "Standard V2",
    "High Fidelity V2",
    "Low Resolution V2",
    "CGI",
    "Text Refine",
    "Wonder 3",
    "Standard MAX",
    "Redefine",
    "Recovery V2",
]

# --------------------------------------------------------------------------- #
# Speech models
# --------------------------------------------------------------------------- #

TTS_ENDPOINT = "fal-ai/elevenlabs/tts/multilingual-v2"
TTS_PRICING = "$0.10 per 1,000 characters."
STT_ENDPOINT = "fal-ai/elevenlabs/speech-to-text/scribe-v2"
STT_PRICING = "$0.008 per input audio minute."

TTS_VOICES = [
    "Rachel",
    "Aria",
    "Roger",
    "Sarah",
    "Laura",
    "Charlie",
    "George",
    "Callum",
    "River",
    "Liam",
    "Charlotte",
    "Alice",
    "Matilda",
    "Will",
    "Jessica",
    "Eric",
    "Chris",
    "Brian",
    "Daniel",
    "Lily",
    "Bill",
]

TEXT_NORMALIZATION = ["auto", "on", "off"]


def model_by_id(model_id: str) -> dict[str, Any]:
    return IMAGE_MODELS_BY_ID[model_id]

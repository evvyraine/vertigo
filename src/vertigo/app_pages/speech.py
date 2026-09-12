"""Speech — ElevenLabs text-to-speech and Scribe transcription."""

from __future__ import annotations

import streamlit as st

from vertigo import config, fal, i18n, naming, ui
from vertigo.jobs import SAVE_AUDIO, SAVE_TRANSCRIPT

library = ui.current_library()
manager = ui.current_manager()

TTS = "tts"
STT = "stt"


def _queue_tts(arguments: dict) -> None:
    job_id = manager.submit(
        kind="tts",
        label=i18n.t("jobs.label.tts", voice=arguments.get("voice", "")),
        endpoint=config.TTS_ENDPOINT,
        arguments=arguments,
        save_kind=SAVE_AUDIO,
        name_hint=naming.slugify(str(arguments.get("text", ""))),
    )
    st.session_state.speech_jobs.insert(0, job_id)
    st.toast(i18n.t("toast.speech_queued"), icon=":material/queue:")


def _queue_transcription(asset, arguments: dict) -> None:
    try:
        url = fal.ensure_remote_url(asset, library)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user
        st.error(i18n.t("error.prepare_asset", name=asset.name, error=exc))
        return
    job_id = manager.submit(
        kind="stt",
        label=i18n.t("jobs.label.stt", name=asset.name),
        endpoint=config.STT_ENDPOINT,
        arguments={**arguments, "audio_url": url},
        save_kind=SAVE_TRANSCRIPT,
        parent_id=asset.id,
    )
    st.session_state.speech_jobs.insert(0, job_id)
    st.toast(i18n.t("toast.transcribe_queued"), icon=":material/queue:")


ui.key_ready()

tts_label = i18n.t("speech.mode_tts")
stt_label = i18n.t("speech.mode_stt")
mode = st.segmented_control(
    "speech_mode",
    [TTS, STT],
    default=TTS,
    format_func=lambda value: tts_label if value == TTS else stt_label,
    key="speech_mode",
    label_visibility="collapsed",
)

left, right = st.columns([2, 3], gap="large")

with left:
    if mode == STT:
        asset = ui.audio_picker(library, key="stt_source", label=i18n.t("speech.audio"))
        st.caption(i18n.t("speech.stt_caption"))
        st.caption(i18n.t("models.stt.pricing"))

        language = st.text_input(
            i18n.t("speech.language"),
            placeholder="eng, spa, fra…",
            key="stt_language",
        )
        diarize = st.toggle(i18n.t("speech.diarize"), value=True, key="stt_diarize")
        tag_events = st.toggle(i18n.t("speech.events"), value=True, key="stt_events")
        keyterms_raw = st.text_input(
            i18n.t("speech.keyterms"),
            key="stt_keyterms",
            help=i18n.t("speech.keyterms_help"),
        )

        arguments: dict = {"diarize": diarize, "tag_audio_events": tag_events}
        if language.strip():
            arguments["language_code"] = language.strip()
        keyterms = [term.strip() for term in keyterms_raw.split(",") if term.strip()]
        if keyterms:
            arguments["keyterms"] = keyterms

        if st.button(
            i18n.t("speech.transcribe"),
            type="primary",
            icon=":material/speech_to_text:",
            disabled=not (fal.has_key() and asset),
            key="stt_go",
        ):
            if asset is not None:
                _queue_transcription(asset, arguments)
    else:
        text = st.text_area(
            i18n.t("speech.text"),
            height=180,
            key="tts_text",
            placeholder=i18n.t("speech.text_placeholder"),
        )
        voice = st.selectbox(i18n.t("speech.voice"), config.TTS_VOICES, key="tts_voice")
        with st.expander(i18n.t("speech.delivery"), expanded=False):
            stability = st.slider(
                i18n.t("speech.stability"), 0.0, 1.0, 0.5, 0.05, key="tts_stability"
            )
            similarity = st.slider(
                i18n.t("speech.similarity"), 0.0, 1.0, 0.75, 0.05, key="tts_similarity"
            )
            style = st.slider(i18n.t("speech.style"), 0.0, 1.0, 0.0, 0.05, key="tts_style")
            speed = st.slider(i18n.t("speech.speed"), 0.7, 1.2, 1.0, 0.05, key="tts_speed")
            language = st.text_input(i18n.t("speech.language"), key="tts_language")
            normalization = st.selectbox(
                i18n.t("speech.normalization"),
                config.TEXT_NORMALIZATION,
                index=0,
                key="tts_normalization",
            )

        characters = len(text.strip())
        st.caption(
            i18n.t(
                "speech.characters",
                chars=f"{characters:,}",
                cost=f"{characters / 1000 * 0.10:.3f}",
                pricing=i18n.t("models.tts.pricing"),
            )
        )

        if st.button(
            i18n.t("speech.generate"),
            type="primary",
            icon=":material/text_to_speech:",
            disabled=not (fal.has_key() and text.strip()),
            key="tts_go",
        ):
            arguments = {
                "text": text.strip(),
                "voice": voice,
                "stability": stability,
                "similarity_boost": similarity,
                "style": style,
                "speed": speed,
                "apply_text_normalization": normalization,
            }
            if language.strip():
                arguments["language_code"] = language.strip()
            _queue_tts(arguments)

with right:
    ui.jobs_panel(st.session_state.speech_jobs)

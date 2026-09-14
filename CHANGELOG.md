# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Hosting guide (`docs/hosting.md`), Dockerfile and `docker-compose.yml`.
- Smoke tests and a GitHub Actions CI matrix for Python 3.11–3.14.
- `CONTRIBUTING.md` and this changelog.

### Changed

- Broaden `requires-python` from 3.14 to **3.11+**.
- `secrets.toml` is now written next to the running app (configurable via
  `VERTIGO_SECRETS_DIR`) and **merged** with existing content instead of being
  overwritten, so a hand-written `FAL_KEY` is preserved.
- Add package metadata: license, classifiers, keywords and project URLs.

## [0.1.0] - 2026-09-13

### Added

- Initial public release: image generation and editing, vector art, upscaling,
  background removal, text-to-speech and transcription, all on fal.ai.
- Per-profile libraries, PIN sign-in and optional Telegram (OIDC) sign-in.
- Local, file-backed media library and background job queue.
- Installable PWA and an English/Russian interface.

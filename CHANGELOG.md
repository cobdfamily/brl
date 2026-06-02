# Changelog

All notable changes to brl. Format roughly follows
[Keep a Changelog](https://keepachangelog.com); dates
are ISO 8601 in UTC.

Pre-existing release tags (if any) are still visible
via `git log --tags --oneline`; this file starts
empty and is filled forward from this point.

## [Unreleased]

## [1.1.1] - 2026-06-01

### Fixed
- `/v1/backtranslate` failed at runtime with exit 127
  (`lou_translate: command not found`). 1.1.0 assumed
  `liblouis-bin` was a transitive dependency of
  `liblouisutdml-bin`, but the latter pulls the liblouis shared
  library, not the `-bin` CLI package. The Dockerfile now
  installs `liblouis-bin` explicitly (provides `lou_translate`).
  Surfaced by the e2e round-trip; 1.1.0's back-translation was
  non-functional.

### Changed
- `api.version` `1.1.0 -> 1.1.1`.

## [1.1.0] - 2026-06-01

### Added
- **Braille → print back-translation** at
  `POST /v1/backtranslate`. Uploaded braille is back-translated
  to print text via liblouis core's `lou_translate --backward`
  and returned inline in the response `stdout`. Slug → table
  resolution mirrors `/translate` (same `text` upload + `table`
  validation). New `bin/brl-backtranslate` wrapper — a pure
  stdin→stdout filter, so it's safe under the hardened
  read-only-root container. Round-trips cleanly on uncontracted
  grade-1 tables; contracted (grade-2) tables back-translate but
  may not reproduce the exact source. file2brl itself stays
  forward-only.

### Changed
- `api.version` `1.0.0 -> 1.1.0`.

## [1.0.0] - 2026-06-01

First tagged release of brl. Captures the existing surface
plus this sprint's standardization work.

### Added
- Print-to-braille translation over HTTP, wrapping liblouis
  `file2brl`: inline translation, a downloadable `.brf`
  variant, and a curated slug catalog (`config/tables.yaml`)
  served as a discovery endpoint. Full surface in README.md.
- `api.version "1.0.0"` — `GET /` liveness now reports brl's
  own identity instead of the engine version (Sprint 1).
- Daily Grype CVE scan (`.github/workflows/cve-scan.yml`) over
  the image's oras-attached CycloneDX SBOM; findings to the
  GitHub Security tab (Sprint 4).

### Changed
- Pinned the url2code base image to `1.0.8` (was the floating
  `latest`) for reproducible builds (Sprint 1).
- Hardened `docker-compose.yaml`: read-only root, tmpfs `/tmp`,
  `cap_drop: ALL`, `no-new-privileges` (Sprint 4).

[1.1.1]: https://github.com/cobdfamily/brl/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/cobdfamily/brl/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/cobdfamily/brl/commits/v1.0.0

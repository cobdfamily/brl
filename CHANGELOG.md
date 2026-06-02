# Changelog

All notable changes to brl. Format roughly follows
[Keep a Changelog](https://keepachangelog.com); dates
are ISO 8601 in UTC.

Pre-existing release tags (if any) are still visible
via `git log --tags --oneline`; this file starts
empty and is filled forward from this point.

## [Unreleased]

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

[1.0.0]: https://github.com/cobdfamily/brl/commits/v1.0.0

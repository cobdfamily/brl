"""End-to-end tests for brl.

Assumes the docker-compose stack at the repo root is up and
reachable at http://localhost:8000. The CI workflow builds the
image locally and brings the stack up before invoking pytest;
locally, ``docker compose up -d`` is enough.

Coverage:

  /                         liveness (service field, version)
  GET /tables               returns the curated catalog
  POST /translate           inline braille text in the JSON
                            response (uses en-ueb-g2 slug)
  POST /translate/file      braille .brf via download_url
                            (uses en-ueb-g2 slug)
  POST /translate (bad)     unknown slug -> non-zero exit,
                            error message in body

Braille output checks are deliberately loose: just that the
translated bytes are non-empty and different from the input,
so a future liblouis table revision (a different glyph for a
contraction, say) doesn't break CI.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import requests

BRL_BASE_URL = os.environ.get("BRL_BASE_URL", "http://localhost:8000")

# A short ASCII source that exercises a couple of UEB grade-2
# contractions (the 'and' and 'the' should compress); deliberately
# chosen to make the print-vs-braille byte difference obvious.
SAMPLE_TEXT = "The quick brown fox jumps over the lazy dog and runs away.\n"


@pytest.fixture(scope="module")
def source_text(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("text") / "source.txt"
    path.write_text(SAMPLE_TEXT, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# liveness — the / endpoint brl inherits from url2code
# ---------------------------------------------------------------------------


def test_liveness_returns_brl_service():
    """``/`` reports ``service: brl`` (not ``url2code``).
    The api.title -> service field wiring landed in
    url2code 1.0.6; this test pins the inheritance."""
    r = requests.get(BRL_BASE_URL + "/", timeout=5)
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "brl"
    assert body["status"] == "ok"
    assert body["version"]


# ---------------------------------------------------------------------------
# /tables — discovery
# ---------------------------------------------------------------------------


def test_tables_returns_curated_catalog():
    """GET /tables returns the catalog as parsed_output:
    a list of {slug, table, name} entries. Without it
    consumers can't discover valid slugs."""
    r = requests.get(BRL_BASE_URL + "/tables", timeout=5)
    assert r.status_code == 200, r.text
    body = r.json()
    catalog = body.get("parsed_output")
    assert isinstance(catalog, list)
    assert len(catalog) >= 1
    # Every entry has the documented shape.
    for entry in catalog:
        assert {"slug", "table", "name"} <= set(entry.keys())
    # The slug used by the rest of these tests must be in
    # the catalog -- otherwise the wrapper will reject it.
    slugs = [e["slug"] for e in catalog]
    assert "en-ueb-g2" in slugs


# ---------------------------------------------------------------------------
# /translate — inline (braille text in the JSON response)
# ---------------------------------------------------------------------------


def test_translate_inline_returns_braille_output(source_text):
    """POST /translate with a simple English source and the
    en-ueb-g2 slug. Expect the braille text in the
    response's `stdout` field — non-empty, distinct from
    the source."""
    with open(source_text, "rb") as f:
        r = requests.post(
            BRL_BASE_URL + "/translate",
            data={"table": "en-ueb-g2"},
            files={"text": ("source.txt", f, "text/plain")},
            timeout=60,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("exit_code") == 0, body

    output = body.get("stdout") or ""
    assert output, "translate returned empty stdout"
    # Translation should produce something different from
    # the input -- file2brl is doing actual work.
    assert output.strip() != SAMPLE_TEXT.strip(), \
        "output identical to input -- translation didn't happen"


def test_translate_inline_honours_cellsperline(source_text):
    """Cog passthrough: setting cellsPerLine should produce
    visibly narrower lines than the default of 40. Pinned
    because a regression in the flag wiring (e.g.
    valuePrefix dropped) would silently push the default
    to file2brl."""
    with open(source_text, "rb") as f:
        wide = requests.post(
            BRL_BASE_URL + "/translate",
            data={"table": "en-ueb-g2", "cellsPerLine": "80"},
            files={"text": ("source.txt", f, "text/plain")},
            timeout=60,
        )
    assert wide.status_code == 200, wide.text
    wide_body = wide.json()
    assert wide_body.get("exit_code") == 0, wide_body

    with open(source_text, "rb") as f:
        narrow = requests.post(
            BRL_BASE_URL + "/translate",
            data={"table": "en-ueb-g2", "cellsPerLine": "20"},
            files={"text": ("source.txt", f, "text/plain")},
            timeout=60,
        )
    assert narrow.status_code == 200, narrow.text
    narrow_body = narrow.json()
    assert narrow_body.get("exit_code") == 0, narrow_body

    # Same source + same table; only cellsPerLine differs.
    # Narrow output must have at least as many lines as wide.
    wide_lines = (wide_body["stdout"] or "").splitlines()
    narrow_lines = (narrow_body["stdout"] or "").splitlines()
    assert len(narrow_lines) > len(wide_lines), \
        f"narrow ({len(narrow_lines)}) didn't produce more lines than wide ({len(wide_lines)}) -- cog flag wiring is suspect"


# ---------------------------------------------------------------------------
# /translate/file — download_url variant
# ---------------------------------------------------------------------------


def test_translate_file_returns_downloadable_brf(source_text):
    """POST /translate/file -> response carries a
    download_url; GET it and verify the bytes are non-empty
    and not the source text."""
    with open(source_text, "rb") as f:
        r = requests.post(
            BRL_BASE_URL + "/translate/file",
            data={"table": "en-ueb-g2"},
            files={"text": ("source.txt", f, "text/plain")},
            timeout=60,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("exit_code") == 0, body

    output_files = body.get("output_files") or {}
    entry = output_files.get("output_path")
    assert entry, f"missing output_path entry: {body}"

    download_url = entry.get("download_url")
    assert download_url, f"missing download_url: {entry}"
    if download_url.startswith("/"):
        download_url = BRL_BASE_URL + download_url

    r2 = requests.get(download_url, timeout=30)
    assert r2.status_code == 200, r2.text
    converted = r2.content
    assert len(converted) > 0, "downloaded .brf is empty"
    # Distinct from the source bytes -- translation happened.
    assert converted.strip() != SAMPLE_TEXT.encode("utf-8").strip(), \
        "downloaded .brf identical to input"


# ---------------------------------------------------------------------------
# error path — unknown slug rejected by the wrapper
# ---------------------------------------------------------------------------


def test_translate_rejects_unknown_slug(source_text):
    """The wrapper validates the slug against tables.yaml
    and exits 64 (EX_USAGE) if it's missing. url2code
    surfaces a non-zero exit_code and the wrapper's stderr
    in the response so the caller sees the issue."""
    with open(source_text, "rb") as f:
        r = requests.post(
            BRL_BASE_URL + "/translate",
            data={"table": "this-slug-does-not-exist"},
            files={"text": ("source.txt", f, "text/plain")},
            timeout=30,
        )
    # url2code returns 502 on non-zero exit + text mode, OR
    # 200 with exit_code != 0 -- depends on the version.
    # Accept either, but require the error to mention the
    # slug being unknown.
    body_text = r.text.lower()
    assert "unknown" in body_text or "slug" in body_text, \
        f"missing slug-error message in body: {r.text[:300]}"

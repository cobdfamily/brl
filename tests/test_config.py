"""Static checks on config/tools.yaml + config/tables.yaml.

brl has no Python source of its own — the HTTP surface is
declared in config/tools.yaml and the table catalog lives in
config/tables.yaml. These tests pin both shapes so a
careless edit can't ship a malformed config or a catalog
that drifts from the YAML.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS_YAML = REPO_ROOT / "config" / "tools.yaml"
TABLES_YAML = REPO_ROOT / "config" / "tables.yaml"


@pytest.fixture(scope="module")
def cfg():
    return yaml.safe_load(TOOLS_YAML.read_text())


@pytest.fixture(scope="module")
def endpoints(cfg):
    return cfg["endpoints"]


@pytest.fixture(scope="module")
def by_name(endpoints):
    return {e["name"]: e for e in endpoints}


@pytest.fixture(scope="module")
def catalog():
    return yaml.safe_load(TABLES_YAML.read_text())


# ---------------------------------------------------------------------------
# top-level shape
# ---------------------------------------------------------------------------


def test_yaml_parses(cfg):
    assert isinstance(cfg, dict)
    assert "endpoints" in cfg
    assert isinstance(cfg["endpoints"], list)


def test_top_level_metadata(cfg):
    assert cfg["api"]["title"] == "brl"
    assert cfg["api"]["default_root"] == "/"
    assert cfg["logging"]["level"] in {"DEBUG", "INFO", "WARNING", "ERROR"}


def test_three_endpoints_exact(by_name):
    """The surface is exactly: translate, translate-file,
    tables. New additions go here in lockstep with their
    YAML."""
    assert set(by_name) == {"translate", "translate-file", "tables"}


def test_routes_are_unique(endpoints):
    pairs = [(e.get("method", "GET"), e["route"]) for e in endpoints]
    assert len(pairs) == len(set(pairs)), f"duplicate routes: {pairs}"


# ---------------------------------------------------------------------------
# tables.yaml catalog
# ---------------------------------------------------------------------------


def test_catalog_parses(catalog):
    """tables.yaml must be a list of {slug, table, name}
    objects. Anything else and the wrapper's slug
    resolution silently fails at request time."""
    assert isinstance(catalog, list)
    assert len(catalog) >= 1
    for entry in catalog:
        assert isinstance(entry, dict)
        assert set(entry.keys()) >= {"slug", "table", "name"}
        assert isinstance(entry["slug"], str) and entry["slug"]
        assert isinstance(entry["table"], str) and entry["table"]
        assert isinstance(entry["name"], str) and entry["name"]


def test_catalog_slugs_are_unique(catalog):
    slugs = [e["slug"] for e in catalog]
    assert len(slugs) == len(set(slugs)), \
        f"duplicate slugs: {sorted(slugs)}"


def test_catalog_slugs_are_url_safe(catalog):
    """Slugs become the value of the `table` form field —
    keep them URL-safe so callers don't have to encode.
    Letters, digits, underscores, hyphens only; not empty,
    no leading dash."""
    import re
    pattern = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
    for entry in catalog:
        assert pattern.match(entry["slug"]), \
            f"slug {entry['slug']!r} is not URL-safe"


def test_catalog_tables_look_like_liblouis_files(catalog):
    """liblouis tables end in .ctb, .utb, or .tbl. Anything
    else is almost certainly a typo."""
    suffixes = (".ctb", ".utb", ".tbl")
    for entry in catalog:
        assert entry["table"].endswith(suffixes), \
            f"table {entry['table']!r} doesn't look like a " \
            f"liblouis file (slug={entry['slug']})"


# ---------------------------------------------------------------------------
# /translate + /translate/file -- shared shape
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def translate_endpoints(by_name):
    return [by_name["translate"], by_name["translate-file"]]


def test_translate_endpoints_call_wrapper(translate_endpoints):
    """The wrapper is the only binary the translation
    endpoints invoke. file2brl is reached via the wrapper,
    never directly — that's how slug resolution and
    stdout-vs-file mode get applied."""
    for e in translate_endpoints:
        assert e["command"]["executable"] == "/app/bin/brl-translate"


def test_translate_endpoints_pass_table_input_output_args(translate_endpoints):
    """The wrapper takes three positional args followed by
    any -c cog flags. First three are the slug, the input
    path, and the output path (or "-" for stdout)."""
    for e in translate_endpoints:
        args = e["command"]["args"]
        assert len(args) >= 3, \
            f"{e['name']} passes {len(args)} args, expected >= 3"
        assert args[0] == "{table}", \
            f"{e['name']} arg 0 must be the table slug placeholder"
        assert args[1] == "{input_path}", \
            f"{e['name']} arg 1 must be the input placeholder"


def test_translate_endpoints_take_text_upload(translate_endpoints):
    """Both translation endpoints take the same upload
    field so callers don't have to remember which one to
    use. ``text`` is the convention; pin it."""
    for e in translate_endpoints:
        uploads = e.get("uploads") or []
        assert len(uploads) == 1, \
            f"{e['name']} has {len(uploads)} uploads, expected 1"
        upload = uploads[0]
        assert upload["field_name"] == "text"
        assert upload["placeholder"] == "input_path"


def test_translate_endpoints_validate_table(translate_endpoints):
    """`table` is a required text validation -- url2code
    rejects requests missing it before invoking the
    wrapper, which keeps the wrapper's slug-lookup error
    path off the hot path for sloppy callers."""
    for e in translate_endpoints:
        validations = e.get("request", {}).get("validations", {})
        assert "table" in validations, \
            f"{e['name']} missing `table` validation"
        assert validations["table"]["type"] == "text"


def test_translate_endpoints_default_page_geometry(translate_endpoints):
    """cellsPerLine / linesPerPage default so callers
    that don't tune get sensible braille without having
    to know the cogs exist. Default cellsPerLine=40 is
    typical for letter paper at 1/4" grid; 25 lines is
    typical for letter at half spacing."""
    for e in translate_endpoints:
        defaults = e.get("defaults", {})
        assert defaults.get("cellsPerLine") == "40", \
            f"{e['name']} missing cellsPerLine default"
        assert defaults.get("linesPerPage") == "25", \
            f"{e['name']} missing linesPerPage default"


# Each row: (cog name, valuePrefix, url2code type, choices).
# Listed once and consumed by the test below; adding a cog
# means adding a row here AND in both translate endpoint
# blocks in tools.yaml. Drift between the two is what this
# pinning is for.
EXPECTED_COGS = [
    # Page geometry.
    ("cellsPerLine",         "cellsPerLine=",         "number", []),
    ("linesPerPage",         "linesPerPage=",         "number", []),
    # Page numbering.
    ("braillePages",         "braillePages=",         "enum",   ["yes", "no"]),
    ("printPages",           "printPages=",           "enum",   ["yes", "no"]),
    ("pageSeparator",        "pageSeparator=",        "enum",   ["yes", "no"]),
    ("printPageNumberAt",    "printPageNumberAt=",    "enum",   ["top", "bottom"]),
    ("braillePageNumberAt",  "braillePageNumberAt=",  "enum",   ["top", "bottom"]),
    ("printPageNumberRange", "printPageNumberRange=", "enum",   ["yes", "no"]),
    ("continuePages",        "continuePages=",        "enum",   ["yes", "no"]),
    # Table chaining.
    ("contractedTable",      "contractedTable=",      "text",   []),
    ("mathTable",            "mathTable=",            "text",   []),
    ("computerBrailleTable", "computerBrailleTable=", "text",   []),
]


def test_translate_endpoints_use_cog_flag_mapping(translate_endpoints):
    """Every cog in EXPECTED_COGS is wired up the same way
    on both translate endpoints: file2brl's ``-C key=value``
    cog format via url2code's `flag` + `valuePrefix`
    mechanism. file2brl's cog flag is ``-C`` /
    ``--config-setting`` (uppercase) -- ``-c`` is not a flag
    and would fail with "invalid option."

    Drift here silently passes the wrong page geometry,
    skips a numbering toggle, or chains the wrong math
    table -- every kind of regression that's invisible from
    a 200 response."""
    for e in translate_endpoints:
        flags = {f["name"]: f for f in e["request"]["flags"]}
        # Pin the count too so an accidental drop is caught.
        assert len(flags) == len(EXPECTED_COGS), \
            f"{e['name']} has {len(flags)} flags, expected {len(EXPECTED_COGS)}"
        for name, prefix, kind, choices in EXPECTED_COGS:
            assert name in flags, \
                f"{e['name']} missing flag {name!r}"
            assert flags[name]["flag"] == "-C", \
                f"{e['name']}.{name} flag is not -C"
            assert flags[name]["valuePrefix"] == prefix, \
                f"{e['name']}.{name} valuePrefix mismatch"
            assert flags[name]["type"] == kind, \
                f"{e['name']}.{name} type {flags[name]['type']!r} != {kind!r}"
            if kind == "enum":
                assert flags[name].get("choices") == choices, \
                    f"{e['name']}.{name} choices mismatch"


def test_translate_endpoints_use_text_output_mode(translate_endpoints):
    """The wrapper either writes braille to stdout (which
    becomes the `stdout` field) or to a file (which url2code
    serves via download_url). Either way url2code captures
    stdout as text -- no regex / native_json parsing of
    file2brl's output."""
    for e in translate_endpoints:
        assert e["output"]["mode"] == "text"


# ---------------------------------------------------------------------------
# /translate -- inline (stdout) variant
# ---------------------------------------------------------------------------


def test_translate_inline_passes_dash_for_output(by_name):
    """``-`` in the third arg position is the wrapper's
    "write braille to stdout" sentinel. Without it the
    wrapper tries to file2brl into a path called "-",
    which usually works as a file but defeats the inline
    point of this endpoint."""
    e = by_name["translate"]
    assert e["command"]["args"][2] == "-"


def test_translate_inline_has_no_output_files(by_name):
    """Inline mode is strictly stdout; declaring
    output_files would generate a download_url that
    points at nothing."""
    e = by_name["translate"]
    assert not e.get("output_files")


# ---------------------------------------------------------------------------
# /translate/file -- file (download_url) variant
# ---------------------------------------------------------------------------


def test_translate_file_passes_output_placeholder(by_name):
    """File mode passes url2code's generated output_path
    as the wrapper's third arg. Wrapper writes file2brl's
    output to that exact path; url2code serves it via
    download_url."""
    e = by_name["translate-file"]
    assert e["command"]["args"][2] == "{output_path}"


def test_translate_file_declares_brf_output(by_name):
    """The download URL extension is .brf -- the standard
    "Braille Ready File" extension most embossers and
    braille displays expect."""
    e = by_name["translate-file"]
    outputs = e.get("output_files") or []
    assert len(outputs) == 1
    out = outputs[0]
    assert out["placeholder"] == "output_path"
    assert out["filename_placeholder"] == "output_filename"
    assert out["suffix"] == ".brf"


# ---------------------------------------------------------------------------
# /tables -- discovery
# ---------------------------------------------------------------------------


def test_tables_endpoint_is_get(by_name):
    """/tables is a parameter-less, read-only listing —
    GET is the honest verb. POST is the default in url2code
    for tool invocations; this is the exception."""
    e = by_name["tables"]
    assert e["method"] == "GET"


def test_tables_endpoint_returns_native_json(by_name):
    """/tables wraps `cat` over the JSON catalog so the
    response's `parsed_output` is the catalog directly.
    text mode would force callers to re-parse; regex_json
    is wrong for a structured array."""
    e = by_name["tables"]
    assert e["output"]["mode"] == "native_json"


def test_tables_endpoint_reads_catalog_file(by_name):
    """The endpoint runs cat-yaml-as-json on the YAML
    catalog -- drift between the served file and the file
    the wrapper consults means /tables advertises slugs the
    wrapper won't recognize, or vice versa. Pinning the
    wrapper path also catches a stray refactor that switches
    back to /bin/cat (which would emit raw YAML and break
    native_json parsing)."""
    e = by_name["tables"]
    assert e["command"]["executable"] == "/app/bin/cat-yaml-as-json"
    assert e["command"]["args"] == ["/app/config/tables.yaml"]

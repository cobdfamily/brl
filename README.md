# brl

[![test](https://github.com/cobdfamily/brl/actions/workflows/test.yml/badge.svg)](https://github.com/cobdfamily/brl/actions/workflows/test.yml)

A simple print to Braille API.

This is a YAML-defined microservice — no Python source in
the repo, only tests. The HTTP surface lives in
[`config/tools.yaml`](config/tools.yaml) and is consumed
by the upstream `cobdfamily/url2code` engine, which brl's
image is built on top of.

## What it does

```
POST /translate         body: text (multipart),
                              table (slug),
                              cellsPerLine (opt),
                              linesPerPage (opt)
   Translate the uploaded text and return the braille
   inline in the JSON response (`stdout` field).

POST /translate/file    same body shape
   Same translation, but return a download URL pointing
   at a .brf file. Best for callers feeding an embosser.

GET  /tables
   Return the curated catalog of supported translation
   tables. Use the `slug` field of any entry as the
   `table` form param above.
```

## Slugs and the catalog

Consumers reference tables by short, URL-safe slugs (e.g.
`en-ueb-g2`, `nemeth`, `fr-bfu-g2`) -- not by the
`.ctb` / `.utb` filenames liblouis ships. The slug catalog
lives in [`config/tables.yaml`](config/tables.yaml):

```yaml
- slug: en-ueb-g2
  table: en-ueb-g2.ctb
  name: English (Unified English Braille) Grade 2 - contracted
```

The catalog is the source of truth for the slug allowlist.
Adding a new slug means editing this YAML; the wrapper at
`bin/brl-translate` rejects any slug that isn't in the
catalog. liblouis itself ships ~700 .ctb / .utb files; the
catalog curates the subset this deployment exposes. The
on-the-wire format at `/tables` is JSON (the
`bin/cat-yaml-as-json` helper converts at request time)
so consumers don't have to parse YAML.

The current catalog covers English (UEB g1 / g2, US g1 /
g2, GB g2), Nemeth math, French (BFU g1 / g2), German
(g0 / g2), Spanish (g1 / g2), Italian, Portuguese, Dutch,
Russian, Arabic, Greek, Hebrew, and Chinese (Taiwan). See
[`config/tables.yaml`](config/tables.yaml) for the live
list.

## Cogs

`file2brl` accepts `-C key=value` pairs to tune output.
The translation endpoints expose these as request form
fields; url2code's `flag` + `valuePrefix` mechanism turns
each `?key=value` into a `-C key=value` arg.

Page geometry:

- `cellsPerLine` (number, default 40) -- characters per line.
- `linesPerPage` (number, default 25) -- lines per page.

Page numbering (all enums; values are file2brl's literal
`yes` / `no` and `top` / `bottom`):

- `braillePages` (yes/no) -- emit braille page numbers.
- `printPages` (yes/no) -- emit source page numbers.
- `pageSeparator` (yes/no) -- separator line between pages.
- `printPageNumberAt` (top/bottom) -- where the print page
  number sits in the header/footer.
- `braillePageNumberAt` (top/bottom) -- same for braille.
- `printPageNumberRange` (yes/no) -- show ranges instead
  of single numbers.
- `continuePages` (yes/no) -- continue numbering across
  page breaks.

Table chaining (each value is a liblouis filename in
`/usr/share/liblouis/tables/`):

- `contractedTable` -- override the contracted table.
- `mathTable` -- math table to chain (e.g. `nemeth.ctb`).
- `computerBrailleTable` -- 8-dot computer braille
  (e.g. `en-us-comp8.ctb`).

Adding more cogs is a `tools.yaml` edit -- file2brl
accepts ~30 cogs total; this is the most-used subset.
The wrapper itself is cog-agnostic.

## Quick start

```sh
docker compose up -d

# Discover available tables.
curl -s http://localhost:8000/v1/tables | jq '.parsed_output[].slug'

# Translate a Word doc-shaped plain text to UEB grade 2.
curl -fsS -X POST \
     -F text=@./report.txt \
     -F table=en-ueb-g2 \
     http://localhost:8000/v1/translate | jq -r .stdout

# Get a downloadable .brf for an embosser.
curl -fsS -X POST \
     -F text=@./report.txt \
     -F table=en-ueb-g2 \
     -F cellsPerLine=40 \
     -F linesPerPage=25 \
     http://localhost:8000/v1/translate/file | jq -r '.output_files.output_path.download_url'
# Then GET that URL to retrieve the .brf bytes.
```

## How translation works

1. url2code receives the multipart upload, writes it to
   `/tmp/brl/uploads/<random>.txt`.
2. url2code resolves any `cellsPerLine` / `linesPerPage`
   form fields into `-c key=value` args via its `flag` +
   `valuePrefix` rendering.
3. url2code invokes
   `/app/bin/brl-translate <slug> <input> <output> [-c ...]`.
4. The wrapper resolves the slug to a liblouis table file
   via `config/tables.yaml`, then invokes
   `file2brl -c literaryTextTable=<table> [-c ...] <input> [<output>]`.
5. For `/translate`, the wrapper passes `-` as the output
   path so file2brl writes braille to stdout; url2code
   captures stdout into the `stdout` field of the JSON
   response.
6. For `/translate/file`, the wrapper passes a real path;
   url2code serves the file via `FileResponse` and
   advertises a `download_url` in the response body.

## What it doesn't do

- **No auth.** Gate the service at your reverse proxy
  (Traefik / nginx) — see DEPLOYMENT.md.
- **No persistence.** Uploads and converted outputs live
  in `/tmp` and are wiped on container restart.
- **No back-translation.** file2brl is one-way (print →
  braille). For braille → print, point a downstream
  service at `lou_back_translate` instead.
- **No semantic-XML markup.** file2brl can do more than
  this service exposes (heading styles, emphasis,
  multi-volume layout); brl wires up the plain-text path
  only. Operators with bespoke needs should ship a
  downstream image with their own wrapper.

## Files

```
config/tools.yaml             # the entire HTTP surface
config/tables.yaml            # slug -> liblouis-table catalog
bin/brl-translate             # shell wrapper: slug resolution + stdout/file
Dockerfile                    # url2code base + liblouis-bin + liblouis-data
docker-compose.yaml           # local-dev / production-shape compose
tests/test_config.py          # YAML + catalog structural tests
tests/test_e2e.py             # docker-compose round-trip tests
.github/workflows/test.yml    # CI: yaml + e2e jobs (+ nightly)
.github/workflows/release.yml # CI: tag-driven multi-arch build/push
```

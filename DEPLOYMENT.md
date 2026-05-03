# Deployment

brl ships as a container image to the kibble registry on
every `git tag v*`. The image is built on top of
`cobdfamily/url2code:<tag>` and adds:

- `liblouis-bin` (`apt-get`) — the `file2brl` binary
- `liblouis-data` (`apt-get`) — ~700 .ctb / .utb tables
- `config/tools.yaml` — the entire HTTP surface
- `config/tables.json` — curated slug -> table catalog
- `bin/brl-translate` — shell wrapper that bridges
  url2code's request shape and file2brl's CLI

No Python source is added; the runtime is url2code's
FastAPI engine, configured by the YAML.

## Pre-flight checklist

- [ ] Public hostname for brl (e.g. `brl.cobd.ca` or
      `brl.openapis.ca`) with an A record. The service
      speaks plain HTTP on `:8000` behind your reverse
      proxy / TLS terminator.
- [ ] Disk space on `/tmp` for uploads + converted
      outputs. Each request writes the input under
      `/tmp/brl/uploads` and the output (file mode only)
      under `/tmp/brl/outputs`. Both are wiped on
      container restart.

## Image distribution

`.github/workflows/release.yml` builds and pushes the
image on every `git tag v*`:

```sh
git tag -a v0.1.0 -m "Release 0.1.0"
git push origin v0.1.0
```

Within a couple of minutes:

- `kibble.apps.blindhub.ca/cobdfamily/brl:0.1.0`
- `kibble.apps.blindhub.ca/cobdfamily/brl:latest`

Multi-arch (amd64 + arm64), matching the fleet.

The image is much smaller than outofoffice's — liblouis
is well under 100 MB on top of the url2code base.

## No built-in auth

Every endpoint is unauthenticated by default. Gate the
service at your reverse proxy if you don't want the
translation API open to the world. Sample nginx snippet:

```nginx
location / {
    if ($http_x_api_key != "$BRL_API_KEY") {
        return 401;
    }
    client_max_body_size 10m;
    proxy_pass http://127.0.0.1:8000;
    proxy_read_timeout 60s;
}
```

For the openapis.ca marketplace shape, see
`infra/docs/auth-strategy.md` in the workspace root.

## Run

```yaml
# /opt/brl/docker-compose.yaml
services:
  brl:
    image: kibble.apps.blindhub.ca/cobdfamily/brl:0.1.0
    container_name: brl
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    # Optional: ship your own catalog without rebuilding.
    # volumes:
    #   - ./tables.json:/app/config/tables.json:ro
```

```sh
mkdir -p /opt/brl
cd /opt/brl
docker compose pull
docker compose up -d
docker compose logs -f brl
```

Behind your TLS reverse proxy, route
`https://brl.cobd.ca/*` to `127.0.0.1:8000`.

## Verify

```sh
# Liveness — service / status / version:
curl -fsS https://brl.cobd.ca/

# Generated OpenAPI docs at /docs and /redocs.

# List supported slugs:
curl -fsS https://brl.cobd.ca/tables | jq '.parsed_output[].slug'

# Translate to UEB grade 2 (inline braille):
curl -fsS -X POST \
  -F text=@./hello.txt \
  -F table=en-ueb-g2 \
  https://brl.cobd.ca/translate | jq -r .stdout

# Translate to a downloadable .brf:
curl -fsS -X POST \
  -F text=@./hello.txt \
  -F table=en-ueb-g2 \
  https://brl.cobd.ca/translate/file | jq
```

## Routine operations

### Upgrading

```sh
git tag -a v0.1.1 -m "Release 0.1.1"
git push origin v0.1.1
# CI builds and pushes.

sed -i 's|brl:[^ ]*|brl:0.1.1|' docker-compose.yaml
docker compose pull
docker compose up -d --no-deps brl
```

### Adding a slug to the catalog

Two paths.

**In-image (rebuild):** edit
[`config/tables.json`](config/tables.json), add an entry,
tag a new release.

```json
{
  "slug": "ja",
  "table": "ja-kantenji.ctb",
  "name": "Japanese (Kantenji)"
}
```

**Out-of-band (no rebuild):** mount your own
`tables.json` over the bundled one. Useful for ops who
want to expose a non-standard slug catalog without
forking the image:

```yaml
services:
  brl:
    volumes:
      - ./my-tables.json:/app/config/tables.json:ro
```

In either case, the `table` field must reference a file
that liblouis-data actually ships. Cross-check by
listing what's installed in the image:

```sh
docker exec brl ls /usr/share/liblouis/tables/ | grep ctb
```

If you need a table liblouis doesn't ship, you'd need to
build a downstream image that drops it into
`/usr/share/liblouis/tables/`.

### Adding a cog

`file2brl` accepts many `-c key=value` cogs beyond
`cellsPerLine` / `linesPerPage` — emphasis behaviour,
hyphenation tables, page numbering, contracted-mode
overrides, etc. Adding one is a `tools.yaml` edit:

```yaml
flags:
  - name: hyphenate
    flag: -c
    valuePrefix: "hyphenate="
    type: bool
  - name: numberedPages
    flag: -c
    valuePrefix: "numberedPages="
    type: bool
```

The wrapper itself is format-agnostic — anything
url2code renders as `-c <key>=<value>` gets forwarded
to file2brl.

### Backups

There is **nothing** to back up. brl is stateless —
uploads and outputs live in `/tmp` and are wiped on
container restart. Consumers persist the converted
bytes; the service does not.

The `tables.json` catalog *is* worth versioning
(it lives in this repo).

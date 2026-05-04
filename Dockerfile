# brl image: cobdfamily/url2code base + liblouis (file2brl).
#
# No Python source in this repo (tests aside). The HTTP surface
# is entirely defined in config/tools.yaml — url2code reads it
# on startup and registers the FastAPI routes from it.
#
# Three endpoints:
#
#   POST /translate         — text in, braille text in JSON out
#   POST /translate/file    — text in, braille file via download_url
#   GET  /tables            — JSON catalog of supported slugs
#
# The catalog at config/tables.yaml maps human-readable slugs
# (e.g. ``en-ueb-g2``) to the actual liblouis ``.ctb`` / ``.utb``
# table filenames. Operators add/remove entries by editing the
# YAML; consumers never see the .ctb taxonomy. /tables serves
# the catalog converted to JSON at request time via the
# bin/cat-yaml-as-json helper.

ARG URL2CODE_TAG=latest
FROM kibble.apps.blindhub.ca/cobdfamily/url2code:${URL2CODE_TAG}

USER root

# Two liblouis-shaped packages:
#
# - liblouisutdml-bin ships file2brl (and xml2brl). file2brl
#   is what brl wraps; without this package the wrapper fails
#   with exit 127 ("command not found").
# - liblouis-data ships the ~700 .ctb / .utb translation
#   tables under /usr/share/liblouis/tables/. file2brl uses
#   these via the literaryTextTable cog the wrapper sets.
#
# liblouis-bin (lou_translate, lou_checktable, ...) is pulled
# in as a transitive dep of liblouisutdml-bin; we don't need
# it explicitly.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        liblouisutdml-bin \
        liblouis-data \
 && rm -rf /var/lib/apt/lists/*

# Pre-create temp tree as root + chown to runtime user so
# upload writes and converted-output writes both succeed
# without further chowns at request time.
RUN mkdir -p /tmp/brl/uploads /tmp/brl/outputs \
 && chown -R url2code:url2code /tmp/brl

# Replace url2code's bundled example tools.yaml with brl's,
# and ship the table catalog alongside it.
COPY --chown=url2code:url2code config /app/config

# Wrapper script that handles slug -> table resolution and
# stdout-vs-file output (see bin/brl-translate for the inline
# rationale).
COPY --chown=url2code:url2code bin /app/bin
RUN chmod 0755 /app/bin/brl-translate

# cat-yaml-as-json is provided by url2code:>=1.0.7 itself
# (lives at /app/bin/cat-yaml-as-json in the base layer);
# this image's bin/ COPY layers on top without clobbering it.
# Used by the /v1/tables discovery endpoint.

USER url2code

# CMD inherited from the base image
# (uvicorn url2code.main:app --host 0.0.0.0 --port 8000) is
# preserved; ENTRYPOINT is unset.

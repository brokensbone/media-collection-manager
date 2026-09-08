#!/usr/bin/env bash
# Build the seeded beets fixture. Outputs fixtures/beets/out/{library.db,owned_rgids.txt}.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p out
docker build -t wantlist-beets-fixture .
docker run --rm -v "$PWD/out:/out" wantlist-beets-fixture
echo
echo "Fixture ready:"
echo "  library.db      -> $PWD/out/library.db   (seed for D2/D5/§14 tests)"
echo "  owned_rgids.txt -> $PWD/out/owned_rgids.txt  (feed to the D0 spike via --owned-file)"

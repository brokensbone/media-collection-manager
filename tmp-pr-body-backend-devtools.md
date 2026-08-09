## Summary

- refresh backend dev-tooling lockfile entries that are actually outdated today
- update `ruff` to `0.16.2`
- update `testcontainers` to `4.15.0`
- note that `mypy` did not move because the earlier issue snapshot was stale and no newer resolvable release is currently available

## Validation

- `nix shell nixpkgs#uv -c sh -lc 'uv sync --frozen && uv run ruff check src tests'`
- `nix shell nixpkgs#uv -c sh -lc 'uv sync --frozen && uv run mypy'`
- `nix shell nixpkgs#uv -c sh -lc 'export LD_LIBRARY_PATH=\"$(nix eval --raw nixpkgs#stdenv.cc.cc.lib.outPath)/lib\"; uv sync --frozen && uv run pytest tests/test_beets_client.py -q'`

## Notes

- I could not run the full backend `pytest` suite on this worker because the Docker-backed tests fail here with `PermissionError: [Errno 13] Permission denied` on the Docker socket.
- Without adding `libstdc++.so.6` to `LD_LIBRARY_PATH`, the beets CLI test also fails on this Nix host because the `lap` wheel cannot load its C++ runtime.

#!/bin/sh
# Stands in for the `beet` CLI in tests: answers `version` (health) and prints a fixed
# owned-release-group dump for `list -a -f '$mb_releasegroupid'` (one blank line included).
case "$1" in
  version) echo "beets 0.0 (fake)"; exit 0 ;;
esac
printf 'rg-owned-1\nrg-owned-2\n\n'

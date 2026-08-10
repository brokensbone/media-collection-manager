#!/usr/bin/env bash
# Run on the orchestrator (fourth) by /opt/deploy/run.sh.
# SSHes to blink to run docker commands
set -euo pipefail

HOST=blink
KEY="${ONWARD_SSH_KEY:?dispatcher must set ONWARD_SSH_KEY}"

rc=0
echo "==> rebuilding wantlist on ${HOST}"
# Quote the whole remote command so git/docker run on blink, not here on fourth.
if ssh -i "${KEY}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
     "edward@${HOST}.int.alcachofa.faith" \
     "cd develop/untitled-music-project/deploy/prod && git pull --ff-only && docker compose build worker api && docker compose up -d"; then
  echo "    ${HOST} ok"
else
  echo "    ${HOST} FAILED" >&2
  rc=1
fi
exit "${rc}"

#!/usr/bin/env bash
# Run on the orchestrator (fourth) by /opt/deploy/run.sh.
# SSHes to blink to run docker commands
set -euo pipefail

HOST=blink
KEY="${ONWARD_SSH_KEY:?dispatcher must set ONWARD_SSH_KEY}"

rc=0
echo "==> rebuilding wantlist on ${h}"
if ssh -i "${KEY}" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
     "edward@${h}.int.alcachofa.faith" cd ~/deploy/untitled-musical-project/deploy/prod && git pull && docker compose up --build; then
  echo "    ${h} ok"
else
  echo "    ${h} FAILED" >&2
  rc=1
fi
exit "${rc}"

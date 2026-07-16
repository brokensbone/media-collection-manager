import os

# testcontainers' ryuk reaper bind-mounts the docker socket, which colima rejects; our
# containers are context-managed (`with ...`), so the reaper is just a safety net.
os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")

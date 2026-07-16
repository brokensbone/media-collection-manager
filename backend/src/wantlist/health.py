import subprocess

from sqlalchemy import Engine, text


def check_postgres(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_beets() -> bool:
    """Confirm the bundled beets is runnable (SPEC §5). Library reachability is surfaced
    by the reconcile job + metrics (§16), not this liveness check."""
    try:
        return subprocess.run(["beet", "version"], capture_output=True, timeout=10).returncode == 0
    except Exception:
        return False

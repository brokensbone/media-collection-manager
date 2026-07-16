import shlex
import subprocess

from sqlalchemy import Engine, text


def check_postgres(engine: Engine) -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def check_beets(command: str) -> bool:
    """Reachable if `<beets command> version` exits 0 (SPEC §5 CLI seam)."""
    try:
        result = subprocess.run(
            [*shlex.split(command), "version"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False

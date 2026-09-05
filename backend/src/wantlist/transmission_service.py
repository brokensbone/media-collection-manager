import subprocess
from dataclasses import dataclass
from typing import Protocol

from .adapters.album_repo import AlbumRepo, TransmissionRow
from .ports.transmission import TransmissionClient


class _Testable(Protocol):
    def test(self) -> None: ...


@dataclass
class CheckResult:
    ok: bool
    detail: str


@dataclass
class ConnectionReport:
    api: CheckResult
    ssh: CheckResult


class TransmissionService:
    """Backs the Transmission page (§12): an on-demand connection test for the RPC API and the
    seedbox SSH, and the full ledger of torrents the app has seen — including ones skipped as
    non-music, so nothing is invisibly dropped."""

    def __init__(
        self,
        *,
        repo: AlbumRepo,
        client: TransmissionClient,
        transfer: _Testable,
        api_configured: bool,
        ssh_configured: bool,
    ) -> None:
        self._repo = repo
        self._client = client
        self._transfer = transfer
        self._api_configured = api_configured
        self._ssh_configured = ssh_configured

    def torrents(self) -> list[TransmissionRow]:
        return self._repo.transmission_ledger()

    def add_torrent(self, metainfo: bytes) -> None:
        if not self._api_configured:
            raise RuntimeError("Transmission RPC is not configured.")
        self._client.add_torrent(metainfo)

    def test(self) -> ConnectionReport:
        return ConnectionReport(api=self._test_api(), ssh=self._test_ssh())

    def _test_api(self) -> CheckResult:
        if not self._api_configured:
            return CheckResult(False, "Not configured — transmission_rpc_url is empty.")
        try:
            self._client.ping()
        except Exception as e:
            return CheckResult(False, _short(e))
        return CheckResult(True, "Connected to the Transmission RPC.")

    def _test_ssh(self) -> CheckResult:
        if not self._ssh_configured:
            return CheckResult(False, "Not configured — transmission_ssh_host is empty.")
        try:
            self._transfer.test()
        except subprocess.CalledProcessError as e:
            return CheckResult(False, (e.stderr or "").strip()[:300] or f"exit {e.returncode}")
        except Exception as e:
            return CheckResult(False, _short(e))
        return CheckResult(True, "SSH to the seedbox succeeded.")


def _short(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"[:300]

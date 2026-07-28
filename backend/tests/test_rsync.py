import subprocess
from typing import Any

from wantlist.adapters.rsync import RsyncTransfer


def _capture(monkeypatch: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["input"] = kwargs.get("input")
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return captured


def test_builds_a_copy_only_rsync_over_ssh(monkeypatch: Any, tmp_path: Any) -> None:
    captured = _capture(monkeypatch)
    RsyncTransfer(host="seedbox", port=2222, user="me", ssh_key="/keys/id").fetch(
        download_dir="/downloads/Album", files=["01.flac", "02.flac"], dest=str(tmp_path / "s")
    )

    argv = captured["argv"]
    assert argv[0] == "rsync"
    # copy-only — seeding must never be disturbed (§12)
    assert "--remove-source-files" not in argv
    assert "--delete" not in argv
    # --old-args: treat --files-from names literally so wildcard chars in a release folder name
    # (e.g. "[FLAC]") aren't glob-expanded on the sender, which pulls in extra files that rsync
    # 3.4 then rejects as "unrequested" and aborts the transfer.
    assert "--old-args" in argv
    # ssh with the configured port + key, headless (no prompts, trust-on-first-use)
    ssh = argv[argv.index("-e") + 1]
    assert ssh == "ssh -p 2222 -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i /keys/id"
    # exact file list on stdin, source is the remote download dir
    assert captured["input"] == "01.flac\n02.flac"
    assert "me@seedbox:/downloads/Album/" in argv


def test_fetch_uses_the_configured_transfer_timeout(monkeypatch: Any, tmp_path: Any) -> None:
    # A multi-GB film can take hours off a slow seedbox; the transfer timeout must be the
    # configured value, not the old hardcoded 30 minutes that failed large files outright.
    captured = _capture(monkeypatch)
    RsyncTransfer(host="h", port=22, user="u", ssh_key="", transfer_timeout=21600).fetch(
        download_dir="/d", files=["a"], dest=str(tmp_path / "s")
    )
    assert captured["timeout"] == 21600


def test_omits_key_flag_when_unset(monkeypatch: Any, tmp_path: Any) -> None:
    captured = _capture(monkeypatch)
    RsyncTransfer(host="h", port=22, user="u", ssh_key="").fetch(
        download_dir="/d", files=["a"], dest=str(tmp_path / "s")
    )
    ssh = captured["argv"][captured["argv"].index("-e") + 1]
    assert ssh == "ssh -p 22 -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

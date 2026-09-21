"""The deliberately small MPD protocol seam used by the radio worker."""

import socket
import time
from typing import BinaryIO, cast


class MpdError(Exception):
    pass


class MpdClient:
    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port

    def load(self, paths: list[str]) -> None:
        """Replace the playlist without starting it."""
        with self._connection() as reader:
            self._command(reader, "clear")
            for path in paths:
                self._command(reader, f"add {self._quote(path)}")

    def refresh_database(self, *, timeout_seconds: float = 300) -> None:
        """Make newly imported music visible before resolving a radio day.

        Beets can have a current catalogue entry before MPD has scanned its file.
        Waiting here avoids clearing the morning queue only to fail part-way through
        adding a schedule containing such a track.
        """
        deadline = time.monotonic() + timeout_seconds
        with self._connection() as reader:
            self._command(reader, "update")
            while True:
                status = self._command(reader, "status")
                if not any(line.startswith("updating_db: ") for line in status):
                    return
                if time.monotonic() >= deadline:
                    raise MpdError("timed out waiting for MPD's music database update")
                time.sleep(1)

    def playlist_paths(self) -> list[str]:
        with self._connection() as reader:
            lines = self._command(reader, "playlistinfo")
        return [line.removeprefix("file: ") for line in lines if line.startswith("file: ")]

    def play(self) -> None:
        with self._connection() as reader:
            self._command(reader, "play")

    def _connection(self) -> BinaryIO:
        try:
            connection = socket.create_connection((self._host, self._port), timeout=10)
        except OSError as exc:
            raise MpdError(f"could not connect to MPD at {self._host}:{self._port}: {exc}") from exc
        reader = cast(BinaryIO, connection.makefile("rwb"))
        greeting = self._readline(reader)
        if not greeting.startswith("OK MPD "):
            reader.close()
            raise MpdError(f"unexpected MPD greeting: {greeting}")
        return reader

    @staticmethod
    def _quote(path: str) -> str:
        return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def _command(self, reader: BinaryIO, command: str) -> list[str]:
        reader.write((command + "\n").encode())
        reader.flush()
        lines: list[str] = []
        while True:
            line = self._readline(reader)
            if line == "OK":
                return lines
            if line.startswith("ACK "):
                raise MpdError(f"MPD rejected {command.split()[0]!r}: {line}")
            lines.append(line)

    @staticmethod
    def _readline(reader: BinaryIO) -> str:
        line = reader.readline()
        if not line:
            raise MpdError("MPD closed the connection")
        return line.decode().rstrip("\n")

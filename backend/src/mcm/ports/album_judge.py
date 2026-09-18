from dataclasses import dataclass
from typing import Protocol

from ..domain.match import MatchTarget


@dataclass
class Judgement:
    """Which album a download is, and how sure. `target` is None for "none of these",
    which is the ordinary answer — most downloads are records MCM has never heard of."""

    target: MatchTarget | None
    confidence: float


class AlbumJudge(Protocol):
    """Decides which of a shortlist of albums a download is a copy of (SPEC §12).

    Retrieval hands over candidates; this answers a question about meaning that string
    similarity cannot: a catalogue number is noise, a deluxe edition is still the same
    record, and in a numbered series (Fabric 99 vs Fabric 19) the number is the whole
    identity. Returns None when the judge is unavailable, so the caller can fall back."""

    def choose(self, *, name: str, candidates: list[MatchTarget]) -> Judgement | None: ...

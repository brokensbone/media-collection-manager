from dataclasses import dataclass
from typing import Protocol


@dataclass
class ReleaseGroupCandidate:
    """One MusicBrainz release-group search hit.

    MusicBrainz's own relevance score is deliberately left behind: it reaches 100 on
    plainly wrong albums once the artist is loosened enough to find anything at all, so
    carrying it would only invite the judgement to lean on it."""

    id: str
    artist: str
    title: str
    first_release_date: str | None = None
    primary_type: str | None = None


@dataclass
class ReleaseGroupJudgement:
    candidate: ReleaseGroupCandidate | None
    probability: float  # how likely the chosen answer is — what resolution gates on
    confidence: float  # how concentrated the distribution is, for logging


class ReleaseGroupJudge(Protocol):
    """Decides which MusicBrainz release group a Spotify album is (SPEC §5).

    Spotify and MusicBrainz name the same record differently: Spotify joins every featured
    artist with commas where MusicBrainz keeps one credit, and may spell an artist in a
    different script entirely. Returns None when the judge is unavailable, so resolution
    can fall back."""

    def choose(
        self, *, artist: str, title: str, candidates: list[ReleaseGroupCandidate]
    ) -> ReleaseGroupJudgement | None: ...

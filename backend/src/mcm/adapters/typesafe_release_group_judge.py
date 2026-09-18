import logging
from typing import Any

from typesafe_sdk import Choice, ChoiceAnswer, TypeSafeClient

from ..ports.release_group_judge import ReleaseGroupCandidate, ReleaseGroupJudgement

log = logging.getLogger(__name__)

NONE = "none of these"

INSTRUCTIONS: dict[str, Any] = {
    "judgement": (
        "An album is known by its Spotify artist and title. The options are MusicBrainz "
        "release groups returned by a search. Which one, if any, is the same record?"
    ),
    "the two catalogues differ": (
        "Spotify joins every credited artist with commas — featured artists, remixers, "
        "orchestras, conductors — where MusicBrainz often keeps a single credit, or "
        "orders them differently. Expect one side to name more artists than the other. "
        "An artist may also be spelled in a different script or language: 坂本龍一 and "
        "Ryuichi Sakamoto are one person, and a classical composer may be credited as "
        "the artist on one side and named only in the title on the other."
    ),
    "titles differ too": (
        "A title may carry a translation or subtitle in brackets on one side and not the "
        "other, differ in punctuation or capitalisation, or be transliterated."
    ),
    "still the same record": (
        "A different edition, remaster, reissue, or a release in another country is the "
        "same release group."
    ),
    "not the same record": (
        "A different album by the same artist is not a match. Nor is a different work "
        "that merely shares a composer, a performer, or a common word in its title — "
        "two collections of the same composer's masses by different ensembles are "
        "different records."
    ),
    "when nothing fits": (
        f"Choose '{NONE}' when none of the options is this album. A search loose enough "
        "to find anything returns near-misses with high relevance scores, so a confident-"
        "looking option can still be the wrong record."
    ),
}


class TypeSafeReleaseGroupJudge:
    """Picks the release group for a Spotify album with a System One Choice (SPEC §5, §14).

    One request per album, only on the text tier — the barcode tier is exact and needs no
    judgement. Returns None on any API failure so resolution falls back."""

    def __init__(self, *, api_key: str, model: str | None = None, timeout: float = 30.0):
        self._client = TypeSafeClient(api_key=api_key, model=model or None, timeout=timeout)

    @staticmethod
    def _labels(candidates: list[ReleaseGroupCandidate]) -> dict[str, ReleaseGroupCandidate]:
        """Readable option keys, since the model sees them. MusicBrainz genuinely holds
        distinct release groups with the same artist and title, so ties take the id."""
        out: dict[str, ReleaseGroupCandidate] = {}
        for c in candidates:
            parts = [f"{c.artist} — {c.title}"]
            if c.first_release_date:
                parts.append(f"({c.first_release_date[:4]})")
            if c.primary_type:
                parts.append(f"[{c.primary_type}]")
            label = " ".join(parts)
            if label in out:
                label = f"{label} {c.id[:8]}"
            out[label] = c
        return out

    def choose(
        self, *, artist: str, title: str, candidates: list[ReleaseGroupCandidate]
    ) -> ReleaseGroupJudgement | None:
        if not candidates:
            return ReleaseGroupJudgement(None, 1.0, 1.0)

        by_label = self._labels(candidates)
        criteria: dict[str, Any] = dict.fromkeys(by_label)
        criteria[NONE] = "none of the options is this album"

        try:
            response = self._client.system_one(
                state={"spotify_artist": artist, "spotify_title": title},
                questions={"release_group": Choice(instructions=INSTRUCTIONS, criteria=criteria)},
            )
        except Exception:  # noqa: BLE001 - any API failure falls back to the score gate
            log.warning("release-group judge unavailable; falling back", exc_info=True)
            return None

        answer = response.answers["release_group"]
        if not isinstance(answer, ChoiceAnswer):
            return None
        return ReleaseGroupJudgement(
            by_label.get(answer.choice),
            answer.probabilities.get(answer.choice, 0.0),
            answer.confidence,
        )

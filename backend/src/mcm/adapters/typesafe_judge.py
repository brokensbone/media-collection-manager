import logging
from typing import Any

from typesafe_sdk import Choice, ChoiceAnswer, TypeSafeClient

from ..domain.match import MatchTarget
from ..ports.album_judge import Judgement

log = logging.getLogger(__name__)

NONE = "none of these"

# Everything the old character-ratio matcher tried to encode as noise lists and gates,
# said once, as meaning. Structured because the boundary between "same record, different
# edition" and "different record by the same artist" needs both sides spelling out.
INSTRUCTIONS: dict[str, Any] = {
    "judgement": (
        "A music download has finished. Its name is a folder or torrent name, not clean "
        "metadata. Which album in the list, if any, is this download a copy of?"
    ),
    "the name is noisy": (
        "Expect release-group tags, file formats, bitrates, catalogue numbers, label "
        "names, years, source tags and underscores for spaces. None of that says which "
        "record it is. The artist and album name may be abbreviated, reordered, "
        "lower-cased, missing their articles, or spelled with different punctuation."
    ),
    "still the same record": (
        "A deluxe, remastered, expanded, anniversary or reissued edition is the same album "
        "as the plain one. So is a different pressing, a different country's release, or a "
        "copy with bonus tracks."
    ),
    "not the same record": (
        "A different album by the same artist is not a match, however much of the name they "
        "share. Nor is a single or EP that shares its name with an album, a live recording "
        "of a studio album, or a remix album of it."
    ),
    "numbered series": (
        "Some records belong to a numbered series — Fabric, FabricLive, DJ-Kicks, Late "
        "Night Tales, and sequels like a second or third album sharing the artist's name. "
        "There the number is the whole identity: Fabric 99 and Fabric 19 are different "
        "records, and so are FabricLive 92 and FabricLive 93. Treat a disagreeing number as "
        "decisive, not as a small difference."
    ),
    "compilations": (
        "A compilation's artist is often just 'Various Artists' or 'VA', which identifies "
        "nothing. For those, the title carries the whole identity."
    ),
    "when nothing fits": (
        f"Most downloads are records nobody has listed. Choose '{NONE}' whenever the "
        "download is not one of the albums offered. That is the ordinary answer, not a "
        "failure."
    ),
}


class TypeSafeAlbumJudge:
    """Chooses among retrieved candidates with a System One Choice (SPEC §12, §14).

    One request per download, carrying the candidates as options plus an explicit
    no-match. Returns None on any API failure so detection falls back to the string
    matcher rather than losing the download."""

    def __init__(self, *, api_key: str, model: str | None = None, timeout: float = 30.0):
        self._client = TypeSafeClient(api_key=api_key, model=model or None, timeout=timeout)

    @staticmethod
    def _labels(candidates: list[MatchTarget]) -> dict[str, MatchTarget]:
        """Readable option keys — the model sees them. Deduped, because MCM can hold two
        albums with the same artist and title."""
        out: dict[str, MatchTarget] = {}
        for t in candidates:
            label = f"{t.artist} — {t.title}"
            if label in out:
                label = f"{label} [{t.id}]"
            out[label] = t
        return out

    def choose(self, *, name: str, candidates: list[MatchTarget]) -> Judgement | None:
        if not candidates:
            return Judgement(None, 1.0)

        by_label = self._labels(candidates)
        criteria: dict[str, Any] = dict.fromkeys(by_label)
        criteria[NONE] = "the download is not any of the albums above"

        try:
            response = self._client.system_one(
                state={"download_name": name},
                questions={"match": Choice(instructions=INSTRUCTIONS, criteria=criteria)},
            )
        except Exception:  # noqa: BLE001 - any API failure falls back to the string matcher
            log.warning("album judge unavailable; falling back", exc_info=True)
            return None

        answer = response.answers["match"]
        if not isinstance(answer, ChoiceAnswer):
            return None
        return Judgement(by_label.get(answer.choice), answer.confidence)

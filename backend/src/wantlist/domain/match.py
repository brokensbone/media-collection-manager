import re
from dataclasses import dataclass
from difflib import SequenceMatcher

_NOISE = re.compile(r"[\W_]+")


@dataclass
class MatchTarget:
    id: int
    artist: str
    title: str


def _normalize(text: str) -> str:
    return _NOISE.sub(" ", text).lower().strip()


def best_match(name: str, targets: list[MatchTarget], threshold: float) -> int | None:
    """Fuzzy-match a download folder name against wanted albums (SPEC §12). Returns the id
    of the best-scoring target if it clears `threshold`, else None (the no-match tail — the
    download is still recorded so the operator can hand-import it)."""
    query = _normalize(name)
    best_id: int | None = None
    best_score = threshold
    for t in targets:
        score = SequenceMatcher(None, query, _normalize(f"{t.artist} {t.title}")).ratio()
        if score >= best_score:
            best_score = score
            best_id = t.id
    return best_id


@dataclass
class Candidate:
    key: str  # opaque id of the thing being ranked (e.g. a beets album id)
    artist: str
    title: str


def _score(query: str, c: Candidate) -> float:
    return SequenceMatcher(None, query, _normalize(f"{c.artist} {c.title}")).ratio()


def _tokens(text: str) -> set[str]:
    return set(_normalize(text).split())


def token_search(query: str, candidates: list[Candidate], *, limit: int) -> list[Candidate]:
    """Library search (D17/D21 Mark-owned box): substring, not fuzzy-ratio — every query token
    must appear in the candidate's artist/title, so "mclusky" finds "mclusky — The World…" (a
    ratio would score that short-query-vs-long-title below any useful floor). Best `limit`,
    closest-by-ratio first."""
    qtokens = _tokens(query)
    if not qtokens:
        return []
    qn = _normalize(query)
    matches = [c for c in candidates if qtokens <= _tokens(f"{c.artist} {c.title}")]
    matches.sort(key=lambda c: _score(qn, c), reverse=True)
    return matches[:limit]


def edition_match(query: str, candidates: list[Candidate]) -> Candidate | None:
    """The likely "you already own this, maybe a different edition" match for the Acquire
    hint (SPEC §7, D17). A ratio threshold misfires on short titles with edition suffixes
    ("Want It" vs "Want It (Remaster)"), so use **token containment**: every word of the
    want (artist + title) appears in the candidate — i.e. the owned title is the want plus
    extras like "deluxe"/"remaster". Among containing candidates, the closest by ratio wins."""
    q = _tokens(query)
    if not q:
        return None
    contained = [c for c in candidates if q <= _tokens(f"{c.artist} {c.title}")]
    if not contained:
        return None
    qn = _normalize(query)
    return max(contained, key=lambda c: _score(qn, c))

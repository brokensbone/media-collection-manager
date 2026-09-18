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


# Edition words ignored when checking a title is present, so a plain download still matches a
# "… (Deluxe)"/"… (Remastered)" edition in the funnel.
_EDITION_NOISE = frozenset(
    {
        "deluxe",
        "edition",
        "remaster",
        "remastered",
        "expanded",
        "anniversary",
        "version",
        "reissue",
        "bonus",
        "mono",
        "stereo",
    }
)

# Format/source tokens that are just packaging, not part of an album title — ignored when
# deciding whether a self-titled download carries a *different* album's name.
_FORMAT_NOISE = frozenset(
    {
        "flac",
        "mp3",
        "m4a",
        "aac",
        "ogg",
        "opus",
        "wav",
        "aiff",
        "aif",
        "alac",
        "ape",
        "wv",
        "dsf",
        "dff",
        "mpc",
        "web",
        "webrip",
        "cd",
        "cdrip",
        "vinyl",
        "lp",
        "ep",
        "rip",
        "scene",
        "remux",
    }
)


def best_match(name: str, targets: list[MatchTarget], threshold: float) -> int | None:
    """Fuzzy-match a download folder name against wanted albums (SPEC §12). Returns the id
    of the best-scoring target if it clears `threshold`, else None (the no-match tail — the
    download is still recorded so the operator can hand-import it).

    Gated on the target title actually appearing in the download name, not just overall
    similarity: a shared artist ("Billy Nomates", "BIG SPECIAL") otherwise carries the ratio
    over the threshold and mis-attaches a different album by that artist (Metalhorse -> CACTI),
    or unrelated titles match on incidental characters ("Blur" -> "Film for the Future"). The
    gate uses the title's *distinctive* words (its tokens minus the artist's and edition noise):
    at least half must be in the download name. A self-titled album has no distinctive words, so
    it matches only a download that is itself just the artist — any leftover word (past the
    artist, edition and format noise) means a different album by that artist."""
    query = _normalize(name)
    name_tokens = _tokens(name)
    best_id: int | None = None
    best_score = threshold
    for t in targets:
        artist_tokens = _tokens(t.artist)
        distinct = _tokens(t.title) - artist_tokens - _EDITION_NOISE
        if distinct:
            if len(distinct & name_tokens) / len(distinct) < 0.5:
                continue  # the album's title isn't really in this download name
        else:
            leftover = name_tokens - artist_tokens - _EDITION_NOISE - _FORMAT_NOISE
            if any(w.isalpha() for w in leftover):
                continue  # self-titled album, but the download names a different one
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


# --- broad retrieval, for judgement-based matching (§12) ----------------------

# Words that say nothing about which record a download is: formats, sources, rip
# provenance. Unlike the gates above this list is not load-bearing — a word missing
# from it costs a little retrieval precision, never a wrong match, because choosing
# among the candidates is a separate judgement.
_RETRIEVAL_JUNK = frozenset(
    """
    flac mp3 m4a aac ogg opus wav aiff aif alac ape wv dsf dff mpc
    web webrip cd cdrip vinyl rip scene remux eac log cue
    kbps 16 24 44 48 96 192 320
    """.split()
)

_ARTICLES = frozenset({"the", "a", "an", "and", "of"})


@dataclass
class ScoredTarget:
    target: MatchTarget
    score: float


def _content(text: str) -> set[str]:
    return _tokens(text) - _RETRIEVAL_JUNK - _ARTICLES


def _coverage(needles: set[str], haystack: set[str]) -> float:
    return len(needles & haystack) / len(needles) if needles else 0.0


def retrieval_score(name: str, target: MatchTarget) -> float:
    """How plausible is it that this download is this album?

    Artist and title score separately so a compilation (whose artist is a useless
    "Various Artists") is still retrievable on its title alone, and a download naming
    only the artist is still retrievable. A self-titled album has no distinctive title
    tokens, so its artist carries both halves.
    """
    name_tokens = _content(name)
    artist_tokens = _content(target.artist)
    title_tokens = _content(target.title) - artist_tokens

    artist_hit = _coverage(artist_tokens, name_tokens)
    title_hit = _coverage(title_tokens, name_tokens) if title_tokens else artist_hit

    ratio = SequenceMatcher(
        None,
        " ".join(sorted(name_tokens)),
        " ".join(sorted(artist_tokens | title_tokens)),
    ).ratio()
    return 0.45 * max(artist_hit, title_hit) + 0.35 * min(artist_hit, title_hit) + 0.20 * ratio


def retrieve(
    name: str, targets: list[MatchTarget], *, limit: int, floor: float = 0.12
) -> list[MatchTarget]:
    """The `limit` most plausible albums for a download, best first.

    Deliberately loose: its job is recall — get the right album *somewhere* into the
    list — not precision. `floor` only drops the plainly unrelated, so a download that
    is nothing MCM knows about comes back with a short list or an empty one. Measured
    at 98% recall in 12 against MCM's existing matches.
    """
    scored = [ScoredTarget(t, s) for t in targets if (s := retrieval_score(name, t)) >= floor]
    scored.sort(key=lambda c: -c.score)
    return [c.target for c in scored[:limit]]

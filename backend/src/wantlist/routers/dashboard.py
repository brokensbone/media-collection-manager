from fastapi import APIRouter, Request

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(request: Request) -> dict[str, int]:
    """At-a-glance counts, one per worklist section (SPEC §8d). Keys match the UI headings:
    releases/decide/acquire/import are live queue sizes; owned/dismissed are state totals."""
    state = request.app.state
    counts = state.album_repo.count_by_state()
    resolved, unresolved = state.album_repo.resolution_counts()
    try:
        # Owned is the beets library itself (§5), not just the Spotify∩beets `owned` state.
        owned = state.library_assist_service.owned_count()
    except Exception:
        owned = counts.get("owned", 0)  # beets hiccup: fall back to the tracked overlap
    return {
        "releases": counts.get("suggested", 0),
        "decide": len(state.decide_service.queue()),
        "acquire": len(state.acquire_service.queue()),
        "import": state.album_repo.count_active_imports(),
        "owned": owned,
        "dismissed": counts.get("dismissed", 0),
        # cold-start resolution progress (§5): how many albums have a MusicBrainz release-group
        "resolved": resolved,
        "unresolved": unresolved,
    }

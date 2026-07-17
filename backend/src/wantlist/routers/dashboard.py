from fastapi import APIRouter, Request

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(request: Request) -> dict[str, int]:
    """At-a-glance counts, one per worklist section (SPEC §8d). Keys match the UI headings:
    releases/decide/acquire/import are live queue sizes; owned/dismissed are state totals."""
    state = request.app.state
    counts = state.album_repo.count_by_state()
    return {
        "releases": counts.get("suggested", 0),
        "decide": len(state.decide_service.queue()),
        "acquire": len(state.acquire_service.queue()),
        "import": state.album_repo.count_active_imports(),
        "owned": counts.get("owned", 0),
        "dismissed": counts.get("dismissed", 0),
    }

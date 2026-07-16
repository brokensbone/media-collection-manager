from fastapi import APIRouter, Request

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(request: Request) -> dict[str, int]:
    """At-a-glance worklist counts (SPEC §8d). decide/acquire are the live queue sizes."""
    state = request.app.state
    counts = state.album_repo.count_by_state()
    return {
        "decide": len(state.decide_service.queue()),
        "acquire": len(state.acquire_service.queue()),
        "owned": counts.get("owned", 0),
        "dismissed": counts.get("dismissed", 0),
        "saved": counts.get("saved", 0),
    }

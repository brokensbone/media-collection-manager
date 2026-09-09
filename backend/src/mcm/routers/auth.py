import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth_service import AuthService

router = APIRouter(prefix="/auth/spotify", tags=["auth"])
_STATE_COOKIE = "wl_oauth_state"


def _service(request: Request) -> AuthService:
    return request.app.state.auth_service  # type: ignore[no-any-return]


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    state = secrets.token_urlsafe(24)
    resp = RedirectResponse(_service(request).authorize_url(state))
    resp.set_cookie(_STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600)
    return resp


@router.get("/callback")
def callback(request: Request, code: str, state: str) -> RedirectResponse:
    expected = request.cookies.get(_STATE_COOKIE)
    if not expected or not secrets.compare_digest(expected, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    _service(request).complete_login(code)
    frontend_url: str = request.app.state.settings.frontend_url
    resp = RedirectResponse(frontend_url)
    resp.delete_cookie(_STATE_COOKIE)
    return resp


@router.get("/status")
def status(request: Request) -> JSONResponse:
    s = _service(request).status()
    return JSONResponse(
        {
            "connected": s.connected,
            "authorized_at": s.authorized_at.isoformat() if s.authorized_at else None,
            "reauth_in_days": s.reauth_in_days,
            "reauth_due": s.reauth_due,
        }
    )

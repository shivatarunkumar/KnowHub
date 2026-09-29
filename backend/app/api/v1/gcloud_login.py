"""Reconnect Google Cloud from the web app (services/gcloud_login.py).

Shared by both APIs: signing in is about this machine, not the database. No KnowHub
account is needed, because signing in to KnowHub itself reads BigQuery and fails for the
same reason; being on this machine is what counts.
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.services import gcloud_login

router = APIRouter(prefix="/gcloud-login", tags=["gcloud-login"])


class LoginStep(BaseModel):
    name: str
    label: str
    state: str
    url: str | None = None
    error: str | None = None


class GcloudLoginStatus(BaseModel):
    """available=false: no button (someone else's browser, a service account, no gcloud)."""

    available: bool
    ok: bool | None = None
    account: str | None = None
    cli_error: str | None = None
    adc_error: str | None = None
    running: bool = False
    steps: list[LoginStep] = []


def _available(request: Request, forwarded_for: str | None, settings: Settings) -> bool:
    return gcloud_login.enabled(settings) and gcloud_login.from_this_machine(
        request.client.host if request.client else None, forwarded_for
    )


async def _status() -> GcloudLoginStatus:
    # cached; a finished sign-in clears the cache so the next poll asks Google again
    checked = await gcloud_login.check()
    return GcloudLoginStatus(
        available=True,
        ok=checked["ok"],
        account=checked["cli"].get("account"),
        cli_error=checked["cli"].get("error"),
        adc_error=checked["adc"].get("error"),
        running=gcloud_login.running(),
        steps=[LoginStep(**step) for step in gcloud_login.steps()],
    )


@router.get("", response_model=GcloudLoginStatus)
async def get_status(
    request: Request,
    x_forwarded_for: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> GcloudLoginStatus:
    """Is this machine signed in to Google Cloud, and is a sign-in under way?"""
    if not _available(request, x_forwarded_for, settings):
        return GcloudLoginStatus(available=False)
    return await _status()


@router.post("", response_model=GcloudLoginStatus)
async def start_login(
    request: Request,
    x_forwarded_for: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> GcloudLoginStatus:
    """Start `gcloud auth login` and `gcloud auth application-default login`; the
    response carries the two sign-in URLs for the browser to open (poll GET for them)."""
    if not _available(request, x_forwarded_for, settings):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Sign in to Google Cloud from a browser on the machine running KnowHub",
        )
    gcloud_login.start(settings)
    return await _status()

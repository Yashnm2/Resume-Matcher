"""Explicit, one-way daily completion notifications."""

import httpx

from app.config import settings


async def send_daily_ready_email(prepared: int, failed: int) -> bool:
    """Send one daily inbox link when configured; never sends referral drafts."""
    if not settings.resend_api_key or not settings.notification_email or prepared < 1:
        return False
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.notification_from_email,
                "to": [settings.notification_email],
                "subject": f"Your {prepared} application pack{'s are' if prepared != 1 else ' is'} ready",
                "html": (
                    f"<p>Resume Matcher prepared <strong>{prepared}</strong> review-only application pack(s). "
                    f"{failed} failed and can be retried.</p><p><a href=\"{settings.public_app_url.rstrip('/')}/scout\">"
                    "Open Today’s 20</a></p>"
                ),
            },
        )
    response.raise_for_status()
    return True

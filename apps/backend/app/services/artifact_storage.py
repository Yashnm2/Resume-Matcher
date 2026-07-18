"""Private Supabase Storage adapter for immutable application-pack artifacts."""

import json
from typing import Any
from urllib.parse import quote

import httpx

from app.config import settings


async def store_application_pack(
    *,
    user_id: str,
    pack_id: str,
    resume_data: dict[str, Any],
    cover_letter: str,
    referral_email: str,
    outreach_message: str,
    interview_prep: dict[str, Any],
) -> dict[str, str]:
    """Upload editable artifacts when Supabase Storage is configured.

    The bucket must be private. The service-role key remains backend-only; the
    browser never receives it. Local development intentionally falls back to
    database-backed artifacts when these deployment settings are absent.
    """
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {}
    base_path = f"{user_id}/{pack_id}"
    artifacts: dict[str, tuple[bytes, str]] = {
        "resume_json": (
            json.dumps(resume_data, ensure_ascii=False, indent=2).encode(),
            "application/json",
        ),
        "cover_letter_txt": (cover_letter.encode(), "text/plain; charset=utf-8"),
        "referral_email_txt": (referral_email.encode(), "text/plain; charset=utf-8"),
        "outreach_txt": (outreach_message.encode(), "text/plain; charset=utf-8"),
        "interview_prep_json": (
            json.dumps(interview_prep, ensure_ascii=False, indent=2).encode(),
            "application/json",
        ),
    }
    names = {
        "resume_json": "resume.json",
        "cover_letter_txt": "cover-letter.txt",
        "referral_email_txt": "referral-email.txt",
        "outreach_txt": "outreach.txt",
        "interview_prep_json": "interview-prep.json",
    }
    return await store_binary_artifacts(
        base_path=base_path, artifacts=artifacts, names=names
    )


async def store_binary_artifacts(
    *,
    base_path: str,
    artifacts: dict[str, tuple[bytes, str]],
    names: dict[str, str],
) -> dict[str, str]:
    """Store named binary artifacts under an immutable user-owned path."""
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {}
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key,
        "x-upsert": "false",
    }
    manifest: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        for key, (content, content_type) in artifacts.items():
            path = f"{base_path}/{names[key]}"
            url = (
                f"{settings.supabase_url.rstrip('/')}/storage/v1/object/"
                f"{quote(settings.supabase_storage_bucket, safe='')}/{quote(path, safe='/')}"
            )
            response = await client.post(
                url, content=content, headers={**headers, "Content-Type": content_type}
            )
            if response.status_code == 409:
                # A retry with the same pack id is already durably stored.
                manifest[key] = path
                continue
            response.raise_for_status()
            manifest[key] = path
    return manifest

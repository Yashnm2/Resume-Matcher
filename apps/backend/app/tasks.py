"""Idempotent scheduled tasks for discovery and daily application packs."""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from celery import chord

from app.celery_app import celery_app
from app.config import settings
from app.scout_repository import scout_repository
from app.services.scout import prepare_pack, scan_source
from app.services.notifications import send_daily_ready_email
from app.pdf import render_resume_pdf
from app.services.artifact_storage import store_binary_artifacts


async def _scan_all_sources(user_id: str | None) -> dict[str, int]:
    """Scan every enabled source while isolating per-source failures."""
    scanned = failed = 0
    user_ids = [user_id] if user_id else await scout_repository.list_scout_users()
    for owner_id in user_ids:
        for source in await scout_repository.list_sources(owner_id):
            if not source["enabled"]:
                continue
            try:
                await scan_source(owner_id, source["source_id"])
                scanned += 1
            except Exception:
                failed += 1
    return {"scanned": scanned, "failed": failed}


@celery_app.task(
    name="app.tasks.scan_all_sources",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    max_retries=3,
)
def scan_all_sources(user_id: str | None = None) -> dict[str, int]:
    """Celery entrypoint for the four-hour source schedule."""
    return asyncio.run(_scan_all_sources(user_id))


async def _select_daily_queue(user_id: str) -> list[str]:
    """Select today's best opportunities and return idempotent pack jobs."""
    selected_ids: list[str] = []
    for profile in await scout_repository.list_profiles(user_id):
        if not profile["is_active"]:
            continue
        timezone_name = profile["config_json"].get("timezone", settings.scout_timezone)
        local_now = datetime.now(ZoneInfo(timezone_name))
        if local_now.hour != 6 or local_now.minute >= 15:
            continue
        local_date = local_now.date().isoformat()
        rows = await scout_repository.select_daily(
            user_id, profile["profile_id"], local_date
        )
        selected_ids.extend(
            row["match_id"] for row in rows if row["state"] in {"selected", "ready"}
        )
    return list(dict.fromkeys(selected_ids))


@celery_app.task(
    name="app.tasks.build_daily_queue",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    max_retries=2,
)
def build_daily_queue(user_id: str | None = None) -> dict[str, int]:
    """Celery entrypoint for the 06:00 daily selection schedule."""
    user_ids = (
        [user_id] if user_id else asyncio.run(scout_repository.list_scout_users())
    )
    queued = 0
    for owner_id in user_ids:
        match_ids = asyncio.run(_select_daily_queue(owner_id))
        queued += len(match_ids)
        if match_ids:
            chord(
                prepare_selected_pack.s(match_id, owner_id) for match_id in match_ids
            )(finalize_daily_run.s(owner_id))
    return {"selected": queued, "queued": queued}


@celery_app.task(
    name="app.tasks.prepare_selected_pack",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    max_retries=2,
)
def prepare_selected_pack(match_id: str, user_id: str = "local-user") -> dict:
    """Prepare one pack on the LLM queue."""
    try:
        pack = asyncio.run(prepare_pack(user_id, match_id))
        render_pack_pdfs.delay(match_id, user_id)
        return {"match_id": match_id, "status": "ready", "pack_id": pack["pack_id"]}
    except Exception as exc:
        return {"match_id": match_id, "status": "failed", "error": str(exc)[:500]}


@celery_app.task(name="app.tasks.finalize_daily_run")
def finalize_daily_run(
    results: list[dict], user_id: str = "local-user"
) -> dict[str, int]:
    """Send one summary only after every independent pack task has settled."""
    prepared = sum(result.get("status") == "ready" for result in results)
    failed = sum(result.get("status") == "failed" for result in results)
    notified = asyncio.run(send_daily_ready_email(prepared, failed))
    return {"prepared": prepared, "failed": failed, "notified": int(notified)}


async def _render_pack_pdfs(match_id: str, user_id: str) -> dict[str, str]:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return {}
    pack = await scout_repository.get_pack(user_id, match_id)
    if not pack or pack.get("status") != "ready" or not pack.get("resume_id"):
        return {}
    resume_id = pack["resume_id"]
    base_url = settings.public_app_url.rstrip("/")
    resume_pdf = await render_resume_pdf(
        f"{base_url}/print/resumes/{resume_id}?template=swiss-single&pageSize=A4",
        "A4",
        margins={"top": 10, "right": 10, "bottom": 10, "left": 10},
    )
    cover_pdf = await render_resume_pdf(
        f"{base_url}/print/cover-letter/{resume_id}?pageSize=A4",
        "A4",
        selector=".cover-letter-print",
    )
    manifest = dict(pack.get("storage_manifest") or {})
    existing_path = next(iter(manifest.values()), None)
    base_path = (
        existing_path.rsplit("/", 1)[0]
        if existing_path
        else f"{user_id}/{pack['pack_id']}"
    )
    pdf_manifest = await store_binary_artifacts(
        base_path=base_path,
        artifacts={
            "resume_pdf": (resume_pdf, "application/pdf"),
            "cover_letter_pdf": (cover_pdf, "application/pdf"),
        },
        names={"resume_pdf": "resume.pdf", "cover_letter_pdf": "cover-letter.pdf"},
    )
    manifest.update(pdf_manifest)
    await scout_repository.upsert_pack(
        user_id, match_id, {"storage_manifest": manifest}
    )
    return pdf_manifest


@celery_app.task(
    name="app.tasks.render_pack_pdfs",
    autoretry_for=(RuntimeError,),
    retry_backoff=True,
    max_retries=2,
)
def render_pack_pdfs(match_id: str, user_id: str = "local-user") -> dict[str, str]:
    """Render and privately store PDFs on the isolated Chromium queue."""
    try:
        return asyncio.run(_render_pack_pdfs(match_id, user_id))
    except Exception as exc:
        asyncio.run(
            scout_repository.audit(
                user_id,
                "pack.pdf.failed",
                "job_match",
                match_id,
                {"error": str(exc)[:500]},
            )
        )
        raise

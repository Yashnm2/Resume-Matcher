"""HTTP API for job scouting, daily selection, contacts, and application packs."""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.auth import CurrentUser, get_current_user
from app.config import settings
from app.database import db
from app.scout_repository import scout_repository
from app.schemas.scout import (
    ArtifactPackResponse,
    ArtifactPackUpdate,
    CandidateFactCreate,
    CandidateFactResponse,
    ContactImportResponse,
    ContactResponse,
    EmailAlertIngest,
    JobMatchResponse,
    JobSourceCreate,
    JobSourceResponse,
    ManualJobCreate,
    OpportunityStateUpdate,
    PreparePackRequest,
    ReferralMatchResponse,
    ReferralHistoryUpdate,
    ScoutRunResponse,
    SearchProfileCreate,
    SearchProfileUpdate,
    SearchProfileResponse,
)
from app.services.scout import (
    _fact_is_safe,
    ingest_and_score,
    import_linkedin_contacts,
    manual_posting,
    prepare_pack,
    rank_referrals,
    resolve_email_alert,
    scan_source,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["scout"])


def _profile_response(row: dict[str, Any]) -> SearchProfileResponse:
    """Translate persistence naming into the public profile contract."""
    return SearchProfileResponse(
        profile_id=row["profile_id"],
        user_id=row["user_id"],
        name=row["name"],
        config=row["config_json"],
        is_active=row["is_active"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_response(row: dict[str, Any]) -> JobSourceResponse:
    """Translate persistence naming into the public source contract."""
    return JobSourceResponse(
        source_id=row["source_id"],
        user_id=row["user_id"],
        name=row["name"],
        source_type=row["source_type"],
        config=row["config_json"],
        enabled=row["enabled"],
        status=row["status"],
        last_scan_at=row["last_scan_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _match_response(row: dict[str, Any]) -> JobMatchResponse:
    """Translate a joined match row into the public opportunity contract."""
    return JobMatchResponse(
        match_id=row["match_id"],
        profile_id=row["profile_id"],
        posting=row["posting"],
        eligible=row["eligible"],
        score=row["score"],
        score_components=row["score_components"],
        gaps=row["gaps_json"],
        explanation=row["explanation"],
        state=row["state"],
        selected_date=row["selected_date"],
        daily_rank=row["daily_rank"],
        pack_status=row.get("pack_status"),
        referral_count=row.get("referral_count", 0),
    )


def _pack_response(row: dict[str, Any]) -> ArtifactPackResponse:
    """Translate persistence naming into the public pack contract."""
    return ArtifactPackResponse(
        pack_id=row["pack_id"],
        match_id=row["match_id"],
        resume_id=row["resume_id"],
        cover_letter=row["cover_letter"],
        outreach_message=row["outreach_message"],
        referral_subject=row["referral_subject"],
        referral_email=row["referral_email"],
        linkedin_message=row["linkedin_message"],
        interview_prep=row["interview_prep"],
        application_answers=row["application_answers"],
        provenance=row["provenance_json"],
        llm_usage=row.get("llm_usage_json") or {},
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/search-profiles", response_model=SearchProfileResponse)
async def create_search_profile(
    request: SearchProfileCreate, user: CurrentUser = Depends(get_current_user)
) -> SearchProfileResponse:
    """Create a reusable search and daily-quota profile."""
    row = await scout_repository.create_profile(
        user.user_id, request.name, request.config.model_dump(), request.is_active
    )
    return _profile_response(row)


@router.get("/search-profiles", response_model=list[SearchProfileResponse])
async def list_search_profiles(
    user: CurrentUser = Depends(get_current_user),
) -> list[SearchProfileResponse]:
    """List the current user's search profiles."""
    return [
        _profile_response(row)
        for row in await scout_repository.list_profiles(user.user_id)
    ]


@router.patch("/search-profiles/{profile_id}", response_model=SearchProfileResponse)
async def update_search_profile(
    profile_id: str,
    request: SearchProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> SearchProfileResponse:
    """Update a user-owned search profile without recreating its match history."""
    changes = request.model_dump(exclude_unset=True)
    if "config" in changes and request.config is not None:
        changes["config"] = request.config.model_dump()
    row = await scout_repository.update_profile(user.user_id, profile_id, changes)
    if row is None:
        raise HTTPException(status_code=404, detail="Search profile not found")
    return _profile_response(row)


@router.post("/sources", response_model=JobSourceResponse)
async def create_job_source(
    request: JobSourceCreate, user: CurrentUser = Depends(get_current_user)
) -> JobSourceResponse:
    """Configure a public source adapter."""
    row = await scout_repository.create_source(
        user.user_id, request.name, request.source_type, request.config, request.enabled
    )
    return _source_response(row)


@router.get("/sources", response_model=list[JobSourceResponse])
async def list_job_sources(
    user: CurrentUser = Depends(get_current_user),
) -> list[JobSourceResponse]:
    """List source health and schedules."""
    return [
        _source_response(row)
        for row in await scout_repository.list_sources(user.user_id)
    ]


@router.post("/sources/{source_id}/scan", response_model=ScoutRunResponse)
async def run_source_scan(
    source_id: str, user: CurrentUser = Depends(get_current_user)
) -> ScoutRunResponse:
    """Run one source now; scheduled workers call the same service."""
    try:
        return ScoutRunResponse.model_validate(
            await scan_source(user.user_id, source_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Source scan failed for %s", source_id)
        raise HTTPException(
            status_code=502,
            detail="The source scan failed. Check its configuration and try again.",
        ) from exc


@router.post("/sources/email-ingest", status_code=202)
async def ingest_email_alert(
    request: EmailAlertIngest,
    x_resume_matcher_secret: str | None = Header(default=None),
) -> dict[str, str]:
    """Receive a provider-forwarded alert without logging into a job board."""
    if (
        not settings.inbound_email_secret
        or x_resume_matcher_secret != settings.inbound_email_secret
    ):
        raise HTTPException(status_code=401, detail="Invalid inbound email secret.")
    try:
        posting, _ = await ingest_and_score(
            settings.scout_user_id, await resolve_email_alert(request.model_dump())
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"posting_id": posting["posting_id"], "status": posting["status"]}


@router.get("/scout-runs", response_model=list[ScoutRunResponse])
async def list_scout_runs(
    limit: int = Query(default=50, ge=1, le=200),
    user: CurrentUser = Depends(get_current_user),
) -> list[ScoutRunResponse]:
    """List recent source executions."""
    return [
        ScoutRunResponse.model_validate(row)
        for row in await scout_repository.list_runs(user.user_id, limit)
    ]


@router.post("/opportunities/manual", status_code=201)
async def create_manual_opportunity(
    request: ManualJobCreate, user: CurrentUser = Depends(get_current_user)
) -> dict[str, str]:
    """Add and immediately score a manually supplied job description."""
    posting, created = await ingest_and_score(
        user.user_id,
        manual_posting(request.model_dump(mode="json")),
        request.profile_id,
    )
    return {
        "posting_id": posting["posting_id"],
        "result": "created" if created else "updated",
    }


@router.get("/opportunities", response_model=list[JobMatchResponse])
async def list_opportunities(
    state: list[str] | None = Query(default=None),
    user: CurrentUser = Depends(get_current_user),
) -> list[JobMatchResponse]:
    """List scored opportunities with optional workflow-state filtering."""
    return [
        _match_response(row)
        for row in await scout_repository.list_matches(user.user_id, states=state)
    ]


@router.post("/opportunities/today/select", response_model=list[JobMatchResponse])
async def select_todays_opportunities(
    profile_id: str, user: CurrentUser = Depends(get_current_user)
) -> list[JobMatchResponse]:
    """Select up to the configured daily limit plus reserve jobs."""
    local_date = datetime.now(ZoneInfo(settings.scout_timezone)).date().isoformat()
    rows = await scout_repository.select_daily(user.user_id, profile_id, local_date)
    return [_match_response(row) for row in rows]


@router.get("/opportunities/today", response_model=list[JobMatchResponse])
async def list_todays_opportunities(
    user: CurrentUser = Depends(get_current_user),
) -> list[JobMatchResponse]:
    """Return today's selected and reserve queue."""
    local_date = datetime.now(ZoneInfo(settings.scout_timezone)).date().isoformat()
    return [
        _match_response(row)
        for row in await scout_repository.list_matches(
            user.user_id, selected_date=local_date
        )
    ]


@router.patch("/opportunities/{match_id}", response_model=dict)
async def update_opportunity_state(
    match_id: str,
    request: OpportunityStateUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """Apply an explicit workflow decision."""
    row = await scout_repository.set_match_state(user.user_id, match_id, request.state)
    if row is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    await scout_repository.audit(
        user.user_id,
        "opportunity.state.changed",
        "job_match",
        match_id,
        {"state": request.state},
    )
    return row


@router.post("/opportunities/{match_id}/replace", response_model=dict)
async def replace_opportunity(
    match_id: str, user: CurrentUser = Depends(get_current_user)
) -> dict[str, Any]:
    """Ignore a selected job and promote the highest-scoring reserve."""
    replacement = await scout_repository.replace_selected(user.user_id, match_id)
    if replacement is None:
        raise HTTPException(
            status_code=400, detail="Only a selected daily opportunity can be replaced."
        )
    await scout_repository.audit(
        user.user_id,
        "opportunity.replaced",
        "job_match",
        match_id,
        {"replacement_match_id": replacement.get("match_id")},
    )
    return replacement


@router.post("/opportunities/{match_id}/prepare", response_model=ArtifactPackResponse)
async def prepare_opportunity_pack(
    match_id: str,
    request: PreparePackRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ArtifactPackResponse:
    """Prepare an idempotent, review-only application pack."""
    try:
        return _pack_response(
            await prepare_pack(
                user.user_id,
                match_id,
                regeneration_key=request.regeneration_key if request.force else None,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Pack preparation failed for %s", match_id)
        raise HTTPException(
            status_code=502,
            detail="Application-pack generation failed. Review the run and retry.",
        ) from exc


@router.get("/opportunities/{match_id}/pack", response_model=ArtifactPackResponse)
async def get_opportunity_pack(
    match_id: str, user: CurrentUser = Depends(get_current_user)
) -> ArtifactPackResponse:
    """Fetch all generated artifacts for an opportunity."""
    row = await scout_repository.get_pack(user.user_id, match_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Application pack not found.")
    return _pack_response(row)


@router.patch("/opportunities/{match_id}/pack", response_model=ArtifactPackResponse)
async def update_opportunity_pack(
    match_id: str,
    request: ArtifactPackUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> ArtifactPackResponse:
    """Save user edits to generated copy; this never mutates the master résumé."""
    current = await scout_repository.get_pack(user.user_id, match_id)
    if current is None:
        raise HTTPException(status_code=404, detail="Application pack not found.")
    updates = request.model_dump(exclude_none=True)
    if not updates:
        return _pack_response(current)
    row = await scout_repository.upsert_pack(user.user_id, match_id, updates)
    if current.get("resume_id"):
        resume_updates = {
            key: value
            for key, value in updates.items()
            if key in {"cover_letter", "outreach_message"}
        }
        if resume_updates:
            await db.update_resume(current["resume_id"], resume_updates)
    await scout_repository.audit(
        user.user_id,
        "pack.edited",
        "job_match",
        match_id,
        {"fields": sorted(updates)},
    )
    return _pack_response(row)


@router.get(
    "/opportunities/{match_id}/referrals", response_model=list[ReferralMatchResponse]
)
async def get_opportunity_referrals(
    match_id: str, refresh: bool = False, user: CurrentUser = Depends(get_current_user)
) -> list[ReferralMatchResponse]:
    """List or recompute the top three explainable referral candidates."""
    match = await scout_repository.get_match(user.user_id, match_id)
    if match is None:
        raise HTTPException(status_code=404, detail="Opportunity not found.")
    rows = (
        await rank_referrals(user.user_id, match)
        if refresh
        else await scout_repository.list_referrals(user.user_id, match_id)
    )
    return [ReferralMatchResponse.model_validate(row) for row in rows]


@router.patch(
    "/opportunities/{match_id}/referrals/{referral_match_id}",
    response_model=ReferralMatchResponse,
)
async def update_referral_history(
    match_id: str,
    referral_match_id: str,
    request: ReferralHistoryUpdate,
    user: CurrentUser = Depends(get_current_user),
) -> ReferralMatchResponse:
    """Record manual outreach and response notes without sending a message."""
    row = await scout_repository.update_referral_history(
        user.user_id,
        match_id,
        referral_match_id,
        contacted=request.contacted,
        response_notes=request.response_notes,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Referral candidate not found.")
    await scout_repository.audit(
        user.user_id,
        "referral.history.updated",
        "referral_match",
        referral_match_id,
        {
            "contacted": request.contacted,
            "has_response_notes": bool(request.response_notes),
        },
    )
    return ReferralMatchResponse.model_validate(row)


@router.post("/contacts/import/linkedin", response_model=ContactImportResponse)
async def import_linkedin_connections(
    file: UploadFile = File(...), user: CurrentUser = Depends(get_current_user)
) -> ContactImportResponse:
    """Import the user's official LinkedIn Connections.csv export."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(
            status_code=400, detail="Upload the LinkedIn Connections.csv file."
        )
    content = await file.read()
    if len(content) > 10_000_000:
        raise HTTPException(status_code=413, detail="Connections file is too large.")
    return ContactImportResponse.model_validate(
        await import_linkedin_contacts(user.user_id, content)
    )


@router.get("/contacts", response_model=list[ContactResponse])
async def list_contacts(
    user: CurrentUser = Depends(get_current_user),
) -> list[ContactResponse]:
    """List imported contacts without enriching or scraping profiles."""
    return [
        ContactResponse.model_validate(row)
        for row in await scout_repository.list_contacts(user.user_id)
    ]


@router.post("/candidate-facts", response_model=CandidateFactResponse)
async def save_candidate_fact(
    request: CandidateFactCreate, user: CurrentUser = Depends(get_current_user)
) -> CandidateFactResponse:
    """Save an explicit answer that generation may reuse."""
    payload = request.model_dump()
    if not _fact_is_safe(payload):
        payload["sensitive"] = True
    return CandidateFactResponse.model_validate(
        await scout_repository.upsert_fact(user.user_id, payload)
    )


@router.get("/candidate-facts", response_model=list[CandidateFactResponse])
async def list_candidate_facts(
    user: CurrentUser = Depends(get_current_user),
) -> list[CandidateFactResponse]:
    """List the user's reusable application facts."""
    return [
        CandidateFactResponse.model_validate(row)
        for row in await scout_repository.list_facts(user.user_id)
    ]


@router.get("/events")
async def scout_events(
    user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Stream lightweight authenticated workflow snapshots for the review UI."""

    async def stream() -> AsyncIterator[str]:
        while True:
            rows = await scout_repository.list_matches(
                user.user_id, states=["selected", "reserve", "preparing", "ready"]
            )
            payload = {
                "opportunities": len(rows),
                "preparing": sum(row["state"] == "preparing" for row in rows),
            }
            yield f"event: scout\ndata: {json.dumps(payload)}\n\n"
            await asyncio.sleep(15)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )

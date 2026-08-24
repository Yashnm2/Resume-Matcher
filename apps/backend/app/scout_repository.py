"""Persistence boundary for the job-scout domain."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select, union, update
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.models import (
    Application,
    ArtifactPack,
    AuditEvent,
    CandidateFact,
    Contact,
    JobMatch,
    JobPosting,
    JobSource,
    ReferralMatch,
    ScoutRun,
    SearchProfile,
)


def utcnow() -> str:
    """Return a stable UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


def row_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy model to a JSON-ready dictionary."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}


class ScoutRepository:
    """Async repository with user-scoped operations and idempotent upserts."""

    async def create_profile(
        self, user_id: str, name: str, config: dict[str, Any], is_active: bool
    ) -> dict[str, Any]:
        async with db.session_factory() as session:
            now = utcnow()
            row = SearchProfile(
                profile_id=str(uuid4()),
                user_id=user_id,
                name=name,
                config_json=config,
                is_active=is_active,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return row_dict(row)

    async def list_profiles(self, user_id: str) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(SearchProfile)
                .where(SearchProfile.user_id == user_id)
                .order_by(SearchProfile.created_at)
            )
            return [row_dict(row) for row in result.scalars().all()]

    async def update_profile(
        self, user_id: str, profile_id: str, changes: dict[str, Any]
    ) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(SearchProfile).where(
                    SearchProfile.user_id == user_id,
                    SearchProfile.profile_id == profile_id,
                )
            )
            row = result.scalars().first()
            if row is None:
                return None
            for key, value in changes.items():
                setattr(row, "config_json" if key == "config" else key, value)
            row.updated_at = utcnow()
            await session.commit()
            return row_dict(row)

    async def list_scout_users(self) -> list[str]:
        """List owners with configured profiles or sources for scheduled work."""
        async with db.session_factory() as session:
            result = await session.execute(
                union(select(SearchProfile.user_id), select(JobSource.user_id))
            )
            return [str(row[0]) for row in result.all() if row[0]]

    async def get_profile(self, user_id: str, profile_id: str) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(SearchProfile).where(
                    SearchProfile.user_id == user_id,
                    SearchProfile.profile_id == profile_id,
                )
            )
            row = result.scalars().first()
            return row_dict(row) if row else None

    async def create_source(
        self,
        user_id: str,
        name: str,
        source_type: str,
        config: dict[str, Any],
        enabled: bool,
    ) -> dict[str, Any]:
        async with db.session_factory() as session:
            now = utcnow()
            row = JobSource(
                source_id=str(uuid4()),
                user_id=user_id,
                name=name,
                source_type=source_type,
                config_json=config,
                cursor_json={},
                enabled=enabled,
                status="idle",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            await session.commit()
            return row_dict(row)

    async def list_sources(self, user_id: str) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobSource)
                .where(JobSource.user_id == user_id)
                .order_by(JobSource.created_at)
            )
            return [row_dict(row) for row in result.scalars().all()]

    async def get_source(self, user_id: str, source_id: str) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobSource).where(
                    JobSource.user_id == user_id, JobSource.source_id == source_id
                )
            )
            row = result.scalars().first()
            return row_dict(row) if row else None

    async def update_source_health(
        self,
        user_id: str,
        source_id: str,
        *,
        status: str,
        error: str | None,
        cursor: dict[str, Any] | None = None,
    ) -> None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobSource).where(
                    JobSource.user_id == user_id, JobSource.source_id == source_id
                )
            )
            row = result.scalars().first()
            if row is None:
                return
            row.status = status
            row.last_error = error
            row.last_scan_at = utcnow()
            row.updated_at = utcnow()
            if cursor is not None:
                row.cursor_json = cursor
            await session.commit()

    async def start_run(self, user_id: str, source_id: str) -> dict[str, Any]:
        async with db.session_factory() as session:
            row = ScoutRun(
                run_id=str(uuid4()),
                user_id=user_id,
                source_id=source_id,
                status="running",
            )
            session.add(row)
            await session.commit()
            return row_dict(row)

    async def finish_run(
        self,
        run_id: str,
        *,
        status: str,
        discovered_count: int,
        created_count: int,
        error: str | None = None,
    ) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            row = await session.get(ScoutRun, run_id)
            if row is None:
                return None
            row.status = status
            row.discovered_count = discovered_count
            row.created_count = created_count
            row.error = error
            row.finished_at = utcnow()
            await session.commit()
            return row_dict(row)

    async def list_runs(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(ScoutRun)
                .where(ScoutRun.user_id == user_id)
                .order_by(ScoutRun.started_at.desc())
                .limit(limit)
            )
            return [row_dict(row) for row in result.scalars().all()]

    async def upsert_posting(
        self, user_id: str, data: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobPosting).where(
                    JobPosting.user_id == user_id,
                    JobPosting.canonical_key == data["canonical_key"],
                )
            )
            row = result.scalars().first()
            created = row is None
            now = utcnow()
            if row is None:
                row = JobPosting(
                    posting_id=str(uuid4()), user_id=user_id, discovered_at=now, **data
                )
                session.add(row)
            else:
                for key, value in data.items():
                    setattr(row, key, value)
                row.updated_at = now
            await session.commit()
            return row_dict(row), created

    async def upsert_match(
        self, user_id: str, profile_id: str, posting_id: str, assessment: dict[str, Any]
    ) -> dict[str, Any]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobMatch).where(
                    JobMatch.profile_id == profile_id, JobMatch.posting_id == posting_id
                )
            )
            row = result.scalars().first()
            now = utcnow()
            values = {
                "eligible": assessment["eligible"],
                "score": assessment["score"],
                "score_components": assessment["components"],
                "gaps_json": assessment["gaps"],
                "explanation": assessment["explanation"],
                "updated_at": now,
            }
            if row is None:
                row = JobMatch(
                    match_id=str(uuid4()),
                    user_id=user_id,
                    profile_id=profile_id,
                    posting_id=posting_id,
                    state="discovered",
                    created_at=now,
                    **values,
                )
                session.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            await session.commit()
            return row_dict(row)

    async def get_match(self, user_id: str, match_id: str) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobMatch, JobPosting)
                .join(JobPosting, JobPosting.posting_id == JobMatch.posting_id)
                .where(JobMatch.user_id == user_id, JobMatch.match_id == match_id)
            )
            pair = result.first()
            if pair is None:
                return None
            match, posting = pair
            data = row_dict(match)
            data["posting"] = row_dict(posting)
            return data

    async def list_matches(
        self,
        user_id: str,
        *,
        selected_date: str | None = None,
        states: list[str] | None = None,
        profile_id: str | None = None,
    ) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            stmt = (
                select(JobMatch, JobPosting, ArtifactPack.status)
                .join(JobPosting, JobPosting.posting_id == JobMatch.posting_id)
                .outerjoin(ArtifactPack, ArtifactPack.match_id == JobMatch.match_id)
                .where(JobMatch.user_id == user_id)
            )
            if selected_date is not None:
                stmt = stmt.where(JobMatch.selected_date == selected_date)
            if profile_id is not None:
                stmt = stmt.where(JobMatch.profile_id == profile_id)
            if states:
                stmt = stmt.where(JobMatch.state.in_(states))
            stmt = stmt.order_by(
                JobMatch.daily_rank.asc().nullslast(), JobMatch.score.desc()
            )
            result = await session.execute(stmt)
            rows: list[dict[str, Any]] = []
            for match, posting, pack_status in result.all():
                data = row_dict(match)
                data["posting"] = row_dict(posting)
                data["pack_status"] = pack_status
                referral_count = await session.scalar(
                    select(func.count())
                    .select_from(ReferralMatch)
                    .where(ReferralMatch.match_id == match.match_id)
                )
                data["referral_count"] = int(referral_count or 0)
                rows.append(data)
            return rows

    async def set_match_state(
        self, user_id: str, match_id: str, state: str
    ) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobMatch).where(
                    JobMatch.user_id == user_id, JobMatch.match_id == match_id
                )
            )
            row = result.scalars().first()
            if row is None:
                return None
            row.state = state
            row.updated_at = utcnow()
            await session.commit()
            return row_dict(row)

    async def replace_selected(
        self, user_id: str, match_id: str
    ) -> dict[str, Any] | None:
        """Ignore one selected job and promote the best reserve in the same daily queue."""
        async with db.session_factory() as session:
            result = await session.execute(
                select(JobMatch)
                .where(
                    JobMatch.user_id == user_id,
                    JobMatch.match_id == match_id,
                )
                .with_for_update()
            )
            current = result.scalars().first()
            if (
                current is None
                or current.state not in {"selected", "ready"}
                or not current.selected_date
            ):
                return None
            rank = current.daily_rank
            current.state = "ignored"
            current.daily_rank = None
            current.updated_at = utcnow()
            reserve_result = await session.execute(
                select(JobMatch)
                .where(
                    JobMatch.user_id == user_id,
                    JobMatch.profile_id == current.profile_id,
                    JobMatch.selected_date == current.selected_date,
                    JobMatch.state == "reserve",
                    JobMatch.eligible.is_(True),
                )
                .order_by(JobMatch.score.desc())
                .limit(1)
                .with_for_update()
            )
            replacement = reserve_result.scalars().first()
            if replacement is not None:
                replacement.state = "selected"
                replacement.daily_rank = rank
                replacement.updated_at = utcnow()
            await session.commit()
            return row_dict(replacement) if replacement else {}

    async def select_daily(
        self, user_id: str, profile_id: str, date_value: str
    ) -> list[dict[str, Any]]:
        profile = await self.get_profile(user_id, profile_id)
        if profile is None:
            return []
        config = profile["config_json"]
        limit = int(config.get("daily_pack_limit", 20))
        reserve_limit = int(config.get("reserve_limit", 10))
        threshold = float(config.get("minimum_match_score", 70))
        max_per_company = int(config.get("max_per_company", 2))
        candidates = await self.list_matches(
            user_id,
            states=["discovered", "selected", "reserve", "ready"],
            profile_id=profile_id,
        )
        company_counts: dict[str, int] = {}
        async with db.session_factory() as session:
            applied_result = await session.execute(
                select(Application.company, Application.role).where(
                    Application.user_id == user_id
                )
            )
            applied_roles = {
                ((company or "").casefold().strip(), (role or "").casefold().strip())
                for company, role in applied_result.all()
            }
        selected: list[dict[str, Any]] = []
        reserve: list[dict[str, Any]] = []
        for item in candidates:
            if not item["eligible"] or item["score"] < threshold:
                continue
            posting = item["posting"]
            if posting["status"] != "active":
                continue
            if posting.get("expires_at") and posting["expires_at"] < utcnow():
                continue
            if item.get("selected_date") and item["selected_date"] != date_value:
                continue
            applied_key = (
                posting["company"].casefold().strip(),
                posting["title"].casefold().strip(),
            )
            if applied_key in applied_roles:
                continue
            company = posting["company"].casefold().strip()
            if item["state"] == "ready" and item.get("selected_date") == date_value:
                selected.append(item)
                company_counts[company] = company_counts.get(company, 0) + 1
                continue
            if (
                len(selected) < limit
                and company_counts.get(company, 0) < max_per_company
            ):
                selected.append(item)
                company_counts[company] = company_counts.get(company, 0) + 1
            elif len(reserve) < reserve_limit:
                reserve.append(item)
        async with db.session_factory() as session:
            await session.execute(
                update(JobMatch)
                .where(
                    JobMatch.user_id == user_id,
                    JobMatch.profile_id == profile_id,
                    JobMatch.selected_date == date_value,
                    JobMatch.state.in_(["selected", "reserve"]),
                )
                .values(
                    state="discovered",
                    selected_date=None,
                    daily_rank=None,
                    updated_at=utcnow(),
                )
            )
            for rank, item in enumerate(selected, 1):
                row = await session.get(JobMatch, item["match_id"])
                if row:
                    if row.state != "ready":
                        row.state = "selected"
                    row.selected_date, row.daily_rank = date_value, rank
            for item in reserve:
                row = await session.get(JobMatch, item["match_id"])
                if row:
                    row.state, row.selected_date, row.daily_rank = (
                        "reserve",
                        date_value,
                        None,
                    )
            await session.commit()
        return await self.list_matches(
            user_id, selected_date=date_value, profile_id=profile_id
        )

    async def claim_pack(
        self, user_id: str, match_id: str, generation_key: str
    ) -> tuple[dict[str, Any], bool]:
        """Atomically claim pack generation.

        The unique match constraint plus a row lock ensures Celery retries and
        simultaneous UI clicks cannot incur duplicate LLM charges.
        """
        async with db.session_factory() as session:
            result = await session.execute(
                select(ArtifactPack)
                .where(
                    ArtifactPack.user_id == user_id, ArtifactPack.match_id == match_id
                )
                .with_for_update()
            )
            row = result.scalars().first()
            now = utcnow()
            if row is not None:
                if (
                    row.status in {"preparing", "ready"}
                    and row.generation_key == generation_key
                ):
                    return row_dict(row), False
                row.status = "preparing"
                row.error = None
                row.generation_key = generation_key
                row.updated_at = now
                await session.commit()
                return row_dict(row), True
            row = ArtifactPack(
                pack_id=str(uuid4()),
                user_id=user_id,
                match_id=match_id,
                generation_key=generation_key,
                status="preparing",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            try:
                await session.commit()
                return row_dict(row), True
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(ArtifactPack).where(
                        ArtifactPack.user_id == user_id,
                        ArtifactPack.match_id == match_id,
                    )
                )
                concurrent = result.scalars().one()
                return row_dict(concurrent), False

    async def upsert_pack(
        self, user_id: str, match_id: str, values: dict[str, Any]
    ) -> dict[str, Any]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(ArtifactPack).where(ArtifactPack.match_id == match_id)
            )
            row = result.scalars().first()
            now = utcnow()
            if row is None:
                row = ArtifactPack(
                    pack_id=str(uuid4()),
                    user_id=user_id,
                    match_id=match_id,
                    created_at=now,
                    updated_at=now,
                    **values,
                )
                session.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                row.updated_at = now
            await session.commit()
            return row_dict(row)

    async def get_pack(self, user_id: str, match_id: str) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(ArtifactPack).where(
                    ArtifactPack.user_id == user_id, ArtifactPack.match_id == match_id
                )
            )
            row = result.scalars().first()
            return row_dict(row) if row else None

    async def upsert_contact(
        self, user_id: str, data: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(Contact).where(
                    Contact.user_id == user_id,
                    Contact.identity_key == data["identity_key"],
                )
            )
            row = result.scalars().first()
            created = row is None
            now = utcnow()
            if row is None:
                row = Contact(
                    contact_id=str(uuid4()),
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                    **data,
                )
                session.add(row)
            else:
                preserved = {
                    "notes": row.notes,
                    "relationship_strength": row.relationship_strength,
                    "excluded": row.excluded,
                }
                for key, value in data.items():
                    setattr(row, key, value)
                row.notes = preserved["notes"]
                row.relationship_strength = preserved["relationship_strength"]
                row.excluded = preserved["excluded"]
                row.updated_at = now
            await session.commit()
            return row_dict(row), created

    async def list_contacts(self, user_id: str) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(Contact)
                .where(Contact.user_id == user_id)
                .order_by(Contact.company, Contact.last_name)
            )
            return [row_dict(row) for row in result.scalars().all()]

    async def replace_referrals(
        self, user_id: str, match_id: str, ranked: list[dict[str, Any]]
    ) -> None:
        async with db.session_factory() as session:
            await session.execute(
                delete(ReferralMatch).where(ReferralMatch.match_id == match_id)
            )
            for item in ranked:
                session.add(
                    ReferralMatch(
                        referral_match_id=str(uuid4()),
                        user_id=user_id,
                        match_id=match_id,
                        contact_id=item["contact_id"],
                        score=item["score"],
                        explanation=item["explanation"],
                    )
                )
            await session.commit()

    async def list_referrals(self, user_id: str, match_id: str) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(ReferralMatch, Contact)
                .join(Contact, Contact.contact_id == ReferralMatch.contact_id)
                .where(
                    ReferralMatch.user_id == user_id, ReferralMatch.match_id == match_id
                )
                .order_by(ReferralMatch.score.desc())
            )
            rows = []
            for referral, contact in result.all():
                data = row_dict(referral)
                data["contact"] = row_dict(contact)
                rows.append(data)
            return rows

    async def update_referral_history(
        self,
        user_id: str,
        match_id: str,
        referral_match_id: str,
        *,
        contacted: bool | None,
        response_notes: str | None,
    ) -> dict[str, Any] | None:
        async with db.session_factory() as session:
            result = await session.execute(
                select(ReferralMatch, Contact)
                .join(Contact, Contact.contact_id == ReferralMatch.contact_id)
                .where(
                    ReferralMatch.user_id == user_id,
                    ReferralMatch.match_id == match_id,
                    ReferralMatch.referral_match_id == referral_match_id,
                )
            )
            pair = result.first()
            if pair is None:
                return None
            referral, contact = pair
            if contacted is not None:
                referral.contacted_at = utcnow() if contacted else None
            if response_notes is not None:
                referral.response_notes = response_notes.strip() or None
            await session.commit()
            data = row_dict(referral)
            data["contact"] = row_dict(contact)
            return data

    async def upsert_fact(self, user_id: str, data: dict[str, Any]) -> dict[str, Any]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(CandidateFact).where(
                    CandidateFact.user_id == user_id,
                    CandidateFact.fact_key == data["fact_key"],
                )
            )
            row = result.scalars().first()
            now = utcnow()
            if row is None:
                row = CandidateFact(
                    fact_id=str(uuid4()),
                    user_id=user_id,
                    created_at=now,
                    updated_at=now,
                    **data,
                )
                session.add(row)
            else:
                for key, value in data.items():
                    setattr(row, key, value)
                row.updated_at = now
            await session.commit()
            return row_dict(row)

    async def list_facts(self, user_id: str) -> list[dict[str, Any]]:
        async with db.session_factory() as session:
            result = await session.execute(
                select(CandidateFact)
                .where(CandidateFact.user_id == user_id)
                .order_by(CandidateFact.category, CandidateFact.label)
            )
            return [row_dict(row) for row in result.scalars().all()]

    async def delete_fact(self, user_id: str, fact_id: str) -> bool:
        """Delete one user-owned candidate fact."""
        async with db.session_factory() as session:
            result = await session.execute(
                delete(CandidateFact).where(
                    CandidateFact.user_id == user_id,
                    CandidateFact.fact_id == fact_id,
                )
            )
            await session.commit()
            return bool(result.rowcount)

    async def audit(
        self,
        user_id: str,
        event_type: str,
        entity_type: str,
        entity_id: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        async with db.session_factory() as session:
            session.add(
                AuditEvent(
                    event_id=str(uuid4()),
                    user_id=user_id,
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    payload_json=payload or {},
                )
            )
            await session.commit()


scout_repository = ScoutRepository()

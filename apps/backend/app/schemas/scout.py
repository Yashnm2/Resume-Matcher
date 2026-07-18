"""Contracts for scheduled job discovery and application-pack preparation."""

from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class SearchProfileConfig(BaseModel):
    desired_titles: list[str] = Field(default_factory=list)
    adjacent_titles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    workplace_types: list[Literal["remote", "hybrid", "onsite"]] = Field(
        default_factory=list
    )
    seniority: list[str] = Field(default_factory=list)
    minimum_years_experience: int | None = Field(default=None, ge=0, le=60)
    maximum_years_experience: int | None = Field(default=None, ge=0, le=60)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    excluded_skills: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    blocked_companies: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    salary_floor: int | None = Field(default=None, ge=0)
    currency: str = "USD"
    visa_sponsorship_required: bool | None = None
    work_authorized_countries: list[str] = Field(default_factory=list)
    daily_pack_limit: int = Field(default=20, ge=1, le=20)
    reserve_limit: int = Field(default=10, ge=0, le=50)
    minimum_match_score: float = Field(default=70, ge=0, le=100)
    max_per_company: int = Field(default=2, ge=1, le=20)
    timezone: str = "Asia/Singapore"


class SearchProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    config: SearchProfileConfig = Field(default_factory=SearchProfileConfig)
    is_active: bool = True


class SearchProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    config: SearchProfileConfig | None = None
    is_active: bool | None = None


class SearchProfileResponse(SearchProfileCreate):
    profile_id: str
    user_id: str
    created_at: str
    updated_at: str


SourceType = Literal[
    "manual",
    "greenhouse",
    "lever",
    "ashby",
    "smartrecruiters",
    "careers_page",
    "email_alert",
    "linkedin_partner",
    "indeed_partner",
]


class JobSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    source_type: SourceType
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class JobSourceResponse(JobSourceCreate):
    source_id: str
    user_id: str
    status: str
    last_scan_at: str | None = None
    last_error: str | None = None
    created_at: str
    updated_at: str


class ManualJobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    company: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=50)
    source_url: HttpUrl | None = None
    location: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    compensation: str | None = None
    profile_id: str | None = None


class EmailAlertIngest(BaseModel):
    subject: str
    text: str
    sender: str
    html: str | None = None


class JobPostingResponse(BaseModel):
    posting_id: str
    source_id: str | None = None
    source_type: str
    source_url: str | None = None
    apply_url: str | None = None
    company: str
    title: str
    location: str | None = None
    workplace_type: str | None = None
    employment_type: str | None = None
    compensation: str | None = None
    description: str
    status: str
    posted_at: str | None = None
    discovered_at: str


class JobMatchResponse(BaseModel):
    match_id: str
    profile_id: str
    posting: JobPostingResponse
    eligible: bool
    score: float
    score_components: dict[str, Any]
    gaps: list[Any]
    explanation: str | None = None
    state: str
    selected_date: str | None = None
    daily_rank: int | None = None
    pack_status: str | None = None
    referral_count: int = 0


class ArtifactPackResponse(BaseModel):
    pack_id: str
    match_id: str
    resume_id: str | None = None
    cover_letter: str | None = None
    outreach_message: str | None = None
    referral_subject: str | None = None
    referral_email: str | None = None
    linkedin_message: str | None = None
    interview_prep: dict[str, Any] | None = None
    application_answers: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)
    llm_usage: dict[str, Any] = Field(default_factory=dict)
    status: str
    error: str | None = None
    created_at: str
    updated_at: str


class ArtifactPackUpdate(BaseModel):
    cover_letter: str | None = Field(default=None, max_length=30_000)
    outreach_message: str | None = Field(default=None, max_length=10_000)
    referral_subject: str | None = Field(default=None, max_length=300)
    referral_email: str | None = Field(default=None, max_length=10_000)
    linkedin_message: str | None = Field(default=None, max_length=3000)


class PreparePackRequest(BaseModel):
    force: bool = False
    regeneration_key: str | None = Field(default=None, min_length=8, max_length=120)


class ContactResponse(BaseModel):
    contact_id: str
    first_name: str
    last_name: str
    email: str | None = None
    company: str | None = None
    position: str | None = None
    profile_url: str | None = None
    connected_on: str | None = None
    relationship_strength: int = 0
    notes: str | None = None
    excluded: bool = False


class ReferralMatchResponse(BaseModel):
    referral_match_id: str
    contact: ContactResponse
    score: float
    explanation: str
    contacted_at: str | None = None
    response_notes: str | None = None


class ReferralHistoryUpdate(BaseModel):
    contacted: bool | None = None
    response_notes: str | None = Field(default=None, max_length=4000)


class CandidateFactCreate(BaseModel):
    fact_key: str = Field(pattern=r"^[a-z0-9_]+$", min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=4000)
    category: str = Field(default="general", max_length=80)
    sensitive: bool = False


class CandidateFactResponse(CandidateFactCreate):
    fact_id: str
    created_at: str
    updated_at: str


class ScoutRunResponse(BaseModel):
    run_id: str
    source_id: str
    status: str
    discovered_count: int
    created_count: int
    error: str | None = None
    started_at: str
    finished_at: str | None = None


class ContactImportResponse(BaseModel):
    imported: int
    updated: int
    skipped: int


class OpportunityStateUpdate(BaseModel):
    state: Literal[
        "discovered", "selected", "reserve", "preparing", "ready", "ignored", "applied"
    ]

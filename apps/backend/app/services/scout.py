"""Discovery, ranking, contact matching, and application-pack orchestration."""

import asyncio
import csv
import hashlib
import html
import io
import ipaddress
import json
import math
import re
import socket
from datetime import datetime, timezone
from email.utils import parseaddr
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
from playwright.async_api import async_playwright

from app.database import db
from app.llm import begin_usage_tracking, finish_usage_tracking
from app.scout_repository import scout_repository, utcnow
from app.services.cover_letter import generate_cover_letter, generate_outreach_message
from app.services.artifact_storage import store_application_pack
from app.services.improver import (
    apply_diffs,
    extract_job_keywords,
    generate_resume_diffs,
    generate_skill_target_plan,
    verify_diff_result,
    verify_skill_target_plan,
)
from app.services.interview_prep import generate_interview_prep


_WORD_RE = re.compile(r"[a-z0-9+#.]{2,}", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_URL_RE = re.compile(r"https?://[^\s<>'\"]+")
_COPY_METRIC_RE = re.compile(r"(?<!\w)(?:\$?\d+(?:\.\d+)?%?|\d+(?:\.\d+)?[xX])(?!\w)")
_SAFE_ALERT_SENDERS = (
    "linkedin.com",
    "indeed.com",
    "indeedmail.com",
    "indeedemail.com",
)
_BLOCKED_FACT_TERMS = {
    "age",
    "birth",
    "birthday",
    "race",
    "ethnicity",
    "gender",
    "sex",
    "religion",
    "disability",
    "veteran",
    "criminal",
    "conviction",
    "demographic",
    "legal_attestation",
    "attestation",
}


class _JsonLdParser(HTMLParser):
    """Extract JSON-LD script bodies without executing page content."""

    def __init__(self) -> None:
        super().__init__()
        self.in_json_ld = False
        self.parts: list[str] = []
        self.documents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("type") == "application/ld+json":
            self.in_json_ld = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_json_ld:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.in_json_ld:
            self.documents.append("".join(self.parts))
            self.in_json_ld = False


def normalize_text(value: str | None) -> str:
    """Normalize text for matching and canonical identities."""
    return " ".join((value or "").casefold().split())


def strip_html(value: str | None) -> str:
    """Convert small trusted-source HTML fragments to readable plain text."""
    return " ".join(html.unescape(_TAG_RE.sub(" ", value or "")).split())


def tokens(value: str | None) -> set[str]:
    """Return normalized lexical tokens."""
    return {match.group(0).casefold() for match in _WORD_RE.finditer(value or "")}


def canonical_key(
    company: str, title: str, location: str | None, external_id: str | None
) -> str:
    """Create a stable source-independent job identity."""

    def canonical(value: str | None) -> str:
        return " ".join(sorted(re.findall(r"[a-z0-9]+", (value or "").casefold())))

    material = "|".join(
        (canonical(company), canonical(title), canonical(location), external_id or "")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def description_hash(description: str) -> str:
    """Hash normalized job content for caching and change detection."""
    return hashlib.sha256(normalize_text(description).encode("utf-8")).hexdigest()


def content_embedding(text: str, dimensions: int = 256) -> list[float]:
    """Create a stable, local feature embedding suitable for cached similarity.

    Word and adjacent-word features preserve technical phrases without making an
    external model call during discovery. The vector is persisted with the
    description hash, so rescans do not repeat feature extraction.
    """
    words = sorted(tokens(text))
    ordered_words = _WORD_RE.findall(normalize_text(text))
    features = words + [
        f"{left}::{right}" for left, right in zip(ordered_words, ordered_words[1:])
    ]
    vector = [0.0] * dimensions
    for feature in features:
        digest = hashlib.sha256(feature.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] & 1 else -1.0
    magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [round(value / magnitude, 6) for value in vector]


def _score_overlap(needles: list[str], haystack: str) -> tuple[float, list[str]]:
    """Score phrase presence and return missing phrases."""
    normalized = normalize_text(haystack)
    clean = [item.strip() for item in needles if item.strip()]
    if not clean:
        return 100.0, []
    missing = [item for item in clean if normalize_text(item) not in normalized]
    return round(100 * (len(clean) - len(missing)) / len(clean), 2), missing


def _score_alternatives(options: list[str], value: str) -> float:
    """Score acceptable alternatives without penalizing unchosen options."""
    clean = [option.strip() for option in options if option.strip()]
    if not clean:
        return 100.0
    normalized_value = normalize_text(value)
    if any(normalize_text(option) in normalized_value for option in clean):
        return 100.0
    value_tokens = tokens(value)
    return round(
        max(
            100
            * len(value_tokens & tokens(option))
            / max(1, len(value_tokens | tokens(option)))
            for option in clean
        ),
        2,
    )


def assess_posting(
    posting: dict[str, Any], profile: dict[str, Any], resume: dict[str, Any] | None
) -> dict[str, Any]:
    """Apply deterministic gates and a transparent weighted match score."""
    config = profile["config_json"]
    haystack = " ".join(
        (posting["title"], posting["company"], posting.get("description") or "")
    )
    normalized = normalize_text(haystack)
    blocked = {normalize_text(item) for item in config.get("blocked_companies", [])}
    excluded_hits = [
        item
        for item in config.get("excluded_terms", []) + config.get("excluded_skills", [])
        if normalize_text(item) in normalized
    ]
    exclusion_reasons: list[str] = []
    if normalize_text(posting["company"]) in blocked:
        exclusion_reasons.append("blocked company")
    if excluded_hits:
        exclusion_reasons.append("excluded term or skill")
    configured_employment = {
        normalize_text(item) for item in config.get("employment_types", [])
    }
    actual_employment = normalize_text(posting.get("employment_type"))
    if (
        configured_employment
        and actual_employment
        and actual_employment not in configured_employment
    ):
        exclusion_reasons.append("employment type")
    if config.get("visa_sponsorship_required") and re.search(
        r"\b(?:no|not|unable to|cannot)\s+(?:provide\s+)?(?:visa\s+)?sponsor",
        normalized,
    ):
        exclusion_reasons.append("sponsorship unavailable")
    years = [int(value) for value in re.findall(r"\b(\d{1,2})\+?\s+years?", normalized)]
    requested_years = min(years) if years else None
    maximum_years = config.get("maximum_years_experience")
    if (
        requested_years is not None
        and maximum_years is not None
        and requested_years > int(maximum_years)
    ):
        exclusion_reasons.append("experience requirement")
    eligible = not exclusion_reasons

    required_score, missing_required = _score_overlap(
        config.get("required_skills", []), haystack
    )
    preferred_score, _ = _score_overlap(config.get("preferred_skills", []), haystack)
    skill_score = round(required_score * 0.75 + preferred_score * 0.25, 2)

    desired_titles = config.get("desired_titles", []) + config.get(
        "adjacent_titles", []
    )
    title_score = _score_alternatives(desired_titles, posting["title"])
    seniority = config.get("seniority", [])
    seniority_score = _score_alternatives(seniority, posting["title"])
    if seniority:
        title_score = round(title_score * 0.75 + seniority_score * 0.25, 2)

    locations = config.get("locations", [])
    location_score = _score_alternatives(locations, posting.get("location") or "")
    workplace_preferences = {
        normalize_text(item) for item in config.get("workplace_types", [])
    }
    workplace = normalize_text(posting.get("workplace_type"))
    if not workplace and "remote" in normalize_text(posting.get("location")):
        workplace = "remote"
    workplace_score = (
        100.0
        if not workplace_preferences
        else (
            100.0
            if workplace in workplace_preferences
            else (50.0 if not workplace else 0.0)
        )
    )
    if not locations:
        location_score = 100.0
    location_score = round(location_score * 0.6 + workplace_score * 0.4, 2)
    preferred_companies = config.get("preferred_companies", [])
    industries = config.get("industries", [])
    if not preferred_companies and not industries:
        company_score = 100.0
    elif normalize_text(posting["company"]) in {
        normalize_text(v) for v in preferred_companies
    }:
        company_score = 100.0
    elif any(normalize_text(industry) in normalized for industry in industries):
        company_score = 80.0
    else:
        company_score = 60.0

    resume_text = ""
    if resume:
        resume_text = f"{resume.get('content', '')} {json.dumps(resume.get('processed_data') or {})}"
    resume_embedding = content_embedding(resume_text)
    job_embedding = posting.get("embedding_json") or content_embedding(
        posting.get("description") or ""
    )
    semantic_score = max(
        0.0,
        min(
            100.0,
            round(100 * sum(a * b for a, b in zip(resume_embedding, job_embedding)), 2),
        ),
    )

    salary_floor = config.get("salary_floor")
    compensation_score = 100.0 if salary_floor is None else 50.0
    compensation_text = posting.get("compensation") or ""
    if salary_floor is not None and compensation_text:
        parsed_salaries: list[int] = []
        for amount, suffix in re.findall(
            r"(?:[$£€]\s*)?(\d{2,3}(?:,\d{3})?|\d+(?:\.\d+)?)\s*([kK]?)",
            compensation_text,
        ):
            value = float(amount.replace(",", ""))
            if suffix:
                value *= 1000
            if value >= 1000:
                parsed_salaries.append(int(value))
        if parsed_salaries:
            compensation_score = (
                100.0 if max(parsed_salaries) >= int(salary_floor) else 0.0
            )
    components = {
        "skills": skill_score,
        "semantic": round(semantic_score, 2),
        "title": title_score,
        "location": location_score,
        "company": company_score,
        "compensation": compensation_score,
    }
    score = round(
        skill_score * 0.30
        + semantic_score * 0.20
        + title_score * 0.15
        + location_score * 0.15
        + company_score * 0.10
        + compensation_score * 0.10,
        2,
    )
    gaps = missing_required + excluded_hits
    explanation = (
        f"{score:.0f}% fit: strongest signals are skills ({skill_score:.0f}) and title alignment "
        f"({title_score:.0f})."
    )
    if not eligible:
        score = 0.0
        explanation = f"Excluded before scoring: {', '.join(exclusion_reasons)}."
    if gaps:
        explanation += f" Review {len(gaps)} gap{'s' if len(gaps) != 1 else ''}."
    return {
        "eligible": eligible,
        "score": score,
        "components": components,
        "gaps": gaps,
        "explanation": explanation,
    }


def _assert_public_url(url: str) -> None:
    """Block non-HTTP and private-network targets to prevent SSRF."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only public HTTP(S) URLs are supported.")
    for address in socket.getaddrinfo(
        parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM
    ):
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise ValueError("Private and local network URLs are not supported.")


async def _robots_allowed(client: httpx.AsyncClient, url: str) -> bool:
    """Check robots.txt for the scout's declared user agent."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    response = await client.get(robots_url, follow_redirects=True)
    if response.status_code >= 400:
        return True
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    return parser.can_fetch("ResumeMatcherScout/1.0", url)


async def _robots_policy(
    client: httpx.AsyncClient, url: str
) -> tuple[bool, float, list[str]]:
    """Return robots permission, declared delay, and sitemap URLs."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        response = await client.get(robots_url, follow_redirects=True)
    except httpx.HTTPError:
        return True, 0.0, []
    if response.status_code >= 400:
        return True, 0.0, []
    parser = RobotFileParser()
    parser.set_url(robots_url)
    parser.parse(response.text.splitlines())
    delay = parser.crawl_delay("ResumeMatcherScout/1.0") or parser.crawl_delay("*") or 0
    if delay > 30:
        raise ValueError(
            "The careers site requires a crawl delay longer than this scanner supports."
        )
    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in response.text.splitlines()
        if line.casefold().startswith("sitemap:")
    ]
    return parser.can_fetch("ResumeMatcherScout/1.0", url), float(delay), sitemaps


def _jsonld_postings(
    page_html: str, *, source: dict[str, Any], page_url: str
) -> list[dict[str, Any]]:
    """Extract normalized JobPosting objects from one static or rendered page."""
    parser = _JsonLdParser()
    parser.feed(page_html)
    results: list[dict[str, Any]] = []
    config = source["config_json"]
    for document in parser.documents:
        try:
            decoded = json.loads(document)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, list):
            candidates = decoded
        elif isinstance(decoded, dict):
            graph = decoded.get("@graph")
            candidates = graph if isinstance(graph, list) else [decoded]
        else:
            continue
        for item in candidates:
            types = item.get("@type", []) if isinstance(item, dict) else []
            if isinstance(types, str):
                types = [types]
            if not isinstance(item, dict) or "JobPosting" not in types:
                continue
            org = item.get("hiringOrganization") or {}
            location = item.get("jobLocation") or {}
            address = location.get("address", {}) if isinstance(location, dict) else {}
            identifier = item.get("identifier") or {}
            results.append(
                _posting(
                    source_id=source["source_id"],
                    source_type="careers_page",
                    company=org.get("name", config.get("company", "Unknown company"))
                    if isinstance(org, dict)
                    else config.get("company", "Unknown company"),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    external_id=identifier.get("value")
                    if isinstance(identifier, dict)
                    else str(identifier) or None,
                    source_url=urljoin(page_url, item.get("url") or page_url),
                    location=address.get("addressLocality")
                    if isinstance(address, dict)
                    else None,
                    employment_type=item.get("employmentType"),
                    posted_at=item.get("datePosted"),
                    raw=item,
                )
            )
    return results


async def _sitemap_urls(
    client: httpx.AsyncClient, roots: list[str], domain: str, limit: int
) -> list[str]:
    """Read sitemap indexes recursively and return likely public job pages."""
    pending = list(dict.fromkeys(roots))[:5]
    visited: set[str] = set()
    candidates: list[str] = []
    while pending and len(visited) < 20 and len(candidates) < limit:
        sitemap_url = pending.pop(0)
        _assert_public_url(sitemap_url)
        if (
            urlparse(sitemap_url).netloc.casefold() != domain.casefold()
            or sitemap_url in visited
        ):
            continue
        visited.add(sitemap_url)
        try:
            response = await client.get(sitemap_url, follow_redirects=True)
            response.raise_for_status()
            root = ElementTree.fromstring(response.content)
        except (httpx.HTTPError, ElementTree.ParseError):
            continue
        locations = [
            node.text.strip()
            for node in root.iter()
            if node.tag.endswith("loc") and node.text
        ]
        if root.tag.endswith("sitemapindex"):
            pending.extend(locations[:20])
        else:
            likely = [
                url
                for url in locations
                if re.search(r"job|career|position|vacanc", url, re.IGNORECASE)
            ]
            candidates.extend(likely[: max(0, limit - len(candidates))])
    return list(dict.fromkeys(candidates))[:limit]


async def _render_public_pages(
    urls: list[str], *, source: dict[str, Any], crawl_delay: float
) -> list[dict[str, Any]]:
    """Render a small, robots-approved fallback set without authentication or evasion."""
    results: list[dict[str, Any]] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="ResumeMatcherScout/1.0 (+private job search assistant)"
        )
        page = await context.new_page()

        async def protect_request(route: Any) -> None:
            try:
                request_url = route.request.url
                if request_url.startswith(("data:", "blob:")):
                    await route.continue_()
                    return
                _assert_public_url(request_url)
                await route.continue_()
            except (ValueError, OSError):
                await route.abort()

        await page.route("**/*", protect_request)
        try:
            for index, url in enumerate(urls):
                if index and crawl_delay:
                    await asyncio.sleep(crawl_delay)
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(1200)
                results.extend(
                    _jsonld_postings(
                        await page.content(), source=source, page_url=page.url
                    )
                )
        finally:
            await context.close()
            await browser.close()
    return results


def _posting(
    *,
    source_id: str | None,
    source_type: str,
    company: str,
    title: str,
    description: str,
    external_id: str | None = None,
    source_url: str | None = None,
    apply_url: str | None = None,
    location: str | None = None,
    workplace_type: str | None = None,
    employment_type: str | None = None,
    compensation: str | None = None,
    posted_at: str | None = None,
    raw: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a normalized posting payload."""
    clean_description = strip_html(description)
    return {
        "source_id": source_id,
        "external_id": external_id,
        "canonical_key": canonical_key(company, title, location, external_id),
        "source_type": source_type,
        "source_url": source_url,
        "apply_url": apply_url or source_url,
        "company": company.strip() or "Unknown company",
        "title": title.strip() or "Untitled role",
        "location": location,
        "workplace_type": workplace_type,
        "employment_type": employment_type,
        "compensation": compensation,
        "description": clean_description,
        "description_hash": description_hash(clean_description),
        "embedding_json": content_embedding(clean_description),
        "embedding_model": "local-feature-v1",
        "raw_json": raw or {},
        "status": "active" if len(clean_description) >= 50 else "needs_description",
        "posted_at": posted_at,
        "expires_at": None,
        "updated_at": utcnow(),
    }


async def discover_source(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Fetch and normalize one configured source using its public contract."""
    source_type = source["source_type"]
    config = source["config_json"]
    source_id = source["source_id"]
    if source_type in {"linkedin_partner", "indeed_partner"}:
        raise ValueError("Partner API access is not configured for this source.")
    if source_type in {"manual", "email_alert"}:
        return []

    timeout = httpx.Timeout(30.0, connect=10.0)
    headers = {"User-Agent": "ResumeMatcherScout/1.0 (+private job search assistant)"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        if source_type == "greenhouse":
            token = str(config["board_token"])
            url = (
                f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
            )
            response = await client.get(url)
            response.raise_for_status()
            return [
                _posting(
                    source_id=source_id,
                    source_type=source_type,
                    company=config.get("company", token),
                    title=item.get("title", ""),
                    description=item.get("content", ""),
                    external_id=str(item.get("id")),
                    source_url=item.get("absolute_url"),
                    location=(item.get("location") or {}).get("name"),
                    posted_at=item.get("updated_at"),
                    raw=item,
                )
                for item in response.json().get("jobs", [])
            ]
        if source_type == "lever":
            site = str(config["site"])
            url = f"https://api.lever.co/v0/postings/{site}?mode=json"
            response = await client.get(url)
            response.raise_for_status()
            return [
                _posting(
                    source_id=source_id,
                    source_type=source_type,
                    company=config.get("company", site),
                    title=item.get("text", ""),
                    description=f"{item.get('descriptionPlain', '')} {item.get('additionalPlain', '')}",
                    external_id=item.get("id"),
                    source_url=item.get("hostedUrl"),
                    apply_url=item.get("applyUrl"),
                    location=(item.get("categories") or {}).get("location"),
                    employment_type=(item.get("categories") or {}).get("commitment"),
                    raw=item,
                )
                for item in response.json()
            ]
        if source_type == "ashby":
            board = str(config["board_name"])
            url = f"https://api.ashbyhq.com/posting-api/job-board/{board}?includeCompensation=true"
            response = await client.get(url)
            response.raise_for_status()
            return [
                _posting(
                    source_id=source_id,
                    source_type=source_type,
                    company=config.get("company", board),
                    title=item.get("title", ""),
                    description=item.get(
                        "descriptionPlain", item.get("descriptionHtml", "")
                    ),
                    external_id=item.get("id"),
                    source_url=item.get("jobUrl"),
                    apply_url=item.get("applyUrl"),
                    location=item.get("location"),
                    workplace_type=item.get("workplaceType"),
                    employment_type=item.get("employmentType"),
                    compensation=json.dumps(item.get("compensation"))
                    if item.get("compensation")
                    else None,
                    posted_at=item.get("publishedAt"),
                    raw=item,
                )
                for item in response.json().get("jobs", [])
                if item.get("isListed", True)
            ]
        if source_type == "smartrecruiters":
            company_id = str(config["company_id"])
            url = f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings?limit=100"
            response = await client.get(url)
            response.raise_for_status()
            results = []
            for item in response.json().get("content", []):
                posting_id = item.get("id")
                detail = await client.get(
                    f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings/{posting_id}"
                )
                detail.raise_for_status()
                payload = detail.json()
                sections = payload.get("jobAd", {}).get("sections", {})
                description = " ".join(
                    str(section.get("text", ""))
                    for section in sections.values()
                    if isinstance(section, dict)
                )
                location_data = payload.get("location") or {}
                results.append(
                    _posting(
                        source_id=source_id,
                        source_type=source_type,
                        company=payload.get("company", {}).get(
                            "name", config.get("company", company_id)
                        ),
                        title=payload.get("name", item.get("name", "")),
                        description=description,
                        external_id=posting_id,
                        source_url=payload.get("ref"),
                        location=location_data.get("fullLocation"),
                        raw=payload,
                    )
                )
            return results
        if source_type == "careers_page":
            url = str(config["url"])
            _assert_public_url(url)
            allowed, crawl_delay, robots_sitemaps = await _robots_policy(client, url)
            if not allowed:
                raise ValueError("The careers page is disallowed by robots.txt.")
            parsed = urlparse(url)
            sitemap_roots = robots_sitemaps or [
                f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
            ]
            max_pages = min(100, max(1, int(config.get("max_pages", 40))))
            pages = [url] + await _sitemap_urls(
                client, sitemap_roots, parsed.netloc, max_pages - 1
            )
            results: list[dict[str, Any]] = []
            approved_pages: list[str] = []
            for index, page_url in enumerate(pages):
                if index and crawl_delay:
                    await asyncio.sleep(crawl_delay)
                page_allowed, _, _ = await _robots_policy(client, page_url)
                if not page_allowed:
                    continue
                approved_pages.append(page_url)
                response = await client.get(page_url, follow_redirects=True)
                response.raise_for_status()
                _assert_public_url(str(response.url))
                results.extend(
                    _jsonld_postings(
                        response.text, source=source, page_url=str(response.url)
                    )
                )
            if not results and config.get("render_javascript"):
                browser_limit = min(10, max(1, int(config.get("browser_max_pages", 5))))
                results = await _render_public_pages(
                    approved_pages[:browser_limit],
                    source=source,
                    crawl_delay=crawl_delay,
                )
            return results
    return []


async def ingest_and_score(
    user_id: str, data: dict[str, Any], profile_id: str | None = None
) -> tuple[dict[str, Any], bool]:
    """Persist one posting and score it against active profiles."""
    posting, created = await scout_repository.upsert_posting(user_id, data)
    profiles = await scout_repository.list_profiles(user_id)
    if profile_id:
        profiles = [
            profile for profile in profiles if profile["profile_id"] == profile_id
        ]
    master = await db.get_master_resume(user_id)
    for profile in profiles:
        if profile["is_active"]:
            assessment = assess_posting(posting, profile, master)
            await scout_repository.upsert_match(
                user_id, profile["profile_id"], posting["posting_id"], assessment
            )
    return posting, created


async def scan_source(user_id: str, source_id: str) -> dict[str, Any]:
    """Execute one observable, idempotent source scan."""
    source = await scout_repository.get_source(user_id, source_id)
    if source is None:
        raise ValueError("Source not found.")
    run = await scout_repository.start_run(user_id, source_id)
    created_count = 0
    try:
        discovered = await discover_source(source)
        for item in discovered:
            _, created = await ingest_and_score(user_id, item)
            created_count += int(created)
        await scout_repository.update_source_health(
            user_id, source_id, status="healthy", error=None
        )
        completed = await scout_repository.finish_run(
            run["run_id"],
            status="completed",
            discovered_count=len(discovered),
            created_count=created_count,
        )
        await scout_repository.audit(
            user_id,
            "source.scan.completed",
            "job_source",
            source_id,
            {"created": created_count},
        )
        return completed or run
    except Exception as exc:
        await scout_repository.update_source_health(
            user_id, source_id, status="error", error=str(exc)[:1000]
        )
        await scout_repository.finish_run(
            run["run_id"],
            status="failed",
            discovered_count=0,
            created_count=0,
            error=str(exc)[:1000],
        )
        raise


async def import_linkedin_contacts(user_id: str, content: bytes) -> dict[str, int]:
    """Upsert LinkedIn Connections.csv while preserving user annotations."""
    text = content.decode("utf-8-sig", errors="replace")
    header_index = next(
        (
            index
            for index, line in enumerate(text.splitlines())
            if "First Name" in line and "Last Name" in line
        ),
        0,
    )
    reader = csv.DictReader(io.StringIO("\n".join(text.splitlines()[header_index:])))
    imported = updated = skipped = 0
    for item in reader:
        first_name = (item.get("First Name") or "").strip()
        last_name = (item.get("Last Name") or "").strip()
        if not first_name and not last_name:
            skipped += 1
            continue
        profile_url = (item.get("URL") or item.get("Profile URL") or "").strip() or None
        email = (item.get("Email Address") or "").strip() or None
        company = (item.get("Company") or "").strip() or None
        identity = (
            profile_url
            or email
            or normalize_text(f"{first_name}|{last_name}|{company}")
        )
        _, created = await scout_repository.upsert_contact(
            user_id,
            {
                "identity_key": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "first_name": first_name,
                "last_name": last_name,
                "email": email,
                "company": company,
                "company_normalized": normalize_text(company),
                "position": (item.get("Position") or "").strip() or None,
                "profile_url": profile_url,
                "connected_on": (item.get("Connected On") or "").strip() or None,
            },
        )
        imported += int(created)
        updated += int(not created)
    return {"imported": imported, "updated": updated, "skipped": skipped}


async def rank_referrals(user_id: str, match: dict[str, Any]) -> list[dict[str, Any]]:
    """Rank up to three explainable first-degree contacts for a matched job."""
    contacts = await scout_repository.list_contacts(user_id)
    posting = match["posting"]
    target_company = normalize_text(posting["company"])
    title_tokens = tokens(posting["title"])
    ranked = []
    for contact in contacts:
        if contact["excluded"] or contact.get("company_normalized") != target_company:
            continue
        position_tokens = tokens(contact.get("position"))
        role_similarity = len(title_tokens & position_tokens) / max(
            1, len(title_tokens | position_tokens)
        )
        recency_score = 0.0
        connected_on = contact.get("connected_on")
        if connected_on:
            for date_format in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
                try:
                    age_days = (
                        datetime.now(timezone.utc).date()
                        - datetime.strptime(connected_on, date_format).date()
                    ).days
                    recency_score = max(0.0, 5.0 * (1 - age_days / 3650))
                    break
                except ValueError:
                    continue
        score = (
            65
            + role_similarity * 15
            + (5 if contact.get("email") else 0)
            + min(10, contact.get("relationship_strength", 0) * 2)
            + recency_score
        )
        reasons = ["works at the target company"]
        if role_similarity:
            reasons.append("has a role related to this vacancy")
        if contact.get("email"):
            reasons.append("has an email in your official export")
        if recency_score:
            reasons.append("is a relatively recent connection")
        ranked.append(
            {
                "contact_id": contact["contact_id"],
                "score": round(min(100, score), 2),
                "explanation": "; ".join(reasons).capitalize() + ".",
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    top = ranked[:3]
    await scout_repository.replace_referrals(user_id, match["match_id"], top)
    return await scout_repository.list_referrals(user_id, match["match_id"])


def _referral_evidence(
    resume_data: dict[str, Any], posting: dict[str, Any]
) -> list[str]:
    """Select two concise claims that already exist in the candidate's résumé."""
    jd_tokens = tokens(posting.get("description"))
    candidates: list[tuple[int, str]] = []
    additional = resume_data.get("additional") or {}
    skills = (
        additional.get("technicalSkills", []) if isinstance(additional, dict) else []
    )
    for skill in skills:
        if isinstance(skill, str) and tokens(skill) & jd_tokens:
            candidates.append((3, f"hands-on experience with {skill}"))
    for entry in resume_data.get("workExperience", []):
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        descriptions = entry.get("description") or []
        if isinstance(descriptions, str):
            descriptions = [descriptions]
        for description in descriptions:
            if not isinstance(description, str):
                continue
            overlap = len(tokens(description) & jd_tokens)
            if overlap:
                statement = " ".join(description.split())[:150].rstrip(" ,.;")
                candidates.append((overlap + 2, statement))
        if title and tokens(title) & jd_tokens:
            candidates.append((2, f"relevant experience as {title}"))
    unique: list[str] = []
    for _, statement in sorted(candidates, key=lambda item: item[0], reverse=True):
        if normalize_text(statement) not in {normalize_text(item) for item in unique}:
            unique.append(statement)
        if len(unique) == 2:
            break
    return unique


def referral_copy(
    contact: dict[str, Any] | None, posting: dict[str, Any], resume_data: dict[str, Any]
) -> tuple[str, str, str]:
    """Create a factual, low-pressure referral request without inventing a relationship."""
    name = contact["first_name"] if contact else "there"
    personal = resume_data.get("personalInfo") or {}
    sender_name = personal.get("name") or personal.get("fullName") or ""
    evidence = _referral_evidence(resume_data, posting)
    qualification_line = ""
    if evidence:
        qualification_line = (
            " Two relevant points from my background are "
            + " and ".join(evidence)
            + "."
        )
    if contact is None:
        subject = f"Interest in {posting['title']} at {posting['company']}"
        body = (
            f"Hello,\n\nI’m applying for the {posting['title']} role at {posting['company']}."
            f"{qualification_line} If you’re the appropriate person, I’d appreciate any guidance on the role or team. "
            "No pressure at all; if not, no response is needed.\n\nThank you"
        )
        if sender_name:
            body += f",\n{sender_name}"
        linkedin = (
            f"Hello — I’m applying for the {posting['title']} role at {posting['company']}."
            f"{qualification_line} If you’re the appropriate person, I’d appreciate any guidance. No pressure."
        )
        return subject, body, linkedin
    subject = f"Referral request — {posting['title']} at {posting['company']}"
    body = (
        f"Hi {name},\n\nI’m applying for the {posting['title']} role at {posting['company']} and noticed "
        f"that you work there.{qualification_line} I’ve attached a tailored résumé for context. "
        "If you feel comfortable after reviewing it, would you be open to referring me or sharing "
        "any advice about the team? No pressure at all.\n\nThank you"
    )
    if sender_name:
        body += f",\n{sender_name}"
    linkedin = (
        f"Hi {name} — I’m applying for the {posting['title']} role at {posting['company']}."
        f"{qualification_line} Would you be open to a referral or any advice on the team? No pressure at all."
    )
    return subject, body, linkedin


def _blocking_diff_warnings(warnings: list[str]) -> list[str]:
    prefixes = (
        "No changes were applied",
        "Section count changed",
        "Identity field changed",
        "Word count increased",
        "Possible invented metric",
    )
    return [warning for warning in warnings if warning.startswith(prefixes)]


def _cover_letter_issues(
    letter: str, resume_data: dict[str, Any], posting: dict[str, Any]
) -> list[str]:
    """Apply local factual and targeting checks to generated cover-letter copy."""
    issues: list[str] = []
    normalized = normalize_text(letter)
    if normalize_text(posting["company"]) not in normalized:
        issues.append("company name is missing")
    title_terms = tokens(posting["title"])
    if title_terms and len(title_terms & tokens(letter)) < max(
        1, len(title_terms) // 2
    ):
        issues.append("target role is missing or incorrect")
    resume_text = json.dumps(resume_data, ensure_ascii=False)
    invented_metrics = set(_COPY_METRIC_RE.findall(letter)) - set(
        _COPY_METRIC_RE.findall(resume_text)
    )
    if invented_metrics:
        issues.append("unsupported metrics: " + ", ".join(sorted(invented_metrics)))
    unsupported_familiarity = (
        "always admired",
        "long admired",
        "long followed",
        "deeply familiar with your",
        "i have followed your",
        "passionate about your company",
    )
    if any(phrase in normalized for phrase in unsupported_familiarity):
        issues.append("unsupported company familiarity or enthusiasm")
    evidence_sources: list[str] = []
    additional = resume_data.get("additional") or {}
    if isinstance(additional, dict):
        evidence_sources.extend(
            skill
            for skill in additional.get("technicalSkills", [])
            if isinstance(skill, str)
        )
    for entry in resume_data.get("workExperience", []):
        if not isinstance(entry, dict):
            continue
        descriptions = entry.get("description") or []
        evidence_sources.extend(
            [descriptions] if isinstance(descriptions, str) else descriptions
        )
    supported_connections = sum(
        1
        for source in evidence_sources
        if isinstance(source, str)
        and len(tokens(source) & tokens(letter)) >= min(3, max(1, len(tokens(source))))
    )
    if len(evidence_sources) >= 2 and supported_connections < 2:
        issues.append("fewer than two résumé-backed connections")
    return issues


async def _generate_verified_cover_letter(
    resume_data: dict[str, Any], posting: dict[str, Any]
) -> tuple[str, list[str]]:
    last_issues: list[str] = []
    job_context = (
        f"Company: {posting['company']}\nRole: {posting['title']}\n\n"
        f"{posting['description']}"
    )
    for _attempt in range(2):
        letter = await generate_cover_letter(resume_data, job_context)
        last_issues = _cover_letter_issues(letter, resume_data, posting)
        if not last_issues:
            return letter, []
    raise ValueError("Cover letter failed verification: " + "; ".join(last_issues))


async def _tailor_verified_resume(
    master: dict[str, Any], posting: dict[str, Any]
) -> tuple[dict[str, Any], list[Any], dict[str, Any], list[str]]:
    """Tailor only through verified field diffs and return field provenance."""
    original = master["processed_data"]
    keywords = await extract_job_keywords(posting["description"])
    skill_targets: list[dict[str, Any]] = []
    try:
        proposed = await generate_skill_target_plan(
            original_resume_data=original,
            job_description=posting["description"],
            job_keywords=keywords,
            language="en",
        )
        verified = verify_skill_target_plan(
            proposed,
            original_resume_data=original,
            job_keywords=keywords,
            job_description=posting["description"],
        )
        skill_targets = [
            item for item in verified.get("accepted", []) if isinstance(item, dict)
        ]
    except Exception:
        skill_targets = []

    last_warnings: list[str] = []
    for _attempt in range(2):
        generated = await generate_resume_diffs(
            original_resume=master["content"],
            job_description=posting["description"],
            job_keywords=keywords,
            original_resume_data=original,
            skill_targets=skill_targets,
        )
        result, applied, rejected = apply_diffs(
            original, generated.changes, skill_targets
        )
        warnings = verify_diff_result(original, result, applied, keywords)
        last_warnings = warnings
        if applied and not _blocking_diff_warnings(warnings):
            fields = {
                change.path: {
                    "action": change.action,
                    "original": change.original,
                    "tailored": change.value,
                    "reason": change.reason,
                    "source": {
                        "type": "master_resume",
                        "resume_id": master["resume_id"],
                    },
                }
                for change in applied
            }
            verification = {
                "passed": True,
                "applied_changes": len(applied),
                "rejected_changes": len(rejected),
                "warnings": warnings,
                "checks": [
                    "allowed paths",
                    "original-value match",
                    "identity preservation",
                    "metric provenance",
                    "section structure",
                ],
            }
            return (
                result,
                applied,
                {"fields": fields, "verification": verification},
                warnings,
            )
    detail = "; ".join(last_warnings) or "no safe changes were produced"
    raise ValueError(
        f"Résumé tailoring failed factual or structural verification: {detail}"
    )


def _fact_is_safe(fact: dict[str, Any]) -> bool:
    material = normalize_text(
        " ".join(str(fact.get(key) or "") for key in ("fact_key", "label", "category"))
    )
    fact_terms = tokens(material.replace("_", " "))
    blocked_terms = {part for term in _BLOCKED_FACT_TERMS for part in term.split("_")}
    return not fact.get("sensitive") and not bool(fact_terms & blocked_terms)


async def prepare_pack(
    user_id: str, match_id: str, regeneration_key: str | None = None
) -> dict[str, Any]:
    """Generate one idempotent application pack through the existing truthful services."""
    match = await scout_repository.get_match(user_id, match_id)
    if match is None:
        raise ValueError("Opportunity not found.")
    master = await db.get_master_resume(user_id)
    if master is None or not master.get("processed_data"):
        raise ValueError(
            "A processed master resume is required before preparing packs."
        )
    posting = match["posting"]
    if posting["status"] == "needs_description":
        raise ValueError(
            "A complete job description is required before preparing a pack."
        )

    generation_key = hashlib.sha256(
        f"pack-v2|{master['resume_id']}|{hashlib.sha256(master['content'].encode('utf-8')).hexdigest()}|{posting['description_hash']}|{regeneration_key or 'initial'}".encode()
    ).hexdigest()
    claimed_pack, claimed = await scout_repository.claim_pack(
        user_id, match_id, generation_key
    )
    if not claimed:
        if claimed_pack["status"] == "ready":
            return claimed_pack
        raise ValueError("This application pack is already being prepared.")
    await scout_repository.set_match_state(user_id, match_id, "preparing")
    usage_token = begin_usage_tracking()
    llm_usage: dict[str, Any] = {}
    try:
        (
            improved,
            applied_changes,
            provenance,
            verification_warnings,
        ) = await _tailor_verified_resume(master, posting)
        improved_text = json.dumps(improved, ensure_ascii=False)
        cover_letter, cover_warnings = await _generate_verified_cover_letter(
            improved, posting
        )
        job_context = f"Company: {posting['company']}\nRole: {posting['title']}\n\n{posting['description']}"
        outreach = await generate_outreach_message(improved, job_context)
        interview = await generate_interview_prep(improved, job_context)
        job = await db.create_job(
            posting["description"], resume_id=master["resume_id"], user_id=user_id
        )
        tailored = await db.create_resume(
            content=improved_text,
            content_type="json",
            filename="tailored_"
            + re.sub(
                r"[^a-zA-Z0-9_-]+", "_", f"{posting['company']}_{posting['title']}"
            )[:120]
            + ".json",
            is_master=False,
            parent_id=master["resume_id"],
            processed_data=improved,
            processing_status="ready",
            cover_letter=cover_letter,
            outreach_message=outreach,
            interview_prep=interview.model_dump_json(),
            title=f"{posting['company']} — {posting['title']}",
            user_id=user_id,
        )
        await db.create_improvement(
            original_resume_id=master["resume_id"],
            tailored_resume_id=tailored["resume_id"],
            job_id=job["job_id"],
            improvements=[change.model_dump(mode="json") for change in applied_changes],
            user_id=user_id,
        )
        referrals = await rank_referrals(user_id, match)
        contact = referrals[0]["contact"] if referrals else None
        subject, referral_email, linkedin = referral_copy(contact, posting, improved)
        facts = await scout_repository.list_facts(user_id)
        safe_answers = {
            fact["label"]: fact["value"] for fact in facts if _fact_is_safe(fact)
        }
        storage_manifest: dict[str, str] = {}
        storage_warning: str | None = None
        try:
            storage_manifest = await store_application_pack(
                user_id=user_id,
                pack_id=f"{claimed_pack['pack_id']}/{generation_key[:12]}",
                resume_data=improved,
                cover_letter=cover_letter,
                referral_email=referral_email,
                outreach_message=outreach,
                interview_prep=interview.model_dump(mode="json"),
            )
        except httpx.HTTPError as exc:
            storage_warning = f"Private artifact upload failed: {exc}"
            await scout_repository.audit(
                user_id,
                "pack.storage.failed",
                "job_match",
                match_id,
                {"error": str(exc)[:500]},
            )
        llm_usage = finish_usage_tracking(usage_token)
        usage_token = None
        pack = await scout_repository.upsert_pack(
            user_id,
            match_id,
            {
                "generation_key": generation_key,
                "resume_id": tailored["resume_id"],
                "cover_letter": cover_letter,
                "outreach_message": outreach,
                "referral_subject": subject,
                "referral_email": referral_email,
                "linkedin_message": linkedin,
                "interview_prep": interview.model_dump(mode="json"),
                "application_answers": safe_answers,
                "provenance_json": {
                    "master_resume_id": master["resume_id"],
                    "job_posting_id": posting["posting_id"],
                    "policy": "Every tailored claim must be supported by the immutable master resume.",
                    **provenance,
                },
                "verification_json": {
                    "passed": True,
                    "warnings": verification_warnings
                    + cover_warnings
                    + ([storage_warning] if storage_warning else []),
                    "resume": provenance["verification"],
                    "cover_letter": {
                        "passed": True,
                        "checks": [
                            "correct company",
                            "correct role",
                            "metric provenance",
                            "two evidence connections",
                        ],
                    },
                },
                "storage_manifest": storage_manifest,
                "llm_usage_json": llm_usage,
                "status": "ready",
                "error": None,
            },
        )
        await scout_repository.set_match_state(user_id, match_id, "ready")
        await scout_repository.audit(
            user_id,
            "pack.prepared",
            "job_match",
            match_id,
            {"pack_id": pack["pack_id"]},
        )
        return pack
    except Exception as exc:
        if usage_token is not None:
            llm_usage = finish_usage_tracking(usage_token)
        await scout_repository.upsert_pack(
            user_id,
            match_id,
            {"status": "failed", "error": str(exc)[:1000], "llm_usage_json": llm_usage},
        )
        await scout_repository.set_match_state(user_id, match_id, "selected")
        raise


def manual_posting(
    payload: dict[str, Any], source_type: str = "manual"
) -> dict[str, Any]:
    """Normalize a manually supplied job."""
    return _posting(
        source_id=None,
        source_type=source_type,
        company=payload["company"],
        title=payload["title"],
        description=payload["description"],
        source_url=payload.get("source_url"),
        location=payload.get("location"),
        workplace_type=payload.get("workplace_type"),
        employment_type=payload.get("employment_type"),
        compensation=payload.get("compensation"),
    )


def email_alert_posting(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a cautious incomplete posting from a user-owned job-alert email."""
    sender_address = parseaddr(payload["sender"])[1].casefold()
    sender_domain = sender_address.rpartition("@")[2]
    if not sender_domain or not any(
        sender_domain == domain or sender_domain.endswith(f".{domain}")
        for domain in _SAFE_ALERT_SENDERS
    ):
        raise ValueError("Unsupported job-alert sender.")
    text = strip_html(f"{payload.get('text', '')} {payload.get('html', '')}")
    urls = _URL_RE.findall(f"{payload.get('text', '')} {payload.get('html', '')}")
    subject = payload["subject"].strip()
    title, _, company = subject.partition(" at ")
    posting = _posting(
        source_id=None,
        source_type="email_alert",
        company=company or "Unknown company",
        title=title or subject,
        description=text[:20_000],
        source_url=urls[0] if urls else None,
        raw={"sender": payload["sender"], "subject": subject},
    )
    posting["status"] = "needs_description"
    return posting


async def resolve_email_alert(payload: dict[str, Any]) -> dict[str, Any]:
    """Resolve an alert to a public company/ATS posting without visiting job boards."""
    fallback = email_alert_posting(payload)
    raw_content = f"{payload.get('text', '')} {payload.get('html', '')}"
    urls = list(dict.fromkeys(_URL_RE.findall(raw_content)))[:10]
    blocked_hosts = ("linkedin.com", "indeed.com", "indeedemail.com", "indeedmail.com")
    timeout = httpx.Timeout(20.0, connect=8.0)
    headers = {"User-Agent": "ResumeMatcherScout/1.0 (+private job search assistant)"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        for candidate_url in urls:
            host = (urlparse(candidate_url).hostname or "").casefold()
            if any(
                host == domain or host.endswith(f".{domain}")
                for domain in blocked_hosts
            ):
                continue
            try:
                _assert_public_url(candidate_url)
                if not await _robots_allowed(client, candidate_url):
                    continue
                response = await client.get(candidate_url, follow_redirects=True)
                response.raise_for_status()
                _assert_public_url(str(response.url))
                source = {
                    "source_id": None,
                    "config_json": {"company": fallback["company"]},
                }
                resolved = _jsonld_postings(
                    response.text, source=source, page_url=str(response.url)
                )
                if resolved:
                    result = resolved[0]
                    result["source_type"] = "email_alert"
                    result["raw_json"] = {
                        **result.get("raw_json", {}),
                        "alert": fallback["raw_json"],
                        "resolved_from": candidate_url,
                    }
                    return result
            except (ValueError, httpx.HTTPError):
                continue
    return fallback

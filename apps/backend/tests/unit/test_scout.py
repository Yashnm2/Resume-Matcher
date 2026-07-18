"""Deterministic safeguards for the job-scout pipeline."""

import pytest

from app.services.scout import (
    _fact_is_safe,
    _score_alternatives,
    _cover_letter_issues,
    assess_posting,
    canonical_key,
    content_embedding,
    email_alert_posting,
    referral_copy,
)


def test_canonical_key_deduplicates_case_and_spacing():
    assert canonical_key(
        "Acme, Inc.", "Backend  Engineer", "Remote", None
    ) == canonical_key(" ACME INC ", "backend engineer", "remote", None)


def test_assess_posting_applies_hard_exclusions_before_scoring(sample_resume):
    result = assess_posting(
        {
            "title": "Senior Backend Engineer",
            "company": "Blocked Co",
            "location": "Remote",
            "workplace_type": "remote",
            "description": "Python FastAPI PostgreSQL platform engineering",
        },
        {
            "config_json": {
                "desired_titles": ["Backend Engineer"],
                "required_skills": ["Python", "FastAPI"],
                "blocked_companies": ["Blocked Co"],
                "minimum_match_score": 70,
            }
        },
        {"processed_data": sample_resume},
    )
    assert result["eligible"] is False
    assert result["score"] == 0
    assert "blocked company" in result["explanation"].lower()


def test_alternative_preferences_do_not_penalize_other_valid_options():
    assert _score_alternatives(["Remote", "Singapore"], "Remote") == 100
    assert _score_alternatives(["Backend Engineer", "Platform Engineer"], "Senior Backend Engineer") == 100


def test_content_embedding_is_stable_and_normalized():
    first = content_embedding("Python FastAPI platform engineering")
    second = content_embedding("Python FastAPI platform engineering")
    assert first == second
    assert len(first) == 256
    assert sum(value * value for value in first) == pytest.approx(1.0, abs=1e-4)


def test_assess_posting_explains_missing_skills(sample_resume):
    result = assess_posting(
        {
            "title": "Backend Engineer",
            "company": "Acme",
            "location": "Remote",
            "workplace_type": "remote",
            "description": "Build Python services for a distributed data platform.",
        },
        {
            "config_json": {
                "desired_titles": ["Backend Engineer"],
                "required_skills": ["Python", "Kubernetes"],
                "workplace_types": ["remote"],
                "minimum_match_score": 0,
            }
        },
        {"processed_data": sample_resume},
    )
    assert result["eligible"] is True
    assert "Kubernetes" in result["gaps"]
    assert set(result["components"]) == {
        "skills",
        "semantic",
        "title",
        "location",
        "company",
        "compensation",
    }


def test_referral_copy_never_invents_contact_or_email(sample_resume):
    subject, email, linkedin = referral_copy(
        None,
        {"title": "Backend Engineer", "company": "Acme"},
        sample_resume,
    )
    assert subject.endswith("Backend Engineer at Acme")
    assert "No pressure" in email
    assert "@" not in email
    assert "noticed that you work there" not in email
    assert "Backend Engineer" in linkedin


def test_alert_sender_requires_exact_supported_domain():
    payload = {
        "subject": "Backend Engineer at Acme",
        "sender": "alerts@linkedin.com.evil.example",
        "text": "A sufficiently long public job alert description with a public role URL.",
    }
    with pytest.raises(ValueError, match="Unsupported"):
        email_alert_posting(payload)
    payload["sender"] = "LinkedIn Jobs <jobs-noreply@linkedin.com>"
    assert email_alert_posting(payload)["company"] == "Acme"


@pytest.mark.parametrize(
    "fact_key,label,expected",
    [
        ("notice_period", "Notice period", True),
        ("work_authorization", "Work authorization", True),
        ("veteran_status", "Veteran status", False),
        ("screening", "Criminal history", False),
        ("pronouns", "Gender identity", False),
    ],
)
def test_candidate_fact_sensitive_categories_are_never_auto_answered(
    fact_key, label, expected
):
    assert (
        _fact_is_safe(
            {
                "fact_key": fact_key,
                "label": label,
                "category": "general",
                "sensitive": False,
            }
        )
        is expected
    )


def test_cover_letter_verifier_rejects_wrong_target_and_invented_metrics(sample_resume):
    issues = _cover_letter_issues(
        "I have always admired Other Co. I improved systems by 99%.",
        sample_resume,
        {"company": "Acme", "title": "Backend Engineer"},
    )
    assert "company name is missing" in issues
    assert any(issue.startswith("unsupported metrics") for issue in issues)
    assert "unsupported company familiarity or enthusiasm" in issues

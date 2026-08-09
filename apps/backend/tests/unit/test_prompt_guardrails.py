"""Content guards on the tailoring prompts.

Two invariants this locks:
1. JD-keyword incorporation is the DEFAULT across sections (the maintainer goal).
2. The anti-fabrication clauses stay present. Per the truthfulness audit,
   invented bullet *narrative* (e.g. "led 12 engineers") is NOT caught by
   verify_diff_result (its metric regex misses bare counts) or verify_alignment
   (which only checks skills/certs/companies) — so these prompt clauses are the
   ONLY guard. If a future edit drops them, this test fails loudly.
"""

from app.prompts.templates import (
    COVER_LETTER_PROMPT,
    DIFF_IMPROVE_PROMPT,
    INTERVIEW_PREP_PROMPT,
    OUTREACH_MESSAGE_PROMPT,
    SKILL_TARGET_PLAN_PROMPT,
)
from app.prompts.enrichment import (
    ANALYZE_RESUME_PROMPT,
    ENHANCE_DESCRIPTION_PROMPT,
)
from app.prompts.refinement import KEYWORD_INJECTION_PROMPT, VALIDATION_POLISH_PROMPT
from app.prompts.resume_wizard import RESUME_WIZARD_TURN_PROMPT


class TestJdIncorporationIsDefault:
    def test_diff_prompt_reframes_by_default(self):
        assert "By DEFAULT" in DIFF_IMPROVE_PROMPT
        assert "reframe" in DIFF_IMPROVE_PROMPT.lower()

    def test_keyword_injection_targets_every_section_by_default(self):
        assert "EVERY section" in KEYWORD_INJECTION_PROMPT
        assert "DEFAULT" in KEYWORD_INJECTION_PROMPT

    def test_cover_letter_reframes_in_jd_terminology(self):
        assert "terminology" in COVER_LETTER_PROMPT.lower()


class TestAntiFabricationClausesPresent:
    def test_diff_prompt_keeps_no_invented_work_clauses(self):
        # rule 11's reframe permission must ship WITH its anti-fabrication clause
        assert "Do NOT add new work, metrics, or responsibilities" in DIFF_IMPROVE_PROMPT
        # rule 2 must remain
        assert "Do not invent metrics or achievements not supported by the original resume" in DIFF_IMPROVE_PROMPT

    def test_keyword_injection_keeps_no_invent_clauses(self):
        assert "do not invent new content, metrics, or work history" in KEYWORD_INJECTION_PROMPT
        assert "Do NOT add skills, technologies, or certifications not in the master resume" in KEYWORD_INJECTION_PROMPT

    def test_cover_letter_keeps_no_invent_clauses(self):
        assert "Do NOT invent information not in the resume" in COVER_LETTER_PROMPT
        assert "proven experience supports it" in COVER_LETTER_PROMPT

    def test_interview_prep_keeps_no_fabrication_guardrails(self):
        assert "Do NOT invent experience" in INTERVIEW_PREP_PROMPT
        assert "tools, employers, metrics, certifications, skills" in INTERVIEW_PREP_PROMPT
        assert "Skill gaps are preparation targets only" in INTERVIEW_PREP_PROMPT
        assert "Do NOT translate JSON property names" in INTERVIEW_PREP_PROMPT
        assert "role_fit_analysis" in INTERVIEW_PREP_PROMPT
        assert "talking_points" in INTERVIEW_PREP_PROMPT


class TestEvidenceBasedWritingRubric:
    def test_tailoring_builds_requirement_to_evidence_map(self):
        assert "requirement-to-evidence map" in DIFF_IMPROVE_PROMPT
        assert "explicit must-haves" in DIFF_IMPROVE_PROMPT
        assert "Skip any requirement without supporting resume evidence" in DIFF_IMPROVE_PROMPT

    def test_tailoring_uses_accomplishment_bullets_without_fake_metrics(self):
        assert "Action + Project/Task + Result" in DIFF_IMPROVE_PROMPT
        assert "scope, method, complexity, audience" in DIFF_IMPROVE_PROMPT
        assert "one accomplishment" in DIFF_IMPROVE_PROMPT

    def test_tailoring_avoids_keyword_stuffing(self):
        assert "Never keyword-stuff" in DIFF_IMPROVE_PROMPT
        assert "Never force a keyword into an unrelated bullet" in KEYWORD_INJECTION_PROMPT
        assert "keywords are natural" in VALIDATION_POLISH_PROMPT.lower()

    def test_skill_plan_requires_substantive_evidence(self):
        assert "substantive evidence" in SKILL_TARGET_PLAN_PROMPT
        assert "benefits or company boilerplate" in SKILL_TARGET_PLAN_PROMPT

    def test_enrichment_asks_for_evidence_without_demanding_numbers(self):
        assert "do not pressure the candidate to invent a metric" in ANALYZE_RESUME_PROMPT
        assert "does not need every element" in ANALYZE_RESUME_PROMPT
        assert "Action + Project/Task + Result" in ENHANCE_DESCRIPTION_PROMPT

    def test_wizard_builds_concise_truthful_master_resume(self):
        assert "do not pad to reach a count" in RESUME_WIZARD_TURN_PROMPT
        assert "Never convert a qualitative statement into a made-up number" in RESUME_WIZARD_TURN_PROMPT
        assert "summary should be 2-4 concise lines" in RESUME_WIZARD_TURN_PROMPT


class TestApplicationWritingRubric:
    def test_cover_letter_proves_fit_instead_of_repeating_resume(self):
        assert "TWO highest-priority job needs" in COVER_LETTER_PROMPT
        assert "Do not merely restate resume bullets" in COVER_LETTER_PROMPT
        assert "why that evidence matters for this role" in COVER_LETTER_PROMPT
        assert "Do not invent a hiring manager" in COVER_LETTER_PROMPT

    def test_outreach_has_specific_context_and_low_friction_ask(self):
        assert "Never fabricate familiarity or a referral" in OUTREACH_MESSAGE_PROMPT
        assert "15-20 minute conversation" in OUTREACH_MESSAGE_PROMPT
        assert "not demanding a job or referral" in OUTREACH_MESSAGE_PROMPT

    def test_interview_prep_uses_truthful_star_when_possible(self):
        assert "compact STAR structure" in INTERVIEW_PREP_PROMPT
        assert "Do not invent missing STAR elements" in INTERVIEW_PREP_PROMPT
        assert "one verified resume fact to one job need" in INTERVIEW_PREP_PROMPT

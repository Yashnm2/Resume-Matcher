"""Fail-closed guard for production-locked LLM features."""

from fastapi import HTTPException

from app.config import settings

LLM_CONFIGURATION_REQUIRED_DETAIL = (
    "AI features are unavailable because the production API key is not configured."
)


def locked_llm_unavailable(
    *,
    locked: bool | None = None,
    provider: str | None = None,
    api_key: str | None = None,
) -> bool:
    """Return whether a locked remote-provider configuration lacks its key."""
    resolved_locked = (
        settings.llm_configuration_locked if locked is None else locked
    )
    resolved_provider = (provider or settings.llm_provider).strip().lower()
    resolved_key = settings.llm_api_key if api_key is None else api_key
    return (
        resolved_locked
        and resolved_provider not in {"ollama", "openai_compatible"}
        and not bool(resolved_key)
    )


def require_locked_llm_configuration() -> None:
    """Raise a safe, actionable response before entering model workflows."""
    if locked_llm_unavailable():
        raise HTTPException(
            status_code=503,
            detail=LLM_CONFIGURATION_REQUIRED_DETAIL,
        )

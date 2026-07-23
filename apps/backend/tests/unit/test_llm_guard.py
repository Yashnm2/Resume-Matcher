"""Production-locked LLM features fail closed with an actionable response."""

import pytest
from fastapi import HTTPException

from app.routers.llm_guard import (
    LLM_CONFIGURATION_REQUIRED_DETAIL,
    locked_llm_unavailable,
    require_locked_llm_configuration,
)


def test_locked_remote_provider_without_key_is_unavailable() -> None:
    assert locked_llm_unavailable(
        locked=True,
        provider="openai",
        api_key="",
    )


def test_unlocked_or_local_provider_does_not_require_remote_key() -> None:
    assert not locked_llm_unavailable(
        locked=False,
        provider="openai",
        api_key="",
    )
    assert not locked_llm_unavailable(
        locked=True,
        provider="ollama",
        api_key="",
    )


def test_guard_returns_safe_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.routers.llm_guard.locked_llm_unavailable",
        lambda: True,
    )
    with pytest.raises(HTTPException) as exc_info:
        require_locked_llm_configuration()
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == LLM_CONFIGURATION_REQUIRED_DETAIL

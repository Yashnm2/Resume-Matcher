"""Tests for free Hugging Face Space persistence."""

import sqlite3

import pytest

from app.services import hf_state


def test_disabled_without_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hf_state.settings, "hf_state_repo_id", None)
    monkeypatch.setattr(hf_state.settings, "hf_token", None)
    assert hf_state.enabled() is False


def test_snapshot_upload_uses_consistent_sqlite_backup(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    database = tmp_path / "resume_matcher.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE sample (value TEXT)")
        connection.execute("INSERT INTO sample VALUES ('saved')")

    uploaded: dict[str, object] = {}

    class FakeApi:
        def __init__(self, token: str):
            uploaded["token"] = token

        def upload_file(self, **kwargs):
            snapshot = sqlite3.connect(kwargs["path_or_fileobj"])
            try:
                uploaded["value"] = snapshot.execute(
                    "SELECT value FROM sample"
                ).fetchone()[0]
            finally:
                snapshot.close()
            uploaded.update(kwargs)

    monkeypatch.setattr(hf_state.settings, "database_url", None)
    monkeypatch.setattr(hf_state.settings, "hf_state_repo_id", "owner/state")
    monkeypatch.setattr(hf_state.settings, "hf_token", "secret")
    monkeypatch.setattr(hf_state.settings, "data_dir", tmp_path)
    monkeypatch.setattr(hf_state, "HfApi", FakeApi)

    assert hf_state._snapshot_and_upload() is True
    assert uploaded["value"] == "saved"
    assert uploaded["repo_id"] == "owner/state"
    assert uploaded["repo_type"] == "dataset"


@pytest.mark.asyncio
async def test_restore_copies_remote_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    remote = tmp_path / "remote.db"
    remote.write_bytes(b"sqlite-state")
    data_dir = tmp_path / "data"
    monkeypatch.setattr(hf_state.settings, "database_url", None)
    monkeypatch.setattr(hf_state.settings, "hf_state_repo_id", "owner/state")
    monkeypatch.setattr(hf_state.settings, "hf_token", "secret")
    monkeypatch.setattr(hf_state.settings, "data_dir", data_dir)
    monkeypatch.setattr(hf_state, "hf_hub_download", lambda **kwargs: str(remote))

    assert await hf_state.restore_state() is True
    assert hf_state.settings.sqlite_path.read_bytes() == b"sqlite-state"

"""Persist the local SQLite database in a private Hugging Face dataset repo."""

import asyncio
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.errors import EntryNotFoundError, RepositoryNotFoundError

from app.config import settings

logger = logging.getLogger(__name__)


def enabled() -> bool:
    """Return whether free-Space snapshot persistence is configured."""
    return bool(settings.hf_state_repo_id and settings.hf_token and not settings.database_url)


def _restore() -> bool:
    if not enabled():
        return False
    try:
        cached = hf_hub_download(
            repo_id=settings.hf_state_repo_id,
            filename=settings.hf_state_filename,
            repo_type="dataset",
            token=settings.hf_token,
        )
    except EntryNotFoundError:
        logger.info("No remote database snapshot exists yet; starting empty")
        return False
    except RepositoryNotFoundError as exc:
        raise RuntimeError(
            "HF_STATE_REPO_ID is missing or HF_TOKEN cannot access it"
        ) from exc
    settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, settings.sqlite_path)
    logger.info("Restored database snapshot from %s", settings.hf_state_repo_id)
    return True


async def restore_state() -> bool:
    """Restore the latest snapshot before SQLAlchemy opens the database."""
    return await asyncio.to_thread(_restore)


def _snapshot_and_upload() -> bool:
    if not enabled() or not settings.sqlite_path.exists():
        return False
    with tempfile.TemporaryDirectory(prefix="resume-matcher-state-") as tmp:
        snapshot = Path(tmp) / settings.hf_state_filename
        source = sqlite3.connect(settings.sqlite_path)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        HfApi(token=settings.hf_token).upload_file(
            path_or_fileobj=str(snapshot),
            path_in_repo=settings.hf_state_filename,
            repo_id=settings.hf_state_repo_id,
            repo_type="dataset",
            commit_message="Save Resume Matcher state",
        )
    return True


async def sync_state() -> bool:
    """Upload a transactionally consistent SQLite snapshot."""
    return await asyncio.to_thread(_snapshot_and_upload)


async def periodic_state_sync() -> None:
    """Continuously checkpoint state while a free Space is awake."""
    interval = max(30, settings.hf_state_sync_seconds)
    while True:
        await asyncio.sleep(interval)
        try:
            await sync_state()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Could not upload the database snapshot")

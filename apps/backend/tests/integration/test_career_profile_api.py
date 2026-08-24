"""End-to-end API coverage for the editable internship evidence profile."""

from httpx import ASGITransport, AsyncClient

from app.main import app


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_import_edit_list_and_delete_master_resume_facts(
    isolated_db, sample_resume
):
    await isolated_db.create_resume(
        content="# Supported master resume",
        is_master=True,
        processed_data=sample_resume,
        processing_status="ready",
        user_id="local-user",
    )

    async with _client() as client:
        imported = await client.post("/api/v1/candidate-facts/import-master")
        assert imported.status_code == 200
        assert imported.json()["imported"] >= 5

        listed = await client.get("/api/v1/candidate-facts")
        assert listed.status_code == 200
        facts = listed.json()
        assert any(fact["category"] == "education" for fact in facts)
        assert all("jane@example.com" not in fact["value"] for fact in facts)

        preference = await client.post(
            "/api/v1/candidate-facts",
            json={
                "fact_key": "internship_voice",
                "label": "Internship voice",
                "value": "Concise, technical, and evidence-first",
                "category": "writing_preferences",
                "sensitive": False,
            },
        )
        assert preference.status_code == 200
        fact_id = preference.json()["fact_id"]

        deleted = await client.delete(f"/api/v1/candidate-facts/{fact_id}")
        assert deleted.status_code == 200
        remaining = (await client.get("/api/v1/candidate-facts")).json()
        assert all(fact["fact_id"] != fact_id for fact in remaining)


async def test_import_requires_a_processed_master_resume(isolated_db):
    async with _client() as client:
        response = await client.post("/api/v1/candidate-facts/import-master")
    assert response.status_code == 400
    assert "processed master resume" in response.json()["detail"]

import asyncio

from fastapi.testclient import TestClient
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.api import app
from backend.esm_data.database import async_session_creator
from backend.esm_data.db_models import Task

client: TestClient = TestClient(app)


async def _db_delete_existing_task(session: AsyncSession, task_id: str) -> None:
    existing = await session.get(Task, task_id)
    if not existing:
        return
    await session.delete(existing)
    await session.commit()


async def _db_create_task(task_id: str) -> None:
    async with async_session_creator() as session:
        await _db_delete_existing_task(session, task_id)
        task = Task(
            task_id=task_id,
            status="COMPLETED",
            report_json='{"extracted_answers": {}, "missing_information": []}',
        )
        session.add(task)
        await session.commit()


class TestFastAPIEndpoints:
    def test_get_templates(self) -> None:
        response = client.get("/api/templates")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_get_task_status_not_found(self) -> None:
        response = client.get("/api/tasks/nonexistent-id-abc")
        assert response.status_code == 404
        assert response.json()["detail"] == "The request job does not exist."

    def test_create_custom_template_invalid(self) -> None:
        response = client.post("/api/templates", json={"name": "INVALID"})
        assert response.status_code == 422

    def test_generate_document_invalid_payload(self) -> None:
        response = client.post("/api/generate", data={"target_doc": "DMP"})
        assert response.status_code == 422

    def test_run_audit_invalid_payload(self) -> None:
        response = client.post("/api/audit", json={})
        assert response.status_code == 422

    def test_patch_task_report_not_found(self) -> None:
        response = client.patch(
            "/api/tasks/nonexistent-id-abc/report",
            json={"extracted_answers": {}, "missing_information": []},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "The requested job does not exist."

    def test_patch_task_report_invalid_payload(self) -> None:
        response = client.patch(
            "/api/tasks/some-id/report", json={"extracted_answers": "invalid_type"}
        )
        assert response.status_code == 422

    def test_patch_task_report_success(self) -> None:
        task_id = "test-task-patch-id"

        async def create_test_task() -> None:
            async with async_session_creator() as session:
                # First delete if it exists from previous dirty runs
                existing = await session.get(Task, task_id)
                if existing:
                    await session.delete(existing)
                    await session.commit()
                task = Task(
                    task_id=task_id,
                    status="COMPLETED",
                    report_json=(
                        '{"extracted_answers": {"Q1": "A1"}, '
                        '"missing_information": []}'
                    ),
                )
                session.add(task)
                await session.commit()

        asyncio.run(create_test_task())

        # Now patch the task
        update_payload = {
            "extracted_answers": {"Q1": "Updated A1", "Q2": "New Answer"},
            "missing_information": ["Q3"],
        }
        response = client.patch(f"/api/tasks/{task_id}/report", json=update_payload)
        assert response.status_code == 200
        assert response.json()["status"] == "SUCCESS"

        # Fetch the status and verify report got updated
        status_response = client.get(f"/api/tasks/{task_id}")
        assert status_response.status_code == 200
        data = status_response.json()
        assert data["report"]["extracted_answers"] == {
            "Q1": "Updated A1",
            "Q2": "New Answer",
        }
        assert data["report"]["missing_information"] == ["Q3"]

        async def delete_test_task() -> None:
            async with async_session_creator() as session:
                task = await session.get(Task, task_id)
                if task:
                    await session.delete(task)
                    await session.commit()

        asyncio.run(delete_test_task())

    def test_delete_task_not_found(self) -> None:
        response = client.delete("/api/tasks/nonexistent-delete-id")
        assert response.status_code == 404
        assert response.json()["detail"] == "The request job does not exist."

    def test_delete_task_success(self) -> None:
        task_id = "test-task-delete-id"
        asyncio.run(_db_create_task(task_id))

        # Now delete the task
        response = client.delete(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["status"] == "DELETED"
        assert response.json()["task_id"] == task_id

        # Verify it is deleted from the DB
        status_response = client.get(f"/api/tasks/{task_id}")
        assert status_response.status_code == 404

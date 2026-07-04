from typing import Any
from fastapi.testclient import TestClient
from backend.api import app

client: TestClient = TestClient(app)

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

from fastapi.testclient import TestClient
from backend.api import app

# Initialize the test client
client = TestClient(app)

class TestFastAPIEndpoints:
    """
    Tests the main application gateways.
    """

    def test_healthcheck_endpoint(self) -> None:
        """Ensures the API spins up and returns 200 OK cleanly."""
        response = client.get("/")
        assert response.status_code == 200
        # Check that the API returns the expected JSON structure
        assert "status" in response.json()
        assert response.json()["status"] == "API is operational"

    def test_unsupported_http_methods_rejected(self) -> None:
        """Ensures the API strictly rejects methods not explicitly allowed."""
        # For example, sending a POST to the root health check
        response = client.post("/")
        assert response.status_code == 405 # Method Not Allowed
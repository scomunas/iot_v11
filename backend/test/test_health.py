import sys
from pathlib import Path

# Add backend directory to sys.path so 'app' can be imported
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, API_KEY
from app.database import get_db_path


def test_database_initialization_and_health():
    with TestClient(app) as client:
        # Check DB file exists
        db_path = get_db_path()
        assert db_path.exists(), f"Database file {db_path} should exist after startup"

        # Check health endpoint without key
        response = client.get("/health")
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API Key"
        print("Test passed: 401 Unauthorized when missing API Key")

        # Check health endpoint with invalid key
        response = client.get("/health", headers={"X-API-Key": "wrong-key"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or missing API Key"
        print("Test passed: 401 Unauthorized when invalid API Key")

        # Check unauthenticated ping probe for Docker healthchecks
        ping_resp = client.get("/ping")
        assert ping_resp.status_code == 200
        assert ping_resp.json() == {"status": "ok"}
        print("Test passed: 200 OK for unauthenticated /ping endpoint")

        # Check health endpoint with valid key
        response = client.get("/health", headers={"X-API-Key": API_KEY})
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert data["scheduler"] == "running"
        assert "homeassistant" in data
        assert "timestamp" in data
        assert "environment" in data
        # Check versioned /api/v1/ping and /api/v1/health endpoints
        v1_ping = client.get("/api/v1/ping")
        assert v1_ping.status_code == 200
        assert v1_ping.json() == {"status": "ok"}

        v1_health = client.get("/api/v1/health", headers={"X-API-Key": API_KEY})
        assert v1_health.status_code == 200
        assert v1_health.json()["status"] == "healthy"
        print("Test passed: 200 OK for /api/v1/ping and /api/v1/health")

        print("Test passed: 200 OK with valid API Key and DB status:", data)


if __name__ == "__main__":
    test_database_initialization_and_health()
    print("All health tests passed successfully!")

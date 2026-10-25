import logging
import sys
from pathlib import Path

# Add backend directory to sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app, API_KEY


def test_logs_endpoint_and_pagination():
    with TestClient(app) as client:
        headers = {"X-API-Key": API_KEY}

        # Generate some distinct log records for testing
        test_logger = logging.getLogger("test_logger")
        for i in range(35):
            test_logger.info(f"Test log message iteration #{i+1}")
        test_logger.warning("Warning: test battery level threshold")
        test_logger.error("Error: sensor disconnected test error")

        # 1. Test GET /logs with default pagination (page=1, page_size=25)
        resp1 = client.get("/logs?page=1&page_size=25", headers=headers)
        assert resp1.status_code == 200, f"Expected 200, got {resp1.status_code}"
        data1 = resp1.json()
        assert "logs" in data1
        assert "total" in data1
        assert "page" in data1
        assert "page_size" in data1
        assert "total_pages" in data1
        assert data1["page"] == 1
        assert data1["page_size"] == 25
        assert len(data1["logs"]) == 25
        assert data1["total"] >= 37
        print(f"PASS: Page 1 returned {len(data1['logs'])} records out of {data1['total']} total (total_pages={data1['total_pages']})")

        # 2. Test GET /logs for page 2 with page_size=10
        resp2 = client.get("/logs?page=2&page_size=10", headers=headers)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["page"] == 2
        assert data2["page_size"] == 10
        assert len(data2["logs"]) == 10
        print("PASS: Page 2 with page_size=10 succeeded")

        # 3. Test filtering by level (e.g. ERROR)
        resp_err = client.get("/logs?level=ERROR", headers=headers)
        assert resp_err.status_code == 200
        data_err = resp_err.json()
        assert all(entry["level"] == "ERROR" for entry in data_err["logs"])
        print(f"PASS: Filtered by ERROR level ({len(data_err['logs'])} entries)")

        # 4. Test filtering by search query
        resp_search = client.get("/logs?search=battery", headers=headers)
        assert resp_search.status_code == 200
        data_search = resp_search.json()
        assert len(data_search["logs"]) >= 1
        assert "battery" in data_search["logs"][0]["message"].lower()
        print(f"PASS: Search query 'battery' matched {len(data_search['logs'])} records")

        # 5. Test page_size selector options (10, 50, 100)
        for size in [10, 50, 100]:
            resp_size = client.get(f"/logs?page=1&page_size={size}", headers=headers)
            assert resp_size.status_code == 200
            assert resp_size.json()["page_size"] == size
            print(f"PASS: Page size {size} supported")

        print("All backend logs tests passed successfully!")


if __name__ == "__main__":
    test_logs_endpoint_and_pagination()

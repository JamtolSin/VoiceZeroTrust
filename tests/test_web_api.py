import time
from fastapi.testclient import TestClient
from backend.web_api import create_app

TOKEN = "test-only-connection-key-32-characters"
HEADERS = {"Authorization": "Bearer " + TOKEN}


def test_authentication_and_origin():
    with TestClient(create_app(TOKEN, origins=["https://example.com"])) as client:
        assert client.get("/health").status_code == 401
        response = client.get("/health", headers={**HEADERS, "Origin": "https://example.com"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://example.com"
        assert client.get("/jobs/missing", headers=HEADERS).status_code == 404


def test_real_job_contract_cleanup_and_consent():
    paths = []
    def runner(operation, path, fields):
        paths.append(path)
        assert path.read_bytes() == b"audio"
        assert fields["consent"] == "true"
        return {"operation": operation, "fake_score": 0.3}
    with TestClient(create_app(TOKEN, runner=runner)) as client:
        rejected = client.post("/jobs/detect", headers=HEADERS, files={"audio": ("test.wav", b"audio")})
        assert rejected.status_code == 400
        response = client.post("/jobs/detect", headers=HEADERS,
            files={"audio": ("test.wav", b"audio")}, data={"consent": "true"})
        assert response.status_code == 200
        for _ in range(100):
            result = client.get("/jobs/" + response.json()["id"], headers=HEADERS).json()
            if result["status"] != "running":
                break
            time.sleep(.01)
        assert result["status"] == "complete"
        assert result["result"]["fake_score"] == .3
        assert not paths[0].exists()


def test_failure_is_reported_and_worker_is_released():
    def runner(*args):
        raise ValueError("invalid audio")
    with TestClient(create_app(TOKEN, runner=runner)) as client:
        response = client.post("/jobs/generate", headers=HEADERS,
            files={"audio": ("test.wav", b"audio")}, data={"consent": "true"})
        for _ in range(100):
            result = client.get("/jobs/" + response.json()["id"], headers=HEADERS).json()
            if result["status"] != "running":
                break
            time.sleep(.01)
        assert result["status"] == "failed"
        assert result["error"] == "invalid audio"
        assert client.get("/health", headers=HEADERS).json()["busy"] is False

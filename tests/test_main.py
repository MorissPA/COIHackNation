from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_rejects_forbidden_extension():
    response = client.post("/api/v1/forms/analyze", files={"file": ("virus.exe", b"MZ", "application/octet-stream")})
    assert response.status_code == 415


def test_rejects_forbidden_filename_character():
    response = client.post("/api/v1/forms/analyze", files={"file": ("wniosek*.pdf", b"%PDF-1.7", "application/pdf")})
    assert response.status_code == 400


def test_rejects_mime_mismatch():
    response = client.post("/api/v1/forms/analyze", files={"file": ("wniosek.pdf", b"not-a-pdf", "application/pdf")})
    assert response.status_code == 415

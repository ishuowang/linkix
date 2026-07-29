from fastapi.testclient import TestClient

from linkix.app import create_app
from linkix.config import Settings
from linkix.providers.douyin import MediaCandidate, ResolvedPost


class FakeProvider:
    name = "douyin"

    def resolve(self, text: str) -> ResolvedPost:
        assert text
        return ResolvedPost(
            provider_id="7345678901234567890",
            title="海边日落延时摄影 · 等风也等你",
            author="等风也等你",
            source_url="https://www.douyin.com/video/7345678901234567890",
            candidates=(
                MediaCandidate(
                    "https://v95.douyinvod.com/video/signed.mp4?secret=hidden",
                    "1080p",
                    size_bytes=123456,
                ),
            ),
        )


def client() -> TestClient:
    settings = Settings(resolve_limit_per_minute=100)
    return TestClient(create_app(settings=settings, provider=FakeProvider()))


def test_health():
    response = client().get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}


def test_resolve_returns_opaque_media_handle():
    response = client().post(
        "/api/v1/resolve",
        json={"text": "https://v.douyin.com/example/"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "douyin"
    assert payload["media"]["title"].startswith("海边日落")
    variant = payload["media"]["variants"][0]
    assert variant["download_url"].startswith("/api/v1/media/")
    assert "douyinvod.com" not in response.text
    assert "secret=hidden" not in response.text


def test_validation_errors_use_problem_json():
    response = client().post("/api/v1/resolve", json={"text": ""})
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "INVALID_INPUT"


def test_cors_is_exact():
    response = client().options(
        "/api/v1/resolve",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"

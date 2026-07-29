from pathlib import Path

import pytest

from linkix.config import Settings
from linkix.errors import UpstreamUnavailable
from linkix.providers.douyin import MediaCandidate
from linkix.services.media import MediaDownloader
from linkix.services.store import MediaLease


class RedirectResponse:
    is_redirect = True
    is_permanent_redirect = False
    headers = {"Location": "http://127.0.0.1/latest/meta-data/"}

    def close(self) -> None:
        pass


class VideoResponse:
    is_redirect = False
    is_permanent_redirect = False
    encoding = "utf-8"

    def __init__(self):
        self.headers = {
            "Content-Type": "video/mp4",
            "Content-Length": "1036",
        }

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self) -> None:
        pass

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, _chunk_size: int):
        yield b"\x00\x00\x00\x18ftypisom" + (b"\x00" * 1024)


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.requested: list[str] = []

    def get(self, url: str, **_kwargs):
        self.requested.append(url)
        if len(self.requested) > 1:
            raise AssertionError("unsafe redirect was followed")
        return self.response

    def close(self) -> None:
        pass


def lease(url: str) -> MediaLease:
    return MediaLease(
        handle="opaque",
        provider="douyin",
        provider_id="7345678901234567890",
        title="海边日落",
        author="测试作者",
        candidates=(MediaCandidate(url, "原片"),),
        expires_at_epoch=9999999999,
    )


def test_download_accepts_a_small_mp4(monkeypatch):
    session = FakeSession(VideoResponse())
    downloader = MediaDownloader(Settings())
    monkeypatch.setattr(downloader, "_session", lambda: session)
    monkeypatch.setattr(
        "linkix.services.media.assert_public_resolution",
        lambda _host: None,
    )

    path, filename = downloader.download(lease("https://v95.douyinvod.com/video.mp4"))
    try:
        assert path.stat().st_size == 1036
        assert filename.endswith(".mp4")
    finally:
        Path(path).unlink(missing_ok=True)


def test_redirect_to_private_host_is_rejected_before_follow(monkeypatch):
    session = FakeSession(RedirectResponse())
    downloader = MediaDownloader(Settings())
    monkeypatch.setattr(downloader, "_session", lambda: session)
    monkeypatch.setattr(
        "linkix.services.media.assert_public_resolution",
        lambda _host: None,
    )

    with pytest.raises(UpstreamUnavailable):
        downloader.download(lease("https://v95.douyinvod.com/video.mp4"))

    assert session.requested == ["https://v95.douyinvod.com/video.mp4"]

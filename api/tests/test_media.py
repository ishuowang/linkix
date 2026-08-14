import pytest

from linkix.config import Settings
from linkix.errors import DownloadBusy, MediaTooLarge, UpstreamUnavailable
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
        source_url="https://www.douyin.com/video/7345678901234567890",
        candidates=(MediaCandidate(url, "原片"),),
        expires_at_epoch=9999999999,
    )


def test_download_accepts_a_small_mp4(monkeypatch):
    session = FakeSession(VideoResponse())
    downloader = MediaDownloader(Settings())
    monkeypatch.setattr(downloader, "_session", lambda _lease, _candidate: session)
    monkeypatch.setattr(
        "linkix.services.media.assert_public_resolution",
        lambda _host: None,
    )

    artifact = downloader.download(lease("https://v95.douyinvod.com/video.mp4"))
    try:
        assert artifact.path.stat().st_size == 1036
        assert artifact.filename.endswith(".mp4")
    finally:
        artifact.cleanup()


def test_redirect_to_private_host_is_rejected_before_follow(monkeypatch):
    session = FakeSession(RedirectResponse())
    downloader = MediaDownloader(Settings())
    monkeypatch.setattr(downloader, "_session", lambda _lease, _candidate: session)
    monkeypatch.setattr(
        "linkix.services.media.assert_public_resolution",
        lambda _host: None,
    )

    with pytest.raises(UpstreamUnavailable):
        downloader.download(lease("https://v95.douyinvod.com/video.mp4"))

    assert session.requested == ["https://v95.douyinvod.com/video.mp4"]


def test_candidate_cannot_self_authorize_an_unlisted_cdn(monkeypatch):
    session = FakeSession(VideoResponse())
    downloader = MediaDownloader(Settings())
    monkeypatch.setattr(downloader, "_session", lambda _lease, _candidate: session)
    monkeypatch.setattr(
        "linkix.services.media.assert_public_resolution",
        lambda _host: None,
    )

    with pytest.raises(UpstreamUnavailable):
        downloader.download(lease("https://public.example/video.mp4"))

    assert session.requested == []


def test_actual_size_overflow_falls_back_to_next_candidate(monkeypatch, tmp_path):
    first = MediaCandidate("https://v95.douyinvod.com/high.mp4", "1080p")
    second = MediaCandidate("https://v95.douyinvod.com/low.mp4", "480p")
    item = lease(first.url)
    item = MediaLease(
        handle=item.handle,
        provider=item.provider,
        provider_id=item.provider_id,
        title=item.title,
        author=item.author,
        source_url=item.source_url,
        candidates=(first, second),
        expires_at_epoch=item.expires_at_epoch,
    )
    output = tmp_path / "video.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 1024)
    calls = []

    def download_candidate(_lease, candidate):
        calls.append(candidate.label)
        if candidate is first:
            raise MediaTooLarge()
        return output

    downloader = MediaDownloader(Settings())
    monkeypatch.setattr(downloader, "_download_candidate", download_candidate)
    artifact = downloader.download(item)
    try:
        assert artifact.path == output
        assert calls == ["1080p", "480p"]
    finally:
        artifact.cleanup()


def test_download_slot_is_held_until_artifact_cleanup(monkeypatch, tmp_path):
    output = tmp_path / "video.mp4"
    output.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 1024)
    downloader = MediaDownloader(Settings(max_parallel_downloads=1))
    monkeypatch.setattr(
        downloader,
        "_download_locked",
        lambda _lease: (output, "video.mp4"),
    )

    artifact = downloader.download(lease("https://v95.douyinvod.com/video.mp4"))
    with pytest.raises(DownloadBusy):
        downloader.download(lease("https://v95.douyinvod.com/video.mp4"))

    artifact.cleanup()
    next_artifact = downloader.download(lease("https://v95.douyinvod.com/video.mp4"))
    next_artifact.cleanup()

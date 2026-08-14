import pytest

from linkix.config import Settings
from linkix.errors import InvalidInput, NoMedia, ParseFailed
from linkix.providers.ytdlp import PLATFORM_SPECS, YtDlpProvider, select_candidates


def spec(name: str):
    return next(item for item in PLATFORM_SPECS if item.name == name)


def xhs_info() -> dict:
    return {
        "extractor_key": "XiaoHongShu",
        "id": "6a37b57600000000160252d2",
        "title": "公开笔记 fixture",
        "webpage_url": "https://www.xiaohongshu.com/discovery/item/6a37b57600000000160252d2",
        "formats": [
            {
                "url": "https://sns-video-v4.xhscdn.com/stream/video.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "h264",
                "acodec": "aac",
                "height": 720,
                "tbr": 709,
                "filesize": 5_296_526,
                "http_headers": {
                    "Referer": "https://www.xiaohongshu.com/",
                    "Cookie": "must-not-be-stored",
                    "Authorization": "must-not-be-stored",
                },
            }
        ],
    }


def test_xiaohongshu_provider_normalizes_public_video():
    provider = YtDlpProvider(
        Settings(),
        spec("xiaohongshu"),
        extractor=lambda _url: xhs_info(),
        dns_guard=lambda _host: None,
    )
    post = provider.resolve(
        "https://www.xiaohongshu.com/discovery/item/6a37b57600000000160252d2?xsec_token=x"
    )
    assert post.provider == "xiaohongshu"
    assert post.author == "小红书用户"
    assert post.source_url == (
        "https://www.xiaohongshu.com/discovery/item/6a37b57600000000160252d2"
    )
    assert post.candidates[0].label == "720p MP4"
    assert dict(post.candidates[0].http_headers) == {"referer": "https://www.xiaohongshu.com/"}


def test_rejects_wrong_extractor_and_collections():
    wrong = xhs_info() | {"extractor_key": "Generic"}
    provider = YtDlpProvider(
        Settings(),
        spec("xiaohongshu"),
        extractor=lambda _url: wrong,
        dns_guard=lambda _host: None,
    )
    with pytest.raises(ParseFailed):
        provider.resolve("https://www.xiaohongshu.com/explore/6a37b57600000000160252d2")

    playlist = xhs_info() | {"_type": "playlist", "entries": [xhs_info()]}
    provider.extractor = lambda _url: playlist
    with pytest.raises(NoMedia):
        provider.resolve("https://www.xiaohongshu.com/explore/6a37b57600000000160252d2")


def test_rejects_profile_paths_before_extraction():
    called = []
    provider = YtDlpProvider(
        Settings(),
        spec("bilibili"),
        extractor=lambda url: called.append(url),
        dns_guard=lambda _host: None,
    )
    with pytest.raises(InvalidInput):
        provider.resolve("https://www.bilibili.com/space/123")
    assert called == []


def test_bilibili_keeps_h264_size_fallbacks_and_ignores_av1():
    mib = 1024 * 1024
    info = {
        "formats": [
            {
                "url": "https://upos-sz-mirrorcos.bilivideo.com/av1.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "av01.0.08M.08",
                "acodec": "none",
                "height": 1080,
                "filesize": 20 * mib,
            },
            {
                "url": "https://upos-sz-mirrorcos.bilivideo.com/1080.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "height": 1080,
                "filesize": 95 * mib,
            },
            {
                "url": "https://upos-sz-mirrorcos.bilivideo.com/480.mp4",
                "protocol": "https",
                "ext": "mp4",
                "vcodec": "avc1.64001f",
                "acodec": "none",
                "height": 480,
                "filesize": 25 * mib,
            },
            {
                "url": "https://upos-sz-mirrorcos.bilivideo.com/audio.m4a",
                "protocol": "https",
                "ext": "m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "filesize": 10 * mib,
            },
        ]
    }
    candidates = select_candidates(info, provider="bilibili", max_bytes=100 * mib)
    assert [item.label for item in candidates] == ["480p MP4 · 合并音轨"]
    assert candidates[0].audio_url.endswith("audio.m4a")


def test_candidate_cdn_must_match_provider_allowlist():
    info = xhs_info()
    info["formats"][0]["url"] = "https://public.example/video.mp4"
    with pytest.raises(NoMedia):
        select_candidates(info, provider="xiaohongshu", max_bytes=100 * 1024 * 1024)

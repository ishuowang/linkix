import pytest

from linkix.config import Settings
from linkix.errors import InvalidInput, NoMedia, ParseFailed
from linkix.providers.kuaishou import (
    KuaishouProvider,
    parse_init_state,
    select_kuaishou_candidates,
)


def photo_fixture() -> dict:
    return {
        "photoId": "5229805182084287773",
        "caption": "公开视频 fixture",
        "userName": "测试作者",
        "singlePicture": False,
        "photoStatus": 0,
        "mainMvUrls": [
            {"url": "https://hwmov.a.yximgs.com/upic/video.mp4"},
            {"url": "https://hwmov.a.yximgs.com/upic/video.mp4"},
            {"url": "https://tymov2.a.kwimgs.com/upic/video.mp4"},
            {"url": "https://public.example/not-allowed.mp4"},
        ],
    }


def test_parses_init_state_without_relying_on_dynamic_top_level_key():
    html = (
        '<script>window.INIT_STATE = {"opaque-changing-key":{"result":1,"photo":'
        '{"photoId":"5229805182084287773","caption":"公开视频 fixture",'
        '"userName":"测试作者","singlePicture":false,"photoStatus":0,'
        '"mainMvUrls":[{"url":"https://hwmov.a.yximgs.com/upic/video.mp4"}]}}};'
        "</script>"
    )
    assert parse_init_state(html)["photoId"] == "5229805182084287773"


def test_kuaishou_candidates_are_deduplicated_and_cdn_limited():
    candidates = select_kuaishou_candidates(photo_fixture())
    assert [item.url for item in candidates] == [
        "https://hwmov.a.yximgs.com/upic/video.mp4",
        "https://tymov2.a.kwimgs.com/upic/video.mp4",
    ]


@pytest.mark.parametrize(
    "updates",
    [
        {"singlePicture": True},
        {"photoStatus": 1},
        {"mainMvUrls": []},
    ],
)
def test_rejects_non_video_or_non_public_posts(updates):
    photo = photo_fixture() | updates
    with pytest.raises(NoMedia):
        select_kuaishou_candidates(photo)


def test_parse_rejects_failed_state():
    with pytest.raises(ParseFailed):
        parse_init_state(
            '<script>window.INIT_STATE={"key":{"result":2,"photo":{"photoId":"1"}}};</script>'
        )


def test_provider_resolves_direct_work_id(monkeypatch):
    provider = KuaishouProvider(
        Settings(),
        dns_guard=lambda _host: None,
    )
    monkeypatch.setattr(provider, "_read_photo", lambda _session, _photo_id: photo_fixture())
    post = provider.resolve("https://www.kuaishou.com/short-video/5229805182084287773")
    assert post.provider == "kuaishou"
    assert post.provider_id == "5229805182084287773"
    assert post.author == "测试作者"


def test_provider_rejects_profile_path_before_network(monkeypatch):
    provider = KuaishouProvider(Settings(), dns_guard=lambda _host: None)
    called = []
    monkeypatch.setattr(provider, "_session", lambda: called.append(True))
    with pytest.raises(InvalidInput):
        provider.resolve("https://www.kuaishou.com/profile/author")
    assert called == []


def test_short_link_query_cannot_inject_a_photo_id(monkeypatch):
    provider = KuaishouProvider(Settings(), dns_guard=lambda _host: None)
    requested = []

    class Response:
        is_redirect = False
        is_permanent_redirect = False
        url = "https://v.kuaishou.com/share-token?next=/short-video/injected123"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Session:
        def get(self, url, **_kwargs):
            requested.append(url)
            return Response()

    with pytest.raises(ParseFailed):
        provider._resolve_photo_id(
            Session(),
            "https://v.kuaishou.com/share-token?next=/short-video/injected123",
        )
    assert requested == ["https://v.kuaishou.com/share-token?next=/short-video/injected123"]


def test_photo_page_does_not_follow_an_untrusted_redirect():
    provider = KuaishouProvider(Settings(), dns_guard=lambda _host: None)
    requested = []

    class Response:
        is_redirect = True
        is_permanent_redirect = False
        headers = {"Location": "http://127.0.0.1/latest/meta-data/"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Session:
        def get(self, url, **kwargs):
            requested.append((url, kwargs.get("allow_redirects")))
            return Response()

    with pytest.raises(InvalidInput):
        provider._read_photo(Session(), "5229805182084287773")
    assert requested == [("https://m.gifshow.com/fw/photo/5229805182084287773", False)]

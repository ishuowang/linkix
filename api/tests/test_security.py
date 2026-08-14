import socket

import pytest

from linkix.errors import InvalidInput, UpstreamUnavailable
from linkix.security import (
    DOUYIN_INPUT_HOSTS,
    assert_public_resolution,
    media_host_allowed,
    validate_http_url,
)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:pass@v.douyin.com/a",
        "https://v.douyin.com:444/a",
        "https://v.douyin.com.evil.example/a",
    ],
)
def test_structural_url_guard_rejects_unsafe_urls(url):
    with pytest.raises(InvalidInput):
        validate_http_url(url, exact_hosts=DOUYIN_INPUT_HOSTS)


def test_public_dns_guard_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
        ],
    )
    with pytest.raises(UpstreamUnavailable):
        assert_public_resolution("v.douyin.com")


def test_media_hosts_cannot_self_authorize_outside_provider_cdn():
    assert media_host_allowed("xiaohongshu", "sns-video-v4.xhscdn.com")
    assert not media_host_allowed("xiaohongshu", "public.example")
    assert media_host_allowed("bilibili", "upos-hz-mirrorakam.akamaized.net")
    assert not media_host_allowed("bilibili", "evil.upos-hz-mirrorakam.akamaized.net")

import pytest

from linkix.errors import InvalidInput, UnsupportedPlatform
from linkix.providers.base import MediaCandidate, ResolvedPost, iter_share_urls
from linkix.providers.registry import ProviderRegistry


class FakeProvider:
    name = "bilibili"
    input_hosts = frozenset({"www.bilibili.com"})

    def resolve(self, text: str) -> ResolvedPost:
        return ResolvedPost(
            provider=self.name,
            provider_id="BV1fixture",
            title="fixture",
            author="fixture",
            source_url=text,
            candidates=(
                MediaCandidate(
                    "https://upos-sz-mirrorcos.bilivideo.com/video.mp4",
                    "720p MP4",
                ),
            ),
        )


def test_dispatches_recognized_platform_share_text():
    result = ProviderRegistry((FakeProvider(),)).resolve(
        "复制链接 https://www.bilibili.com/video/BV1fixture 观看"
    )
    assert result.provider == "bilibili"


def test_rejects_unknown_platform_and_missing_url():
    registry = ProviderRegistry((FakeProvider(),))
    with pytest.raises(UnsupportedPlatform):
        registry.resolve("https://example.com/video/1")
    with pytest.raises(InvalidInput):
        registry.resolve("只有普通文本")


def test_normalizes_bare_app_short_links():
    values = list(iter_share_urls("复制这条：xhslink.com/o/abc123 打开小红书"))
    assert values[0][0] == "https://xhslink.com/o/abc123"

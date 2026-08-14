from __future__ import annotations

from ..config import Settings
from ..errors import InvalidInput, UnsupportedPlatform
from ..security import normalize_host
from .base import Provider, ResolvedPost, iter_share_urls
from .douyin import DouyinProvider
from .kuaishou import KuaishouProvider
from .ytdlp import PLATFORM_SPECS, YtDlpProvider


class ProviderRegistry:
    name = "auto"

    def __init__(self, providers: tuple[Provider, ...]):
        self.providers = providers

    @classmethod
    def from_settings(cls, settings: Settings) -> ProviderRegistry:
        return cls(
            (
                DouyinProvider(settings),
                KuaishouProvider(settings),
                *(YtDlpProvider(settings, spec) for spec in PLATFORM_SPECS),
            )
        )

    def resolve(self, text: str) -> ResolvedPost:
        found_url = False
        for value, parsed in iter_share_urls(text):
            found_url = True
            host = normalize_host(parsed.hostname or "")
            for provider in self.providers:
                if host in provider.input_hosts:
                    return provider.resolve(value)
        if found_url:
            raise UnsupportedPlatform("支持抖音、快手、小红书、B 站和微博的公开单视频链接。")
        raise InvalidInput("没有找到分享链接，请粘贴公开单视频的分享文本或完整链接。")

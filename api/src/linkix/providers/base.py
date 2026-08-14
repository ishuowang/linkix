from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from ..errors import InvalidInput, UnsupportedPlatform
from ..security import validate_http_url

URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
BARE_SHARE_RE = re.compile(
    r"(?<![\w@])(?:xhslink\.com|v\.kuaishou\.com|b23\.tv|t\.cn)/[^\s<>]+",
    re.IGNORECASE,
)
TRAILING_PUNCTUATION = ".,，。!！?？)]}）】"


@dataclass(frozen=True, slots=True)
class MediaCandidate:
    url: str
    label: str
    mime_type: str = "video/mp4"
    size_bytes: int | None = None
    bitrate: int = 0
    audio_url: str | None = None
    audio_size_bytes: int | None = None
    http_headers: tuple[tuple[str, str], ...] = ()

    @property
    def total_size_bytes(self) -> int | None:
        values = [value for value in (self.size_bytes, self.audio_size_bytes) if value]
        return sum(values) if values else None


@dataclass(frozen=True, slots=True)
class ResolvedPost:
    provider_id: str
    title: str
    author: str
    source_url: str
    candidates: tuple[MediaCandidate, ...]
    provider: str = ""


class Provider(Protocol):
    name: str
    input_hosts: frozenset[str]

    def resolve(self, text: str) -> ResolvedPost: ...


def iter_share_urls(text: str, *, max_chars: int = 4096):
    if len(text or "") > max_chars:
        raise InvalidInput("分享文本过长。")
    matches = [(match.start(), match.group(0)) for match in URL_RE.finditer(text or "")]
    matches.extend(
        (match.start(), f"https://{match.group(0)}") for match in BARE_SHARE_RE.finditer(text or "")
    )
    seen: set[str] = set()
    for _position, raw in sorted(matches):
        value = raw.rstrip(TRAILING_PUNCTUATION)
        if value in seen:
            continue
        seen.add(value)
        try:
            yield value, validate_http_url(value)
        except InvalidInput:
            continue


def extract_share_url(
    text: str,
    *,
    exact_hosts: frozenset[str],
    platform_name: str,
) -> str:
    found_url = False
    for value, _parsed in iter_share_urls(text):
        found_url = True
        try:
            validate_http_url(value, exact_hosts=exact_hosts)
            return value
        except InvalidInput:
            continue
    if found_url:
        raise UnsupportedPlatform(f"这不是受支持的{platform_name}分享链接。")
    raise InvalidInput("没有找到分享链接，请粘贴公开单视频的分享文本或完整链接。")

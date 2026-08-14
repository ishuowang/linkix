from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import requests

from ..config import Settings
from ..errors import InvalidInput, NoMedia, ParseFailed
from ..security import (
    assert_public_resolution,
    media_host_allowed,
    normalize_host,
    validate_http_url,
)
from .base import MediaCandidate, ResolvedPost, extract_share_url

SAFE_UPSTREAM_HEADERS = frozenset({"accept", "accept-language", "origin", "referer", "user-agent"})
DIRECT_PROTOCOLS = frozenset({"http", "https"})


@dataclass(frozen=True, slots=True)
class PlatformSpec:
    name: str
    display_name: str
    input_hosts: frozenset[str]
    short_hosts: frozenset[str]
    extractor_keys: frozenset[str]


PLATFORM_SPECS = (
    PlatformSpec(
        name="xiaohongshu",
        display_name="小红书",
        input_hosts=frozenset(
            {
                "xiaohongshu.com",
                "www.xiaohongshu.com",
                "xhslink.com",
                "www.xhslink.com",
            }
        ),
        short_hosts=frozenset({"xiaohongshu.com", "xhslink.com", "www.xhslink.com"}),
        extractor_keys=frozenset({"XiaoHongShu"}),
    ),
    PlatformSpec(
        name="bilibili",
        display_name="B 站",
        input_hosts=frozenset(
            {
                "bilibili.com",
                "www.bilibili.com",
                "m.bilibili.com",
                "b23.tv",
            }
        ),
        short_hosts=frozenset({"m.bilibili.com", "b23.tv"}),
        extractor_keys=frozenset({"BiliBili"}),
    ),
    PlatformSpec(
        name="weibo",
        display_name="微博",
        input_hosts=frozenset(
            {
                "weibo.com",
                "www.weibo.com",
                "m.weibo.cn",
                "video.weibo.com",
                "t.cn",
            }
        ),
        short_hosts=frozenset({"t.cn"}),
        extractor_keys=frozenset({"Weibo", "WeiboVideo"}),
    ),
)


def _size(value: Mapping[str, Any]) -> int | None:
    raw = value.get("filesize") or value.get("filesize_approx")
    try:
        parsed = int(raw or 0)
    except (TypeError, ValueError):
        return None
    return parsed or None


def _number(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _is_direct_http(value: Mapping[str, Any]) -> bool:
    url = value.get("url")
    if not isinstance(url, str) or not url:
        return False
    protocol = str(value.get("protocol") or urlsplit(url).scheme).lower()
    return protocol in DIRECT_PROTOCOLS


def _has_video(value: Mapping[str, Any]) -> bool:
    return str(value.get("vcodec") or "none").lower() != "none"


def _has_audio(value: Mapping[str, Any]) -> bool:
    return str(value.get("acodec") or "none").lower() != "none"


def _web_video(value: Mapping[str, Any]) -> bool:
    codec = str(value.get("vcodec") or "").lower()
    ext = str(value.get("ext") or "").lower()
    return (
        _is_direct_http(value)
        and _has_video(value)
        and ext in {"mp4", "m4v"}
        and codec.startswith(("avc1", "h264", "h.264"))
    )


def _web_audio(value: Mapping[str, Any]) -> bool:
    codec = str(value.get("acodec") or "").lower()
    ext = str(value.get("ext") or "").lower()
    return (
        _is_direct_http(value)
        and _has_audio(value)
        and ext in {"m4a", "mp4"}
        and codec.startswith(("mp4a", "aac"))
    )


def _format_score(value: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        _number(value.get("height")),
        _number(value.get("tbr")),
        _number(value.get("filesize") or value.get("filesize_approx")),
    )


def _safe_headers(*values: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    selected: dict[str, str] = {}
    for value in values:
        headers = value.get("http_headers")
        if not isinstance(headers, Mapping):
            continue
        for name, raw in headers.items():
            normalized = str(name).strip().lower()
            if normalized not in SAFE_UPSTREAM_HEADERS:
                continue
            text = str(raw).strip()
            if text and len(text) <= 1024:
                selected[normalized] = text
    return tuple(sorted(selected.items()))


def _label(value: Mapping[str, Any], *, merged: bool = False) -> str:
    height = _number(value.get("height"))
    quality = f"{height}p" if height else str(value.get("format_note") or "原片")
    return f"{quality} MP4" + (" · 合并音轨" if merged else "")


def _candidate(
    video: Mapping[str, Any],
    info: Mapping[str, Any],
    *,
    provider: str,
    audio: Mapping[str, Any] | None = None,
) -> MediaCandidate:
    video_url = str(video["url"])
    video_host = validate_http_url(video_url).hostname or ""
    if not media_host_allowed(provider, video_host):
        raise InvalidInput("媒体域名不在平台 CDN 白名单中。")
    audio_url = None
    if audio is not None:
        audio_url = str(audio["url"])
        audio_host = validate_http_url(audio_url).hostname or ""
        if not media_host_allowed(provider, audio_host):
            raise InvalidInput("音轨域名不在平台 CDN 白名单中。")
    return MediaCandidate(
        url=video_url,
        audio_url=audio_url,
        label=_label(video, merged=audio is not None),
        size_bytes=_size(video),
        audio_size_bytes=_size(audio or {}),
        bitrate=_number(video.get("tbr")) * 1000,
        http_headers=_safe_headers(info, video, audio or {}),
    )


def _fits_limit(
    video: Mapping[str, Any],
    audio: Mapping[str, Any] | None,
    max_bytes: int,
) -> bool:
    video_size = _size(video)
    audio_size = _size(audio or {})
    declared = (video_size or 0) + (audio_size or 0)
    return not declared or declared <= max_bytes


def select_candidates(
    info: Mapping[str, Any],
    *,
    provider: str,
    max_bytes: int,
    limit: int = 6,
) -> tuple[MediaCandidate, ...]:
    formats = [item for item in (info.get("formats") or []) if isinstance(item, Mapping)]
    requested = info.get("requested_formats")
    if isinstance(requested, list):
        formats.extend(item for item in requested if isinstance(item, Mapping))
    if _web_video(info):
        formats.append(info)

    ranked: list[tuple[tuple[int, int, int], MediaCandidate]] = []
    for item in formats:
        if not (_web_video(item) and _web_audio(item)) or not _fits_limit(
            item,
            None,
            max_bytes,
        ):
            continue
        try:
            ranked.append((_format_score(item), _candidate(item, info, provider=provider)))
        except InvalidInput:
            continue

    videos = sorted(
        (item for item in formats if _web_video(item) and not _has_audio(item)),
        key=_format_score,
        reverse=True,
    )
    audios = sorted(
        (item for item in formats if _web_audio(item) and not _has_video(item)),
        key=_format_score,
        reverse=True,
    )
    for video in videos:
        for audio in audios:
            if not _fits_limit(video, audio, max_bytes):
                continue
            try:
                candidate = _candidate(
                    video,
                    info,
                    provider=provider,
                    audio=audio,
                )
            except InvalidInput:
                continue
            ranked.append((_format_score(video), candidate))
            break

    selected: list[MediaCandidate] = []
    seen: set[tuple[str, str | None]] = set()
    for _score, candidate in sorted(ranked, key=lambda item: item[0], reverse=True):
        key = (candidate.url, candidate.audio_url)
        if key in seen:
            continue
        seen.add(key)
        selected.append(candidate)
        if len(selected) >= limit:
            break
    if not selected:
        raise NoMedia("没有找到大小限制内、可在 Web/iOS 播放的 H.264 + AAC 视频。")
    return tuple(selected)


def _single_video(info: Mapping[str, Any]) -> Mapping[str, Any]:
    if info.get("_type") in {"playlist", "multi_video"} or isinstance(info.get("entries"), list):
        raise NoMedia("当前只支持公开单视频，不支持合集、分段或混合媒体帖子。")
    return info


def _canonical_source(spec: PlatformSpec, value: str) -> str:
    parsed = urlsplit(value)
    path = parsed.path.rstrip("/")
    if spec.name == "xiaohongshu":
        return f"https://www.xiaohongshu.com{path}"
    if spec.name == "bilibili":
        match = re.search(r"/video/((?:BV|av)[^/?#]+)", path, re.IGNORECASE)
        if match:
            query = parse_qs(parsed.query)
            page = query.get("p", [""])[0]
            suffix = f"?{urlencode({'p': page})}" if page.isdigit() else ""
            return f"https://www.bilibili.com/video/{match.group(1)}{suffix}"
    if spec.name == "weibo":
        query = parse_qs(parsed.query)
        clean_query = urlencode({"fid": query["fid"][0]}) if query.get("fid") else ""
        return urlunsplit(("https", normalize_host(parsed.hostname or ""), path, clean_query, ""))
    return value


class YtDlpProvider:
    def __init__(
        self,
        settings: Settings,
        spec: PlatformSpec,
        *,
        extractor: Callable[[str], Mapping[str, Any]] | None = None,
        dns_guard: Callable[[str], None] = assert_public_resolution,
    ):
        self.settings = settings
        self.spec = spec
        self.name = spec.name
        self.input_hosts = spec.input_hosts
        self.extractor = extractor or self._extract
        self.dns_guard = dns_guard

    def _validate_path(self, value: str, *, allow_short: bool) -> None:
        parsed = validate_http_url(value, exact_hosts=self.input_hosts)
        host = normalize_host(parsed.hostname or "")
        path = parsed.path
        if allow_short and host in self.spec.short_hosts:
            if path in {"", "/"}:
                raise InvalidInput(f"请输入完整的{self.spec.display_name}分享链接。")
            return
        valid = False
        if self.name == "xiaohongshu":
            valid = host == "www.xiaohongshu.com" and bool(
                re.fullmatch(r"/(?:explore|discovery/item)/[\da-f]+/?", path, re.IGNORECASE)
            )
        elif self.name == "bilibili":
            valid = host in {"bilibili.com", "www.bilibili.com"} and bool(
                re.match(r"/video/(?:BV[^/?#]+|av\d+)(?:/|$)", path, re.IGNORECASE)
            )
        elif self.name == "weibo":
            valid = (
                (host == "m.weibo.cn" and bool(re.match(r"/(?:status|detail)/[\w-]+", path)))
                or (
                    host in {"weibo.com", "www.weibo.com"}
                    and bool(re.match(r"/(?:\d+/[\w-]+|tv/show/[\w:-]+)", path))
                )
                or (
                    host == "video.weibo.com"
                    and path.rstrip("/") == "/show"
                    and bool(parse_qs(parsed.query).get("fid"))
                )
            )
        if not valid:
            raise InvalidInput(f"当前只支持{self.spec.display_name}的公开单视频作品页。")

    def _extract(self, url: str) -> Mapping[str, Any]:
        import yt_dlp

        proxy = (
            self.settings.bilibili_proxy if self.name == "bilibili" else self.settings.ytdlp_proxy
        )
        options = {
            "cachedir": False,
            "extract_flat": False,
            "fragment_retries": self.settings.connect_retries,
            "geo_bypass": False,
            "noplaylist": True,
            "no_warnings": True,
            "proxy": proxy or "",
            "quiet": True,
            "retries": self.settings.connect_retries,
            "skip_download": True,
            "socket_timeout": 30,
        }
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            raise ParseFailed(f"{self.spec.display_name}暂时无法解析这个公开视频。") from exc
        if not isinstance(info, Mapping):
            raise ParseFailed(f"{self.spec.display_name}没有返回可用作品数据。")
        return info

    def _expand_short_url(self, value: str) -> str:
        parsed = validate_http_url(value, exact_hosts=self.input_hosts)
        if normalize_host(parsed.hostname or "") not in self.spec.short_hosts:
            self._validate_path(value, allow_short=False)
            return value

        session = requests.Session()
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )
        proxy = (
            self.settings.bilibili_proxy if self.name == "bilibili" else self.settings.ytdlp_proxy
        )
        if proxy:
            session.proxies.update({"http": proxy, "https": proxy})
        current = value
        try:
            for _ in range(self.settings.max_redirects + 1):
                current_parsed = validate_http_url(current, exact_hosts=self.input_hosts)
                self.dns_guard(current_parsed.hostname or "")
                with session.get(
                    current,
                    allow_redirects=False,
                    stream=True,
                    timeout=(15, 30),
                ) as response:
                    if not (response.is_redirect or response.is_permanent_redirect):
                        response.raise_for_status()
                        self._validate_path(current, allow_short=False)
                        return current
                    location = response.headers.get("Location")
                    if not location:
                        break
                    current = urljoin(current, location)
                    validate_http_url(current, exact_hosts=self.input_hosts)
        except requests.RequestException as exc:
            raise ParseFailed(f"{self.spec.display_name}短链暂时无法打开。") from exc
        finally:
            session.close()
        raise ParseFailed(f"{self.spec.display_name}短链跳转次数过多或目标无效。")

    def resolve(self, text: str) -> ResolvedPost:
        share_url = extract_share_url(
            text,
            exact_hosts=self.input_hosts,
            platform_name=self.spec.display_name,
        )
        self._validate_path(share_url, allow_short=True)
        parsed = validate_http_url(share_url, exact_hosts=self.input_hosts)
        self.dns_guard(parsed.hostname or "")
        resolved_url = self._expand_short_url(share_url)
        try:
            info = _single_video(self.extractor(resolved_url))
        except (NoMedia, ParseFailed):
            raise
        except Exception as exc:
            raise ParseFailed(f"{self.spec.display_name}暂时无法解析这个公开视频。") from exc

        extractor_key = str(info.get("extractor_key") or "")
        if extractor_key not in self.spec.extractor_keys:
            raise ParseFailed(f"{self.spec.display_name}链接没有进入受信任的单视频解析器。")
        candidates = select_candidates(
            info,
            provider=self.name,
            max_bytes=self.settings.max_media_bytes,
        )
        provider_id = str(info.get("id") or "").strip()
        if not provider_id:
            raise ParseFailed(f"{self.spec.display_name}没有返回作品 ID。")
        title = str(info.get("title") or info.get("description") or f"{self.spec.display_name}作品")
        author = str(
            info.get("uploader")
            or info.get("channel")
            or info.get("creator")
            or f"{self.spec.display_name}用户"
        )
        source_url = str(info.get("webpage_url") or resolved_url)
        try:
            self._validate_path(source_url, allow_short=False)
        except InvalidInput:
            source_url = resolved_url
        return ResolvedPost(
            provider=self.name,
            provider_id=provider_id[:160],
            title=title.strip()[:160],
            author=author.strip()[:80],
            source_url=_canonical_source(self.spec, source_url),
            candidates=candidates,
        )

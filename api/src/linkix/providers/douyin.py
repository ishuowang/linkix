from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Settings
from ..errors import InvalidInput, NoMedia, ParseFailed, UnsupportedPlatform
from ..security import (
    DOUYIN_INPUT_HOSTS,
    DOUYIN_MEDIA_SUFFIXES,
    assert_public_resolution,
    validate_http_url,
)

URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
AWEME_RE = re.compile(r"/(?:video|note)/(\d+)")
TRAILING_PUNCTUATION = ".,，。!！?？)]}）】"


@dataclass(frozen=True, slots=True)
class MediaCandidate:
    url: str
    label: str
    mime_type: str = "video/mp4"
    size_bytes: int | None = None
    bitrate: int = 0


@dataclass(frozen=True, slots=True)
class ResolvedPost:
    provider_id: str
    title: str
    author: str
    source_url: str
    candidates: tuple[MediaCandidate, ...]


def extract_share_url(text: str) -> str:
    if len(text) > 4096:
        raise InvalidInput("分享文本过长。")
    for match in URL_RE.finditer(text or ""):
        value = match.group(0).rstrip(TRAILING_PUNCTUATION)
        try:
            validate_http_url(value, exact_hosts=DOUYIN_INPUT_HOSTS)
            return value
        except InvalidInput:
            continue
    if URL_RE.search(text or ""):
        raise UnsupportedPlatform("首版只支持公开抖音视频链接。")
    raise InvalidInput("没有找到分享链接，请粘贴抖音分享文本或完整链接。")


def find_aweme_detail(value: object, aweme_id: str) -> dict | None:
    if isinstance(value, dict):
        if str(value.get("aweme_id")) == str(aweme_id) and isinstance(value.get("video"), dict):
            return value
        for child in value.values():
            detail = find_aweme_detail(child, aweme_id)
            if detail:
                return detail
    elif isinstance(value, list):
        for child in value:
            detail = find_aweme_detail(child, aweme_id)
            if detail:
                return detail
    return None


def parse_router_data(html: str, aweme_id: str) -> dict:
    match = re.search(
        r"<script[^>]*>\s*window\._ROUTER_DATA\s*=\s*(.*?)\s*;?\s*</script>",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        match = re.search(
            r'<script[^>]*\bid=["\']_ROUTER_DATA["\'][^>]*>(.*?)</script>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
    if not match:
        raise ParseFailed("抖音分享页没有返回作品数据。")
    try:
        router_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ParseFailed("抖音分享页数据格式发生变化。") from exc
    detail = find_aweme_detail(router_data, aweme_id)
    if not detail:
        raise ParseFailed("抖音分享页里没有找到目标作品。")
    return detail


def normalize_video_url(url: str) -> str:
    if "aweme.snssdk.com/aweme/v1/playwm/" in url:
        return url.replace("/aweme/v1/playwm/", "/aweme/v1/play/")
    return url


def select_video_candidates(detail: dict, limit: int = 8) -> tuple[MediaCandidate, ...]:
    video = detail.get("video") or {}
    addresses: list[tuple[int, str, dict]] = []
    for item in video.get("bit_rate") or []:
        address = item.get("play_addr") or {}
        if address.get("url_list"):
            label = str(item.get("gear_name") or item.get("quality_type") or "原片")
            addresses.append((int(item.get("bit_rate") or 0), label, address))
    for key in ("play_addr_h264", "play_addr", "play_addr_265"):
        address = video.get(key) or {}
        if address.get("url_list"):
            addresses.append((0, "原片", address))

    selected: list[MediaCandidate] = []
    seen: set[str] = set()
    for bitrate, label, address in sorted(addresses, key=lambda item: item[0], reverse=True):
        declared_size = int(address.get("data_size") or 0) or None
        for value in address.get("url_list") or []:
            if not isinstance(value, str):
                continue
            url = normalize_video_url(value)
            try:
                validate_http_url(url, allowed_suffixes=DOUYIN_MEDIA_SUFFIXES)
            except InvalidInput:
                continue
            if url in seen:
                continue
            seen.add(url)
            selected.append(
                MediaCandidate(
                    url=url,
                    label=label,
                    size_bytes=declared_size,
                    bitrate=bitrate,
                )
            )
            if len(selected) >= limit:
                return tuple(selected)
    if not selected:
        raise NoMedia("这个作品可能是图集、私密内容或已经失效。")
    return tuple(selected)


class DouyinProvider:
    name = "douyin"

    def __init__(
        self,
        settings: Settings,
        *,
        session_factory: Callable[[], requests.Session] = requests.Session,
        dns_guard: Callable[[str], None] = assert_public_resolution,
    ):
        self.settings = settings
        self.session_factory = session_factory
        self.dns_guard = dns_guard

    def _session(self, *, direct: bool = True) -> requests.Session:
        session = self.session_factory()
        session.trust_env = not direct and self.settings.parser_trust_env
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
                ),
                "Referer": "https://m.douyin.com/",
            }
        )
        if direct and self.settings.douyin_proxy:
            session.proxies.update(
                {
                    "http": self.settings.douyin_proxy,
                    "https": self.settings.douyin_proxy,
                }
            )
        retry = Retry(
            total=self.settings.connect_retries,
            connect=self.settings.connect_retries,
            read=1,
            status=2,
            other=0,
            backoff_factor=self.settings.backoff_factor,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _guard_input_url(self, value: str) -> None:
        parsed = validate_http_url(value, exact_hosts=DOUYIN_INPUT_HOSTS)
        self.dns_guard(parsed.hostname or "")

    def _limited_text(self, session: requests.Session, url: str) -> str:
        self._guard_input_url(url)
        with session.get(
            url,
            allow_redirects=False,
            stream=True,
            timeout=(15, 45),
        ) as response:
            response.raise_for_status()
            return self._limited_response_text(response)

    def _limited_response_text(self, response: requests.Response) -> str:
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > self.settings.max_upstream_bytes:
                raise ParseFailed("上游页面超过安全大小限制。")
            chunks.append(chunk)
        encoding = response.encoding or "utf-8"
        return b"".join(chunks).decode(encoding, errors="replace")

    def _resolve_aweme_id(self, share_url: str) -> str:
        direct = AWEME_RE.search(share_url)
        if direct:
            return direct.group(1)

        session = self._session(direct=True)
        current = share_url
        try:
            for _ in range(self.settings.max_redirects + 1):
                self._guard_input_url(current)
                with session.get(
                    current,
                    allow_redirects=False,
                    stream=True,
                    timeout=(15, 30),
                ) as response:
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise ParseFailed("短链跳转缺少目标地址。")
                        current = urljoin(current, location)
                        validate_http_url(current, exact_hosts=DOUYIN_INPUT_HOSTS)
                        continue
                    response.raise_for_status()
                    match = AWEME_RE.search(current) or AWEME_RE.search(response.url)
                    if not match:
                        match = re.search(
                            r"(?:modal_id|aweme_id)=(\d+)",
                            current,
                        )
                    if not match:
                        match = AWEME_RE.search(self._limited_response_text(response))
                    if match:
                        return match.group(1)
                    break
        except requests.RequestException as exc:
            raise ParseFailed("抖音短链暂时无法打开。") from exc
        finally:
            session.close()
        raise ParseFailed("短链已打开，但没有识别到作品 ID。")

    def _mobile_detail(self, aweme_id: str) -> dict:
        session = self._session(direct=True)
        try:
            html = self._limited_text(
                session,
                f"https://m.douyin.com/share/video/{aweme_id}",
            )
            return parse_router_data(html, aweme_id)
        except requests.RequestException as exc:
            raise ParseFailed("抖音分享页暂时无法访问。") from exc
        finally:
            session.close()

    def _fallback_detail(self, aweme_id: str) -> dict:
        session = self._session(direct=False)
        try:
            with session.get(
                self.settings.parser_api,
                params={"aweme_id": aweme_id},
                timeout=(15, 45),
            ) as response:
                response.raise_for_status()
                if len(response.content) > self.settings.max_upstream_bytes:
                    raise ParseFailed("备用解析器响应超过安全大小限制。")
                payload = response.json()
            detail = (payload.get("data") or {}).get("aweme_detail") or {}
            if not isinstance(detail, dict) or not detail:
                raise ParseFailed("备用解析器没有返回作品数据。")
            return detail
        except (requests.RequestException, ValueError) as exc:
            raise ParseFailed("备用解析器暂时不可用。") from exc
        finally:
            session.close()

    def resolve(self, text: str) -> ResolvedPost:
        share_url = extract_share_url(text)
        aweme_id = self._resolve_aweme_id(share_url)
        try:
            detail = self._mobile_detail(aweme_id)
        except ParseFailed:
            if not self.settings.enable_parser_fallback:
                raise
            detail = self._fallback_detail(aweme_id)

        candidates = select_video_candidates(detail)
        author = str((detail.get("author") or {}).get("nickname") or "抖音用户").strip()
        title = str(detail.get("desc") or f"抖音作品 {aweme_id}").strip()
        return ResolvedPost(
            provider_id=aweme_id,
            title=title[:160],
            author=author[:80],
            source_url=f"https://www.douyin.com/video/{aweme_id}",
            candidates=candidates,
        )

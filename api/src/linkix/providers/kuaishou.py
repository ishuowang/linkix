from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Settings
from ..errors import InvalidInput, NoMedia, ParseFailed
from ..security import assert_public_resolution, validate_http_url
from .base import MediaCandidate, ResolvedPost, extract_share_url

KUAISHOU_INPUT_HOSTS = frozenset(
    {
        "kuaishou.com",
        "www.kuaishou.com",
        "v.kuaishou.com",
        "kuaishou.cn",
        "www.kuaishou.cn",
    }
)
KUAISHOU_REDIRECT_HOSTS = KUAISHOU_INPUT_HOSTS | frozenset(
    {
        "m.gifshow.com",
        "v.m.chenzhongtech.com",
    }
)
KUAISHOU_MEDIA_SUFFIXES = (
    "yximgs.com",
    "kwimgs.com",
)
PHOTO_ID_RE = re.compile(r"/(?:short-video|fw/(?:photo|long-video))/([A-Za-z0-9_-]{5,160})/?$")
INIT_STATE_RE = re.compile(
    r"window\.INIT_STATE\s*=\s*(\{.*?\})\s*;?\s*</script>",
    re.IGNORECASE | re.DOTALL,
)


def _find_photo(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        photo = value.get("photo")
        if isinstance(photo, dict) and value.get("result") in {1, "1"}:
            return photo
        for child in value.values():
            found = _find_photo(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_photo(child)
            if found:
                return found
    return None


def parse_init_state(html: str) -> dict[str, Any]:
    match = INIT_STATE_RE.search(html)
    if not match:
        raise ParseFailed("快手公开页面没有返回作品数据。")
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise ParseFailed("快手公开页面数据格式发生变化。") from exc
    photo = _find_photo(state)
    if not photo:
        raise ParseFailed("快手公开页面里没有找到目标作品。")
    return photo


def _photo_id_from_url(value: str) -> str | None:
    match = PHOTO_ID_RE.fullmatch(urlsplit(value).path)
    return match.group(1) if match else None


def select_kuaishou_candidates(photo: dict[str, Any]) -> tuple[MediaCandidate, ...]:
    if photo.get("singlePicture") is True or photo.get("photoStatus") not in {None, 0, "0"}:
        raise NoMedia("这个快手作品不是可下载的公开视频。")
    selected: list[MediaCandidate] = []
    seen: set[str] = set()
    for item in photo.get("mainMvUrls") or []:
        if not isinstance(item, dict):
            continue
        value = item.get("url")
        if not isinstance(value, str) or value in seen:
            continue
        try:
            validate_http_url(value, allowed_suffixes=KUAISHOU_MEDIA_SUFFIXES)
        except InvalidInput:
            continue
        seen.add(value)
        selected.append(
            MediaCandidate(
                url=value,
                label="原片 MP4",
                size_bytes=int(item.get("size") or item.get("fileSize") or 0) or None,
                bitrate=int(item.get("bitrate") or item.get("avgBitrate") or 0),
                http_headers=(("referer", "https://www.kuaishou.com/"),),
            )
        )
    if not selected:
        raise NoMedia("这个快手作品没有公开的单视频下载地址。")
    return tuple(selected[:8])


class KuaishouProvider:
    name = "kuaishou"
    input_hosts = KUAISHOU_INPUT_HOSTS

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

    def _session(self) -> requests.Session:
        session = self.session_factory()
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://www.kuaishou.com/",
            }
        )
        if self.settings.kuaishou_proxy:
            session.proxies.update(
                {
                    "http": self.settings.kuaishou_proxy,
                    "https": self.settings.kuaishou_proxy,
                }
            )
        retry = Retry(
            total=self.settings.connect_retries,
            connect=self.settings.connect_retries,
            read=1,
            status=2,
            backoff_factor=self.settings.backoff_factor,
            status_forcelist=(408, 425, 429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def _guard(self, value: str) -> None:
        parsed = validate_http_url(value, exact_hosts=KUAISHOU_REDIRECT_HOSTS)
        self.dns_guard(parsed.hostname or "")

    def _validate_input_path(self, value: str) -> None:
        parsed = validate_http_url(value, exact_hosts=self.input_hosts)
        host = parsed.hostname or ""
        path = parsed.path
        valid = (
            (host == "v.kuaishou.com" and path not in {"", "/"})
            or (
                host in {"kuaishou.com", "www.kuaishou.com"}
                and bool(re.match(r"/(?:f|short-video)/[^/?#]+", path))
            )
            or (
                host in {"kuaishou.cn", "www.kuaishou.cn"}
                and bool(re.match(r"/short-video/[^/?#]+", path))
            )
        )
        if not valid:
            raise InvalidInput("当前只支持快手公开单视频的分享短链或作品页。")

    def _resolve_photo_id(self, session: requests.Session, share_url: str) -> str:
        direct = _photo_id_from_url(share_url)
        if direct:
            return direct
        current = share_url
        try:
            for _ in range(self.settings.max_redirects + 1):
                self._guard(current)
                with session.get(
                    current,
                    allow_redirects=False,
                    stream=True,
                    timeout=(15, 30),
                ) as response:
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            break
                        current = urljoin(current, location)
                        continue
                    photo_id = _photo_id_from_url(current) or _photo_id_from_url(response.url)
                    if photo_id:
                        return photo_id
                    break
        except requests.RequestException as exc:
            raise ParseFailed("快手短链暂时无法打开。") from exc
        raise ParseFailed("快手短链已打开，但没有识别到作品 ID。")

    def _read_photo(self, session: requests.Session, photo_id: str) -> dict[str, Any]:
        current = f"https://m.gifshow.com/fw/photo/{photo_id}"
        try:
            for _ in range(self.settings.max_redirects + 1):
                self._guard(current)
                with session.get(
                    current,
                    allow_redirects=False,
                    stream=True,
                    timeout=(15, 45),
                ) as response:
                    if response.is_redirect or response.is_permanent_redirect:
                        location = response.headers.get("Location")
                        if not location:
                            raise ParseFailed("快手页面跳转缺少目标地址。")
                        current = urljoin(current, location)
                        validate_http_url(current, exact_hosts=KUAISHOU_REDIRECT_HOSTS)
                        continue
                    response.raise_for_status()
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in response.iter_content(64 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > self.settings.max_upstream_bytes:
                            raise ParseFailed("快手公开页面超过安全大小限制。")
                        chunks.append(chunk)
                    encoding = response.encoding or "utf-8"
                    html = b"".join(chunks).decode(encoding, errors="replace")
                    return parse_init_state(html)
        except requests.RequestException as exc:
            raise ParseFailed("快手公开页面暂时无法访问。") from exc
        raise ParseFailed("快手页面跳转次数过多。")

    def resolve(self, text: str) -> ResolvedPost:
        share_url = extract_share_url(
            text,
            exact_hosts=self.input_hosts,
            platform_name="快手",
        )
        self._validate_input_path(share_url)
        self._guard(share_url)
        session = self._session()
        try:
            photo_id = self._resolve_photo_id(session, share_url)
            photo = self._read_photo(session, photo_id)
        finally:
            session.close()
        resolved_id = str(photo.get("photoId") or photo_id)
        title = str(photo.get("caption") or f"快手作品 {resolved_id}").strip()
        author = str(
            photo.get("userName") or (photo.get("user") or {}).get("name") or "快手用户"
        ).strip()
        return ResolvedPost(
            provider=self.name,
            provider_id=resolved_id[:160],
            title=title[:160],
            author=author[:80],
            source_url=f"https://www.kuaishou.com/short-video/{photo_id}",
            candidates=select_kuaishou_candidates(photo),
        )

from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Settings
from ..errors import DownloadBusy, InvalidInput, MediaTooLarge, UpstreamUnavailable
from ..security import (
    DOUYIN_MEDIA_SUFFIXES,
    assert_public_resolution,
    validate_http_url,
)
from .store import MediaLease


def safe_filename(author: str, title: str, provider_id: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\r\n]+', "_", f"{author}_{title}_{provider_id}")
    value = value.strip(" ._")[:120] or provider_id
    return f"{value}.mp4"


class MediaDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._semaphore = threading.BoundedSemaphore(settings.max_parallel_downloads)

    def _session(self) -> requests.Session:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
                ),
                "Referer": "https://m.douyin.com/",
            }
        )
        if self.settings.douyin_proxy:
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
        adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=2)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session

    def download(self, lease: MediaLease) -> tuple[Path, str]:
        if not self._semaphore.acquire(blocking=False):
            raise DownloadBusy("下载任务较多，请稍后重试。", retry_after=10)
        try:
            return self._download_locked(lease)
        finally:
            self._semaphore.release()

    def _open_safe_response(
        self,
        session: requests.Session,
        initial_url: str,
    ) -> requests.Response | None:
        current = initial_url
        for _ in range(self.settings.max_redirects + 1):
            try:
                parsed = validate_http_url(
                    current,
                    allowed_suffixes=DOUYIN_MEDIA_SUFFIXES,
                )
                assert_public_resolution(parsed.hostname or "")
            except (InvalidInput, UpstreamUnavailable):
                return None

            response = session.get(
                current,
                allow_redirects=False,
                stream=True,
                timeout=(20, 180),
            )
            if not (response.is_redirect or response.is_permanent_redirect):
                return response

            location = response.headers.get("Location")
            response.close()
            if not location:
                return None
            current = urljoin(current, location)
        return None

    def _download_locked(self, lease: MediaLease) -> tuple[Path, str]:
        session = self._session()
        try:
            for candidate in lease.candidates:
                path: Path | None = None
                try:
                    if (
                        candidate.size_bytes
                        and candidate.size_bytes > self.settings.max_media_bytes
                    ):
                        continue

                    response = self._open_safe_response(session, candidate.url)
                    if response is None:
                        continue
                    with response:
                        response.raise_for_status()
                        content_type = response.headers.get("Content-Type", "").lower()
                        if "text/html" in content_type or "application/json" in content_type:
                            continue
                        declared = int(response.headers.get("Content-Length") or 0)
                        if declared and declared > self.settings.max_media_bytes:
                            continue

                        descriptor, raw_path = tempfile.mkstemp(
                            prefix="linkix_",
                            suffix=".mp4",
                        )
                        os.close(descriptor)
                        path = Path(raw_path)
                        total = 0
                        with path.open("wb") as output:
                            for chunk in response.iter_content(256 * 1024):
                                if not chunk:
                                    continue
                                total += len(chunk)
                                if total > self.settings.max_media_bytes:
                                    raise MediaTooLarge("视频超过当前下载上限，请选择更小的版本。")
                                output.write(chunk)

                    if not path.exists() or path.stat().st_size < 1024:
                        path.unlink(missing_ok=True)
                        continue
                    with path.open("rb") as media:
                        header = media.read(12)
                    if len(header) < 8 or header[4:8] != b"ftyp":
                        path.unlink(missing_ok=True)
                        continue
                    return path, safe_filename(
                        lease.author,
                        lease.title,
                        lease.provider_id,
                    )
                except MediaTooLarge:
                    if path:
                        path.unlink(missing_ok=True)
                    raise
                except (requests.RequestException, OSError, ValueError):
                    if path:
                        path.unlink(missing_ok=True)
                    continue
        finally:
            session.close()
        raise UpstreamUnavailable("媒体线路暂时不可用，请重新解析后再试。")

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import Settings
from ..errors import DownloadBusy, InvalidInput, MediaTooLarge, UpstreamUnavailable
from ..providers.base import MediaCandidate
from ..security import (
    PROVIDER_REFERERS,
    assert_public_resolution,
    media_host_allowed,
    validate_http_url,
)
from .store import MediaLease


@dataclass(slots=True)
class MediaArtifact:
    path: Path
    filename: str
    _release: Callable[[], None] = field(repr=False)
    _cleanup_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _cleaned: bool = field(default=False, init=False, repr=False)

    def cleanup(self) -> None:
        with self._cleanup_lock:
            if self._cleaned:
                return
            self._cleaned = True
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        finally:
            self._release()


def safe_filename(author: str, title: str, provider_id: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\r\n]+', "_", f"{author}_{title}_{provider_id}")
    value = value.strip(" ._")[:120] or provider_id
    return f"{value}.mp4"


class MediaDownloader:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._semaphore = threading.BoundedSemaphore(settings.max_parallel_downloads)

    def _session(self, lease: MediaLease, candidate: MediaCandidate) -> requests.Session:
        session = requests.Session()
        session.trust_env = False
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                    "AppleWebKit/537.36 Chrome/130 Mobile Safari/537.36"
                ),
                "Referer": PROVIDER_REFERERS.get(lease.provider, lease.source_url),
            }
        )
        session.headers.update(dict(candidate.http_headers))
        proxies = {
            "douyin": self.settings.douyin_proxy,
            "kuaishou": self.settings.kuaishou_proxy,
            "bilibili": self.settings.bilibili_proxy,
        }
        proxy = proxies.get(lease.provider, self.settings.ytdlp_proxy)
        if proxy:
            session.proxies.update({"http": proxy, "https": proxy})
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

    def download(self, lease: MediaLease) -> MediaArtifact:
        if not self._semaphore.acquire(blocking=False):
            raise DownloadBusy("下载任务较多，请稍后重试。", retry_after=10)
        try:
            path, filename = self._download_locked(lease)
            return MediaArtifact(path, filename, self._semaphore.release)
        except BaseException:
            self._semaphore.release()
            raise

    def _open_safe_response(
        self,
        session: requests.Session,
        initial_url: str,
        *,
        lease: MediaLease,
    ) -> requests.Response | None:
        current = initial_url
        for _ in range(self.settings.max_redirects + 1):
            try:
                parsed = validate_http_url(current)
                host = parsed.hostname or ""
                if not media_host_allowed(lease.provider, host):
                    return None
                assert_public_resolution(host)
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

    def _fetch_to_temp(
        self,
        session: requests.Session,
        url: str,
        *,
        lease: MediaLease,
        suffix: str,
        byte_budget: int,
    ) -> tuple[Path, int]:
        response = self._open_safe_response(
            session,
            url,
            lease=lease,
        )
        if response is None:
            raise UpstreamUnavailable("媒体地址没有通过下载安全检查。")

        path: Path | None = None
        try:
            with response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type or "application/json" in content_type:
                    raise UpstreamUnavailable("上游没有返回媒体文件。")
                declared = int(response.headers.get("Content-Length") or 0)
                if declared and declared > byte_budget:
                    raise MediaTooLarge("视频超过当前下载上限，请选择更小的版本。")

                descriptor, raw_path = tempfile.mkstemp(prefix="linkix_", suffix=suffix)
                os.close(descriptor)
                path = Path(raw_path)
                total = 0
                with path.open("wb") as output:
                    for chunk in response.iter_content(256 * 1024):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > byte_budget:
                            raise MediaTooLarge("视频超过当前下载上限，请选择更小的版本。")
                        output.write(chunk)
            if not path.exists() or path.stat().st_size < 1024:
                raise UpstreamUnavailable("上游返回的媒体文件不完整。")
            return path, total
        except Exception:
            if path:
                path.unlink(missing_ok=True)
            raise

    @staticmethod
    def _assert_mp4(path: Path) -> None:
        with path.open("rb") as media:
            header = media.read(12)
        if len(header) < 8 or header[4:8] != b"ftyp":
            raise UpstreamUnavailable("上游返回的文件不是可播放的 MP4。")

    def _assert_muxed_av(self, path: Path) -> None:
        ffprobe = shutil.which(self.settings.ffprobe_path)
        if not ffprobe:
            raise UpstreamUnavailable("服务器没有安装 ffprobe，无法校验合并结果。")
        try:
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "stream=codec_type,codec_name",
                    "-of",
                    "json",
                    str(path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            streams = json.loads(result.stdout).get("streams") or []
        except (json.JSONDecodeError, subprocess.SubprocessError) as exc:
            raise UpstreamUnavailable("ffprobe 无法校验合并后的媒体文件。") from exc
        video_codecs = {
            item.get("codec_name") for item in streams if item.get("codec_type") == "video"
        }
        audio_codecs = {
            item.get("codec_name") for item in streams if item.get("codec_type") == "audio"
        }
        if not video_codecs.intersection({"h264"}) or not audio_codecs.intersection({"aac"}):
            raise UpstreamUnavailable("合并后的文件不是 H.264 + AAC 可播放视频。")

    def _merge_tracks(self, video: Path, audio: Path) -> Path:
        ffmpeg = shutil.which(self.settings.ffmpeg_path)
        if not ffmpeg:
            raise UpstreamUnavailable("这个视频需要合并音轨，但服务器没有安装 ffmpeg。")
        descriptor, raw_path = tempfile.mkstemp(prefix="linkix_", suffix=".mp4")
        os.close(descriptor)
        output = Path(raw_path)
        try:
            subprocess.run(
                [
                    ffmpeg,
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(video),
                    "-i",
                    str(audio),
                    "-map",
                    "0:v:0",
                    "-map",
                    "1:a:0",
                    "-c",
                    "copy",
                    "-movflags",
                    "+faststart",
                    str(output),
                ],
                check=True,
                capture_output=True,
                timeout=180,
            )
            if output.stat().st_size > self.settings.max_media_bytes:
                raise MediaTooLarge("视频超过当前下载上限，请选择更小的版本。")
            self._assert_mp4(output)
            self._assert_muxed_av(output)
            return output
        except Exception:
            output.unlink(missing_ok=True)
            raise

    def _download_candidate(
        self,
        lease: MediaLease,
        candidate: MediaCandidate,
    ) -> Path:
        session = self._session(lease, candidate)
        video_path: Path | None = None
        audio_path: Path | None = None
        try:
            video_path, video_size = self._fetch_to_temp(
                session,
                candidate.url,
                lease=lease,
                suffix=".mp4",
                byte_budget=self.settings.max_media_bytes,
            )
            if not candidate.audio_url:
                self._assert_mp4(video_path)
                result = video_path
                video_path = None
                return result

            remaining = self.settings.max_media_bytes - video_size
            if remaining <= 0:
                raise MediaTooLarge("视频超过当前下载上限，请选择更小的版本。")
            audio_path, _audio_size = self._fetch_to_temp(
                session,
                candidate.audio_url,
                lease=lease,
                suffix=".m4a",
                byte_budget=remaining,
            )
            return self._merge_tracks(video_path, audio_path)
        finally:
            session.close()
            if video_path:
                video_path.unlink(missing_ok=True)
            if audio_path:
                audio_path.unlink(missing_ok=True)

    def _download_locked(self, lease: MediaLease) -> tuple[Path, str]:
        saw_too_large = False
        for candidate in lease.candidates:
            declared = (candidate.size_bytes or 0) + (candidate.audio_size_bytes or 0)
            if declared and declared > self.settings.max_media_bytes:
                saw_too_large = True
                continue
            try:
                path = self._download_candidate(lease, candidate)
                return path, safe_filename(lease.author, lease.title, lease.provider_id)
            except MediaTooLarge:
                saw_too_large = True
                continue
            except (
                OSError,
                requests.RequestException,
                subprocess.SubprocessError,
                UpstreamUnavailable,
                ValueError,
            ):
                continue
        if saw_too_large:
            raise MediaTooLarge("所有可用清晰度都超过当前下载上限。")
        raise UpstreamUnavailable("媒体线路暂时不可用，请重新解析后再试。")

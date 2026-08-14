from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from ..errors import MediaExpired
from ..providers.base import MediaCandidate, ResolvedPost


@dataclass(frozen=True, slots=True)
class MediaLease:
    handle: str
    provider: str
    provider_id: str
    title: str
    author: str
    source_url: str
    candidates: tuple[MediaCandidate, ...]
    expires_at_epoch: float

    @property
    def expires_at(self) -> str:
        return datetime.fromtimestamp(self.expires_at_epoch, tz=UTC).isoformat()


class MediaStore:
    def __init__(self, ttl_seconds: int = 900):
        self.ttl_seconds = ttl_seconds
        self._items: dict[str, MediaLease] = {}
        self._lock = threading.Lock()

    def create(self, provider: str, post: ResolvedPost) -> MediaLease:
        now = time.time()
        lease = MediaLease(
            handle=secrets.token_urlsafe(24),
            provider=provider,
            provider_id=post.provider_id,
            title=post.title,
            author=post.author,
            source_url=post.source_url,
            candidates=post.candidates,
            expires_at_epoch=now + self.ttl_seconds,
        )
        with self._lock:
            self._purge_locked(now)
            self._items[lease.handle] = lease
        return lease

    def get(self, handle: str) -> MediaLease:
        now = time.time()
        with self._lock:
            self._purge_locked(now)
            lease = self._items.get(handle)
        if not lease:
            raise MediaExpired("请重新解析链接后再下载。")
        return lease

    def _purge_locked(self, now: float) -> None:
        expired = [handle for handle, lease in self._items.items() if lease.expires_at_epoch <= now]
        for handle in expired:
            self._items.pop(handle, None)

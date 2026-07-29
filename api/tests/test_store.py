import time

import pytest

from linkix.errors import MediaExpired
from linkix.providers.douyin import MediaCandidate, ResolvedPost
from linkix.services.store import MediaStore


def post_fixture() -> ResolvedPost:
    return ResolvedPost(
        provider_id="123",
        title="测试视频",
        author="测试作者",
        source_url="https://www.douyin.com/video/123",
        candidates=(MediaCandidate("https://v95.douyinvod.com/a.mp4", "原片"),),
    )


def test_store_uses_opaque_expiring_handles(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(time, "time", lambda: now[0])
    store = MediaStore(ttl_seconds=60)
    lease = store.create("douyin", post_fixture())
    assert "douyinvod" not in lease.handle
    assert store.get(lease.handle).provider_id == "123"

    now[0] = 1061.0
    with pytest.raises(MediaExpired):
        store.get(lease.handle)

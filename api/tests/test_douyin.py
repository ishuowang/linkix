import json

import pytest

from linkix.errors import InvalidInput, UnsupportedPlatform
from linkix.providers.douyin import (
    extract_share_url,
    normalize_video_url,
    parse_router_data,
    select_video_candidates,
)

AWEME_ID = "7345678901234567890"


def detail_fixture() -> dict:
    return {
        "aweme_id": AWEME_ID,
        "desc": "海边日落延时摄影",
        "author": {"nickname": "等风也等你"},
        "video": {
            "bit_rate": [
                {
                    "bit_rate": 2200000,
                    "gear_name": "1080p",
                    "play_addr": {
                        "data_size": 123456,
                        "url_list": [
                            "https://v95.douyinvod.com/video/main.mp4",
                            "https://v96.douyinvod.com/video/backup.mp4",
                        ],
                    },
                }
            ],
            "play_addr": {"url_list": ["https://v95.douyinvod.com/video/main.mp4"]},
        },
    }


def test_extracts_url_from_chinese_share_text():
    value = extract_share_url("2.33 复制打开抖音，看看作品 https://v.douyin.com/abc123/ ！")
    assert value == "https://v.douyin.com/abc123/"


def test_rejects_other_platforms():
    with pytest.raises(UnsupportedPlatform):
        extract_share_url("https://www.bilibili.com/video/BV1xx")


def test_rejects_text_without_url():
    with pytest.raises(InvalidInput):
        extract_share_url("只有一段普通文本")


def test_parses_both_router_data_shapes():
    detail = detail_fixture()
    payload = {"loaderData": {"video": detail}}
    assigned = (
        "<script>window._ROUTER_DATA = " + json.dumps(payload, ensure_ascii=False) + ";</script>"
    )
    embedded = (
        '<script id="_ROUTER_DATA" type="application/json">'
        + json.dumps(payload, ensure_ascii=False)
        + "</script>"
    )
    assert parse_router_data(assigned, AWEME_ID)["desc"] == detail["desc"]
    assert parse_router_data(embedded, AWEME_ID)["desc"] == detail["desc"]


def test_candidates_are_sorted_deduplicated_and_whitelisted():
    candidates = select_video_candidates(detail_fixture())
    assert [candidate.url for candidate in candidates] == [
        "https://v95.douyinvod.com/video/main.mp4",
        "https://v96.douyinvod.com/video/backup.mp4",
    ]
    assert candidates[0].label == "1080p"
    assert candidates[0].size_bytes == 123456


def test_playwm_is_normalized():
    value = "https://aweme.snssdk.com/aweme/v1/playwm/?video_id=1"
    assert "/aweme/v1/play/" in normalize_video_url(value)

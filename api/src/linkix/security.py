from __future__ import annotations

import ipaddress
import socket
from collections.abc import Iterable
from urllib.parse import SplitResult, urlsplit

from .errors import InvalidInput, UpstreamUnavailable

DOUYIN_INPUT_HOSTS = frozenset(
    {
        "v.douyin.com",
        "v.iesdouyin.com",
        "m.douyin.com",
        "www.douyin.com",
        "www.iesdouyin.com",
    }
)

DOUYIN_MEDIA_SUFFIXES = (
    "douyinvod.com",
    "douyin.com",
    "douyinpic.com",
    "bytecdn.cn",
    "byteimg.com",
    "bytedance.com",
    "snssdk.com",
    "pstatp.com",
)


def normalize_host(host: str) -> str:
    try:
        return host.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidInput("域名格式不正确。") from exc


def _matches_suffix(host: str, suffixes: Iterable[str]) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def validate_http_url(
    value: str,
    *,
    exact_hosts: Iterable[str] = (),
    allowed_suffixes: Iterable[str] = (),
) -> SplitResult:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise InvalidInput("链接格式不正确。") from exc

    if parsed.scheme not in {"http", "https"}:
        raise InvalidInput("只接受 HTTP 或 HTTPS 链接。")
    if not parsed.hostname:
        raise InvalidInput("链接缺少有效域名。")
    if parsed.username or parsed.password:
        raise InvalidInput("链接不能包含用户名或密码。")
    if port not in {None, 80, 443}:
        raise InvalidInput("链接不能使用自定义端口。")

    host = normalize_host(parsed.hostname)
    exact = {normalize_host(item) for item in exact_hosts}
    if exact and host not in exact:
        raise UnsupportedHost
    if allowed_suffixes and not _matches_suffix(host, allowed_suffixes):
        raise UnsupportedHost
    return parsed


class UnsupportedHost(InvalidInput):
    def __init__(self):
        super().__init__("这个域名不在允许的解析范围内。")


def assert_public_resolution(host: str) -> None:
    normalized = normalize_host(host)
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(
                normalized,
                None,
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as exc:
        raise UpstreamUnavailable("目标域名暂时无法解析，请稍后重试。") from exc

    if not addresses:
        raise UpstreamUnavailable("目标域名没有返回可用地址。")

    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise UpstreamUnavailable("出站请求被安全策略拒绝。")

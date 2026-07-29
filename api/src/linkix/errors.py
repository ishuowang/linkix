from __future__ import annotations


class LinkixError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    title = "服务暂时不可用"

    def __init__(self, detail: str | None = None, *, retry_after: int | None = None):
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.retry_after = retry_after


class InvalidInput(LinkixError):
    status_code = 400
    code = "INVALID_INPUT"
    title = "链接格式不正确"


class UnsupportedPlatform(LinkixError):
    status_code = 422
    code = "UNSUPPORTED_PLATFORM"
    title = "暂不支持这个平台"


class NoMedia(LinkixError):
    status_code = 422
    code = "NO_MEDIA"
    title = "没有找到可用视频"


class ParseFailed(LinkixError):
    status_code = 502
    code = "PARSE_FAILED"
    title = "解析失败"


class UpstreamUnavailable(LinkixError):
    status_code = 502
    code = "UPSTREAM_UNAVAILABLE"
    title = "上游暂时不可用"


class MediaExpired(LinkixError):
    status_code = 410
    code = "MEDIA_EXPIRED"
    title = "取链地址已经过期"


class MediaTooLarge(LinkixError):
    status_code = 413
    code = "MEDIA_TOO_LARGE"
    title = "视频超过当前下载上限"


class RateLimited(LinkixError):
    status_code = 429
    code = "RATE_LIMITED"
    title = "请求有点频繁"


class DownloadBusy(LinkixError):
    status_code = 503
    code = "DOWNLOAD_BUSY"
    title = "下载通道正忙"

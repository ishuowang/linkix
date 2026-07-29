from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from .config import Settings
from .errors import LinkixError, RateLimited
from .models import (
    AuthorOut,
    HealthResponse,
    MediaVariantOut,
    ResolvedMediaOut,
    ResolveRequest,
    ResolveResponse,
)
from .providers.douyin import DouyinProvider
from .services.media import MediaDownloader
from .services.rate_limit import SlidingWindowLimiter
from .services.store import MediaStore


def problem_response(error: LinkixError, request_id: str) -> JSONResponse:
    headers = {"X-Request-ID": request_id}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse(
        status_code=error.status_code,
        media_type="application/problem+json",
        headers=headers,
        content={
            "type": f"https://github.com/ishuowang/linkix/problems/{error.code.lower()}",
            "title": error.title,
            "status": error.status_code,
            "code": error.code,
            "detail": error.detail,
            "request_id": request_id,
        },
    )


def create_app(
    *,
    settings: Settings | None = None,
    provider: DouyinProvider | None = None,
    store: MediaStore | None = None,
    downloader: MediaDownloader | None = None,
) -> FastAPI:
    config = settings or Settings.from_env()
    resolver = provider or DouyinProvider(config)
    media_store = store or MediaStore(config.media_handle_ttl_seconds)
    media_downloader = downloader or MediaDownloader(config)
    limiter = SlidingWindowLimiter(config.resolve_limit_per_minute)

    api = FastAPI(
        title="Linkix API",
        version=config.app_version,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    api.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )

    @api.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = request_id
        if request.method == "POST" and request.url.path == "/api/v1/resolve":
            client = request.client.host if request.client else "unknown"
            if not limiter.allow(client):
                return problem_response(
                    RateLimited("每分钟最多解析十次，请稍后再试。", retry_after=60),
                    request_id,
                )
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @api.exception_handler(LinkixError)
    async def handle_linkix_error(request: Request, error: LinkixError):
        return problem_response(error, request.state.request_id)

    @api.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, _error: RequestValidationError):
        from .errors import InvalidInput

        return problem_response(
            InvalidInput("请输入 1–4096 个字符的分享文本或链接。"),
            request.state.request_id,
        )

    @api.get("/api/v1/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=config.app_version)

    @api.post("/api/v1/resolve", response_model=ResolveResponse)
    def resolve(payload: ResolveRequest, request: Request) -> ResolveResponse:
        post = resolver.resolve(payload.text)
        lease = media_store.create(resolver.name, post)
        return ResolveResponse(
            request_id=request.state.request_id,
            provider=resolver.name,
            media=ResolvedMediaOut(
                provider_id=post.provider_id,
                title=post.title,
                author=AuthorOut(name=post.author),
                source_url=post.source_url,
                variants=[
                    MediaVariantOut(
                        id=lease.handle,
                        label="原片 MP4",
                        mime_type="video/mp4",
                        size_bytes=post.candidates[0].size_bytes,
                        download_url=f"/api/v1/media/{lease.handle}",
                        expires_at=lease.expires_at,
                    )
                ],
            ),
        )

    @api.get("/api/v1/media/{handle}")
    def download(handle: str):
        lease = media_store.get(handle)
        path, filename = media_downloader.download(lease)
        return FileResponse(
            path,
            media_type="video/mp4",
            filename=filename,
            background=BackgroundTask(Path(path).unlink, missing_ok=True),
            headers={"Cache-Control": "private, no-store"},
        )

    return api


app = create_app()

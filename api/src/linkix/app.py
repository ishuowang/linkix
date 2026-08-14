from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

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
from .providers.base import Provider
from .providers.registry import ProviderRegistry
from .services.media import MediaArtifact, MediaDownloader
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


class CleanupFileResponse(FileResponse):
    def __init__(self, artifact: MediaArtifact, **kwargs):
        self.artifact = artifact
        super().__init__(artifact.path, filename=artifact.filename, **kwargs)

    async def __call__(self, scope, receive, send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.artifact.cleanup()


def create_app(
    *,
    settings: Settings | None = None,
    provider: Provider | None = None,
    store: MediaStore | None = None,
    downloader: MediaDownloader | None = None,
) -> FastAPI:
    config = settings or Settings.from_env()
    resolver = provider or ProviderRegistry.from_settings(config)
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
        provider_name = post.provider or resolver.name
        lease = media_store.create(provider_name, post)
        candidate = post.candidates[0]
        return ResolveResponse(
            request_id=request.state.request_id,
            provider=provider_name,
            media=ResolvedMediaOut(
                provider_id=post.provider_id,
                title=post.title,
                author=AuthorOut(name=post.author),
                source_url=post.source_url,
                variants=[
                    MediaVariantOut(
                        id=lease.handle,
                        label=candidate.label,
                        mime_type=candidate.mime_type,
                        size_bytes=candidate.total_size_bytes,
                        download_url=f"/api/v1/media/{lease.handle}",
                        expires_at=lease.expires_at,
                    )
                ],
            ),
        )

    @api.get("/api/v1/media/{handle}")
    def download(handle: str):
        lease = media_store.get(handle)
        artifact = media_downloader.download(lease)
        try:
            return CleanupFileResponse(
                artifact,
                media_type="video/mp4",
                headers={"Cache-Control": "private, no-store"},
            )
        except Exception:
            artifact.cleanup()
            raise

    return api


app = create_app()

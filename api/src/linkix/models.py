from __future__ import annotations

from pydantic import BaseModel, Field


class ResolveRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4096)


class AuthorOut(BaseModel):
    name: str


class MediaVariantOut(BaseModel):
    id: str
    label: str
    mime_type: str
    size_bytes: int | None = None
    download_url: str
    expires_at: str


class ResolvedMediaOut(BaseModel):
    provider_id: str
    title: str
    author: AuthorOut
    source_url: str
    variants: list[MediaVariantOut]


class ResolveResponse(BaseModel):
    request_id: str
    provider: str
    media: ResolvedMediaOut


class HealthResponse(BaseModel):
    status: str
    version: str

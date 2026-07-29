from __future__ import annotations

import os
from dataclasses import dataclass


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_csv(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    return tuple(item.strip().rstrip("/") for item in value.split(",") if item.strip())


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str = "linkix-api"
    app_version: str = "0.1.0"
    cors_origins: tuple[str, ...] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    max_input_chars: int = 4096
    max_redirects: int = 5
    max_upstream_bytes: int = 5 * 1024 * 1024
    max_media_bytes: int = 100 * 1024 * 1024
    media_handle_ttl_seconds: int = 15 * 60
    resolve_limit_per_minute: int = 10
    max_parallel_downloads: int = 4
    connect_retries: int = 4
    backoff_factor: float = 0.75
    enable_parser_fallback: bool = False
    parser_api: str = "https://douyin.wtf/api/douyin/web/fetch_one_video"
    douyin_proxy: str | None = None
    parser_trust_env: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        defaults = cls()
        return cls(
            cors_origins=_as_csv(os.getenv("LINKIX_CORS_ORIGINS"), defaults.cors_origins),
            max_input_chars=int(os.getenv("LINKIX_MAX_INPUT_CHARS", str(defaults.max_input_chars))),
            max_redirects=int(os.getenv("LINKIX_MAX_REDIRECTS", str(defaults.max_redirects))),
            max_upstream_bytes=int(
                os.getenv("LINKIX_MAX_UPSTREAM_BYTES", str(defaults.max_upstream_bytes))
            ),
            max_media_bytes=int(os.getenv("LINKIX_MAX_MEDIA_BYTES", str(defaults.max_media_bytes))),
            media_handle_ttl_seconds=int(
                os.getenv(
                    "LINKIX_MEDIA_HANDLE_TTL_SECONDS",
                    str(defaults.media_handle_ttl_seconds),
                )
            ),
            resolve_limit_per_minute=int(
                os.getenv(
                    "LINKIX_RESOLVE_LIMIT_PER_MINUTE",
                    str(defaults.resolve_limit_per_minute),
                )
            ),
            max_parallel_downloads=int(
                os.getenv(
                    "LINKIX_MAX_PARALLEL_DOWNLOADS",
                    str(defaults.max_parallel_downloads),
                )
            ),
            connect_retries=int(os.getenv("LINKIX_CONNECT_RETRIES", str(defaults.connect_retries))),
            backoff_factor=float(os.getenv("LINKIX_BACKOFF_FACTOR", str(defaults.backoff_factor))),
            enable_parser_fallback=_as_bool(
                os.getenv("LINKIX_ENABLE_PARSER_FALLBACK"),
                defaults.enable_parser_fallback,
            ),
            parser_api=os.getenv("LINKIX_PARSER_API", defaults.parser_api),
            douyin_proxy=os.getenv("LINKIX_DOUYIN_PROXY") or None,
            parser_trust_env=_as_bool(
                os.getenv("LINKIX_PARSER_TRUST_ENV"),
                defaults.parser_trust_env,
            ),
        )

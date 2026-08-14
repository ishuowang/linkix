# Linkix API

FastAPI service for resolving public Douyin, Kuaishou, Xiaohongshu, Bilibili, and
Weibo single-video share links. It exposes opaque, short-lived media handles and
never accepts arbitrary upstream download URLs.

Kuaishou uses its official public mobile page, while Xiaohongshu, Bilibili, and
Weibo use yt-dlp extractors. Bilibili DASH downloads require `ffmpeg` and
`ffprobe`; both are included in the API Docker image.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn linkix.app:app --host 127.0.0.1 --port 8010 --reload
```

See the repository root README for configuration and deployment guidance.

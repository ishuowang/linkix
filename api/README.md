# Linkix API

FastAPI service for resolving public Douyin video share links. It exposes opaque,
short-lived media handles and never accepts arbitrary upstream download URLs.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn linkix.app:app --host 127.0.0.1 --port 8010 --reload
```

See the repository root README for configuration and deployment guidance.

# Real deployable image for the standalone Ucuz Yemek backend service (see
# backend/server.py's module docstring for why this exists). Staged for a
# future deploy (e.g. to one of the portfolio's Oracle boxes via
# docker-compose.yml) -- not yet deployed anywhere public, per the standing
# ask-before-deploy/publish rule. Built and run locally against a local
# Postgres container during this pass; see plans/ucuz-yemek.md for the real
# verification evidence.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY ucuz_yemek ./ucuz_yemek
COPY backend ./backend
COPY web ./web
RUN uv sync --frozen --no-dev

EXPOSE 8811
CMD ["uv", "run", "uvicorn", "backend.server:app", "--host", "0.0.0.0", "--port", "8811"]

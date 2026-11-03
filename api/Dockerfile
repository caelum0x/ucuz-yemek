# Deployable image for the real web app + API (api/index.py), run as its own
# service on railyard-box instead of Vercel (owner constraint 2026-11-04: no
# Vercel for real production traffic -- see plans/ucuz-yemek.md). Same app,
# same code, just run via uvicorn instead of Vercel's Python builder. Reached
# Vercel this box's backend container is on the box's products-net, so DNS-
# resolves as http://ucuz-yemek-backend:8811 -- no public egress needed, which
# is the real reason the Vercel-hosted proxy never actually engaged.
FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY ucuz_yemek ./ucuz_yemek
COPY api ./api
COPY web ./web
RUN uv sync --frozen --no-dev

EXPOSE 8812
CMD ["uv", "run", "uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "8812"]

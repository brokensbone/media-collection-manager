# Single image serving both the API and the built SPA (D10). Build context = repo root.
# Stage 1: build the frontend.
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build  # -> /fe/dist

# Stage 2: the backend + bundled beets, with the built SPA copied in.
FROM python:3.12-slim AS app
# rsync + ssh client are needed at runtime to pull completed torrents off the seedbox (§12).
RUN apt-get update \
    && apt-get install -y --no-install-recommends rsync openssh-client \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir uv
WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock ./
COPY backend/src ./src
COPY backend/migrations ./migrations
COPY backend/alembic.ini ./
RUN uv sync --no-dev --frozen

# Put the venv on PATH so `uvicorn`, `alembic`, `python` and the bundled `beet` all resolve
# directly (the app shells out to a bare `beet`, §5).
ENV PATH="/app/backend/.venv/bin:$PATH"

COPY --from=frontend /fe/dist /app/frontend-dist

EXPOSE 8000
CMD ["uvicorn", "wantlist.app:app", "--host", "0.0.0.0", "--port", "8000"]

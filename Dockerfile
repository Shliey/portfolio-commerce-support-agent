FROM node:22-alpine AS web-build
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    BUSINESS_DB=/app/data/business.db \
    CHECKPOINT_DB=/app/data/checkpoints.db \
    WEB_DIST=/app/web-dist
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev
COPY --from=web-build /app/web/dist /app/web-dist
RUN mkdir -p /app/data
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD ["uv", "run", "--no-sync", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]
CMD ["uv", "run", "--no-sync", "uvicorn", "commerce_support.api:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]

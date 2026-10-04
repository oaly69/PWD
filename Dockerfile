# syntax=docker/dockerfile:1

# ---------- 前端构建 ----------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 运行镜像 ----------
FROM python:3.12-slim AS runtime

ARG VERSION=dev
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PWD_VERSION=${VERSION} \
    PWD_DATA_DIR=/data \
    PWD_PORT=8080 \
    PWD_STATIC_DIR=/app/frontend/dist \
    TZ=Asia/Shanghai

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/app backend/app
COPY --from=web /web/dist frontend/dist
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /data

VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PWD_PORT','8080'),timeout=4)" || exit 1

ENTRYPOINT ["/entrypoint.sh"]

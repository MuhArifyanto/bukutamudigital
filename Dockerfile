# ─── Stage 1: Builder (compile wheels with build toolchain) ─────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.lock .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.lock

# ─── Stage 2: Runtime (minimal image, no gcc, non-root user) ──────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /wheels /wheels
COPY requirements.lock .
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.lock \
    && rm -rf /wheels

# Create non-root user and writable runtime directories
RUN groupadd --system appgroup \
    && useradd --system --gid appgroup --create-home --home-dir /home/appuser appuser \
    && mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appgroup /app

# Copy application source (non-sensitive files only via .dockerignore)
COPY --chown=appuser:appgroup . .

# Collect static files with ephemeral build-time config only
RUN SECRET_KEY=dummy-build-time-secret-key \
    ALLOWED_HOSTS=localhost \
    CSRF_TRUSTED_ORIGINS=https://localhost \
    python manage.py collectstatic --noinput \
    && chown -R appuser:appgroup /app/staticfiles

USER appuser

EXPOSE 8000

# Container healthcheck (verifies DB & cache via /healthz/ using an allowed Host header)
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os, urllib.request; port=os.environ.get('PORT', '8000'); raw=os.environ.get('ALLOWED_HOSTS', 'localhost').split(','); h=next((x.strip().lstrip('*') for x in raw if x.strip() and x.strip() != '*'), 'localhost'); host=('healthcheck'+h if h.startswith('.') else h); req=urllib.request.Request(f'http://127.0.0.1:{port}/healthz/', headers={'Host': host}); resp=urllib.request.urlopen(req, timeout=4); assert resp.status == 200"

# Run migrations, cache table setup, optional admin sync, and start Daphne via exec for clean SIGTERM handling
CMD ["sh", "-c", "python manage.py migrate --noinput && (python manage.py createcachetable || true) && (python manage.py setup_admin || true) && exec daphne -b 0.0.0.0 -p ${PORT:-8000} bukudigital.asgi:application"]

# ─── Stage: Build ────────────────────────────────────────────────
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

# Install system dependencies (untuk mysqlclient)
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Set work directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Collect static files (dummy SECRET_KEY untuk build time saja)
RUN SECRET_KEY=dummy-build-time-secret-key python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Run Daphne (ASGI server - support WebSocket)
CMD daphne -b 0.0.0.0 -p $PORT bukudigital.asgi:application
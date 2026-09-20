# =====================================================================
# Telegram AI Agent Userbot - Multi-stage Production Container
# =====================================================================

# Stage 1: Build & wheels preparation
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --no-deps --wheel-dir /build/wheels -r requirements.txt

# Stage 2: Runtime image (non-root, minimal attack surface)
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TELEGRAM_SESSION_NAME=/data/userbot_session

# Create non-root user and persistent data volume directory
RUN groupadd -g 10001 userbot && \
    useradd -u 10001 -g userbot -m -d /home/userbot userbot && \
    mkdir -p /app /data && \
    chown -R userbot:userbot /app /data

WORKDIR /app

# Install wheels from builder stage
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels /wheels/* && \
    rm -rf /wheels

# Copy application source code
COPY --chown=userbot:userbot . .

# Switch to non-root user
USER userbot

VOLUME ["/data"]

CMD ["python", "main.py"]

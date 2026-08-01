FROM python:3.14-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


FROM python:3.14-slim

WORKDIR /app

RUN groupadd -g 1000 appuser && \
    useradd -m -u 1000 -g appuser appuser && \
    chown -R appuser:appuser /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /root/.local /home/appuser/.local

COPY --chown=appuser:appuser . .

USER appuser

ENV PATH=/home/appuser/.local/bin:$PATH \
    PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Trusted reverse proxy IPs for X-Forwarded-For (comma-separated).
# Empty = only loopback trusted; spoofed headers cannot bypass rate limits.
ENV FORWARDED_ALLOW_IPS=""

CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers \
    --forwarded-allow-ips "$FORWARDED_ALLOW_IPS"

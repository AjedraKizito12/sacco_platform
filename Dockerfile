# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.11.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
# Create a minimal package structure so hatchling can find the project
RUN mkdir -p app && touch app/__init__.py

RUN pip install --no-cache-dir --prefix=/install .

# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid 1000 --no-create-home --shell /bin/false appuser

WORKDIR /app

COPY --chown=appuser:appgroup . .

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

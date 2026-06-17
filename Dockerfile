FROM python:3.10-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.10-slim AS base

WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY . .

FROM base AS release
CMD ["alembic", "upgrade", "head"]

FROM base AS runner
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

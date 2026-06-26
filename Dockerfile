FROM python:3.10-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.10-slim

WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY . .

ENV PYTHONUNBUFFERED=1

CMD alembic upgrade head; uvicorn app.main:app --host 0.0.0.0 --port $PORT
# Cache bust to force fresh build and copy migrations
FROM python:3.10-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.10-slim AS runner

WORKDIR /app
COPY --from=builder /usr/local /usr/local
COPY . .

ENV PYTHONUNBUFFERED=1

RUN find /app/alembic -type d -name __pycache__ -exec rm -rf {} +
RUN test -f /app/alembic/versions/c2d3e4f5a6b7_add_course_chat_messages.py \
    && test -f /app/alembic/versions/d3e4f5a6b7c8_add_social_chat_tables.py
RUN alembic heads
RUN mv /usr/local/bin/alembic /usr/local/bin/alembic-real \
    && printf '%s\n' '#!/bin/sh' 'if [ "$1" = "upgrade" ] && [ "$2" = "head" ]; then' '  exec python -m app.scripts.release_migrate' 'fi' 'exec /usr/local/bin/alembic-real "$@"' > /usr/local/bin/alembic \
    && chmod +x /usr/local/bin/alembic

CMD ["sh", "-c", "python -m app.scripts.release_migrate && exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"]

# learning-hub-api

REST API Gateway for the Multimodal AI Learning Hub. Handles all HTTP requests, authentication, and service orchestration.

## Overview

This repository is the API Gateway that:
- Provides REST API endpoints for frontend
- Handles authentication (JWT)
- Manages document CRUD
- Orchestrates chat sessions
- Dispatches tasks to workers and AI service

## Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| ORM | SQLAlchemy (async) |
| Validation | Pydantic v2 |
| Auth | JWT (python-jose) |
| Task Client | Celery |

## Directory Structure

```
learning-hub-api/
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py
│   │       ├── documents.py
│   │       ├── chat.py
│   │       └── study.py
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   └── security.py
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   └── services/         # Business logic
├── alembic/              # Database migrations
├── docs/                 # API documentation
├── tests/
├── Dockerfile
├── requirements.txt
└── main.py
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
alembic upgrade head

# Run the service
uvicorn main:app --reload --port 8000
```

## Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db

# Redis
REDIS_URL=redis://localhost:6379/0

# External Services
AI_SERVICE_URL=http://localhost:8001
AI_SERVICE_API_KEY=your_key
MINIO_ENDPOINT=localhost:9000

# Auth
SECRET_KEY=your_secret_key
ALGORITHM=HS256
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register new user |
| POST | `/api/v1/auth/login` | Login |
| POST | `/api/v1/auth/refresh` | Refresh token |
| GET | `/api/v1/documents` | List documents |
| POST | `/api/v1/documents/upload` | Upload document |
| GET | `/api/v1/documents/{id}` | Get document |
| DELETE | `/api/v1/documents/{id}` | Delete document |
| POST | `/api/v1/chat/sessions` | Create chat session |
| GET | `/api/v1/chat/sessions` | List chat sessions |
| POST | `/api/v1/chat/ask` | Send message (streaming) |
| POST | `/api/v1/study/quiz/generate` | Generate quiz |
| POST | `/api/v1/study/flashcards/generate` | Generate flashcards |
| POST | `/api/v1/study/essay/submit` | Submit essay |

## Service Communication

- **AI Service**: Forward AI requests to `learning-hub-ai`
- **Worker**: Dispatch async tasks via Redis
- **Database**: PostgreSQL for persistence
- **Storage**: MinIO for file storage

## Related Documentation

- [Main Docs](../README.md) - System overview
- [API Contracts](../communication/api-contracts.md) - Service contracts
- [System Design](../3-architecture/system-design.md) - Architecture details

## CI/CD Secrets Validation Bypass

In production mode (`DEBUG=False`), the application settings class `Settings` ([app/core/config.py](file:///d:/Laptrinh/Project_Practice/MULTIMODAL%20AI%20LEARNING%20HUB/learning-hub-api/app/core/config.py)) validates that both `SECRET_KEY` and `INTERNAL_API_KEY` are secure and non-default.

To prevent build/deployment pipeline crashes (such as Heroku's release command `alembic upgrade head`) or local/CI test suite failures (`pytest`) when these keys are not yet configured or populated in the environment:

- Validation is **automatically bypassed** if the process is identified as a database migration (`alembic` is running) or a test runner (`pytest` is executing).
- For runtime services (like the production Uvicorn web dyno), the security checks remain **fully active** to guarantee that the server will fail to start if not configured with secure keys.
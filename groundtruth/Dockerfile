# Groundtruth — single-container production image.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install core dependencies first (better layer caching).
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Optional: enable real LLM extraction by uncommenting the next two lines.
# COPY backend/requirements-llm.txt /app/backend/requirements-llm.txt
# RUN pip install --no-cache-dir -r /app/backend/requirements-llm.txt

COPY backend /app/backend
COPY frontend /app/frontend

WORKDIR /app/backend
EXPOSE 8000

# Run migrations happen on startup (create_all). Single worker keeps SQLite safe;
# scale out only with a Postgres DATABASE_URL.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

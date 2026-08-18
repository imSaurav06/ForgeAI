# Production Multi-Service Dockerfile for ForgeAI Platform
FROM python:3.12-slim as base

# Prevent Python from writing pyc files to disk and disable buffering
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

# Set working directory
WORKDIR /app

# Install system dependencies (git, curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml and dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

# Copy application source code
COPY shared /app/shared
COPY services /app/services
COPY docs /app/docs

# Default port exposure
EXPOSE 8000 8001 8002 8003 8004 8005 8006 8007

# Default entrypoint for Gateway Service
CMD ["python", "-m", "uvicorn", "services.gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]

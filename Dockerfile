# Cloud Run deployment - optimized for layer caching
FROM python:3.12-slim

# Install system dependencies
RUN apt update && apt install -y curl procps git && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

# Use copy mode instead of symlinks for Cloud Run compatibility
ENV UV_LINK_MODE=copy

# Copy dependency files first (changes less often = better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies (this layer is cached unless deps change)
RUN uv sync --no-dev

# Pre-download the embedding model into the image (avoids HF rate limits at startup)
RUN /app/.venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

# Copy application code (changes often, but deps are already cached)
COPY backend/ ./backend/

EXPOSE 8080

# Default model (can be overridden via Cloud Run env vars)
ENV MODEL_NAME=gemini-3-flash-preview
ENV PYTHONPATH=/app
ENV PORT=8080

# Run uvicorn via the venv created by uv
CMD ["/app/.venv/bin/uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.12-slim

WORKDIR /app

# Install system utilities for local debugging if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency definitions first for layer caching
COPY pyproject.toml /app/

# Create minimal src structure so editable install succeeds during build
RUN mkdir -p /app/src/badge_tracker && touch /app/src/badge_tracker/__init__.py
RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8080

# Run uvicorn with live reload watching both source code and YAML definitions
CMD ["uvicorn", "badge_tracker.main:app", "--host", "0.0.0.0", "--port", "8080", "--reload", "--reload-dir", "/app/src", "--reload-dir", "/app/data/goals"]

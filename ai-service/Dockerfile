FROM python:3.12-slim

WORKDIR /app

# System deps for native audio/crypto libs
RUN apt-get update && apt-get install -y \
    gcc g++ libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Worker-only deps (< 100MB RAM target) — never the ~500MB+ docling/torch
# resume/JD parsing stack, which app.voice_agent.worker never imports (see
# requirements-worker.txt's comment). Use requirements-api.txt instead if
# this Dockerfile ever needs to build app.main:app's image.
COPY requirements-worker.txt .
RUN pip install --no-cache-dir -r requirements-worker.txt

# Copy app code, config, and environment
COPY .env* ./
COPY app/ ./app/
COPY config/ ./config/

# Expose port (Render/Cloud Run dynamically set $PORT)
EXPOSE 8080 10000

# AgentServer (num_idle_processes=0) binds to PORT immediately and satisfies Render health check
CMD ["python", "-m", "app.voice_agent.worker", "start"]

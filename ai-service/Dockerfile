FROM python:3.12-slim

WORKDIR /app

# System deps for native audio/crypto libs
RUN apt-get update && apt-get install -y \
    gcc g++ libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app code and config
COPY app/ ./app/
COPY config/ ./config/

# Expose port (Render/Cloud Run dynamically set $PORT)
EXPOSE 8080 10000

# AgentServer (num_idle_processes=0) binds to PORT immediately and satisfies Render health check
CMD ["python", "-m", "app.voice_agent.worker", "start"]

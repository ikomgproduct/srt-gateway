FROM python:3.11-slim

# Install FFmpeg to get SRT capabilities
RUN apt-get update && apt-get install -y ffmpeg curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Web App Port
EXPOSE 8000
# SRT Input/Output Ports (adjust range if needed)
EXPOSE 9000-9100/udp

# Explicitly use backend module
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

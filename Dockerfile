FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN mkdir -p /roms /media

ENV PYTHONUNBUFFERED=1
ENV ROMS_PATH=/roms
ENV MEDIA_PATH=/media

EXPOSE 5000

ENV PYTHONPATH=/app
CMD ["python", "-m", "backend.app"]

# Compile the pages' JSX and bundle React, so the app needs no CDN and no
# in-browser compiler (see tools/build_frontend.js)
FROM node:20-slim AS frontend
WORKDIR /build
RUN npm install --no-save --no-audit --no-fund react@18.3.1 react-dom@18.3.1 @babel/core@7.25.2 @babel/preset-react@7.24.7
COPY tools/build_frontend.js .
COPY frontend/ ./frontend/
RUN node build_frontend.js frontend

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /build/frontend/ ./frontend/

RUN mkdir -p /roms /media

ENV PYTHONUNBUFFERED=1
ENV ROMS_PATH=/roms
ENV MEDIA_PATH=/media

EXPOSE 5000

ENV PYTHONPATH=/app
# One worker: the library scrape, upload staging and caches live in its memory.
# Threads serve requests side by side; the long timeout covers big uploads and
# slow scraping sources.
CMD ["gunicorn", "--workers", "1", "--threads", "16", "--timeout", "600", "--bind", "0.0.0.0:5000", "--access-logfile", "-", "backend.app:app"]

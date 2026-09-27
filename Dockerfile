FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=7860 \
    FORWARDED_ALLOW_IPS=*

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=app:app scraper/ scraper/
COPY --from=frontend --chown=app:app /build/dist frontend/dist
RUN mkdir -p output logs && chown app:app output logs

USER app
EXPOSE 7860
CMD ["python", "-m", "scraper.web"]

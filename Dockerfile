# SpecGrid web server (FastAPI + the build-free frontend), for docker-compose.yml.
# Same Python as local development (3.14) so behaviour matches what the tests ran on.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is reused until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY frontend ./frontend
COPY scripts ./scripts

# Never run the web server as root. Uploaded photos go to /data/media (a host folder that nginx
# also reads, see docker-compose.yml); uid 10001 must own it on the host (deploy/README.md).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin specgrid \
 && mkdir -p /data/media && chown specgrid /data/media
USER specgrid

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"

# Migrations run in the separate "migrate" service (docker-compose.yml), not here.
# --proxy-headers: trust X-Forwarded-For from nginx so rate limits / logs see the real client IP.
# Safe with '*' only because docker-compose.yml publishes this port on 127.0.0.1 (nginx is the
# only thing on the host that can reach it).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

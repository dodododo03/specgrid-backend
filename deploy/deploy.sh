#!/bin/bash
# Update the running site to the latest code on GitHub.
#
#   ./deploy/deploy.sh
#
# Steps: pull -> rebuild the app image -> restart (the app container runs migrations on start)
# -> wait until /api/v1/health answers 200. MariaDB/Redis keep running; their data is untouched.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== git pull"
git pull --ff-only

echo "== build + restart app"
docker compose up -d --build

echo "== waiting for health check"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1; then
    curl -sS http://127.0.0.1:8000/api/v1/health; echo
    echo "== deployed $(git rev-parse --short HEAD)"
    docker image prune -f >/dev/null   # drop old image layers so the small disk doesn't fill up
    exit 0
  fi
  sleep 2
done

echo "!! app did not become healthy in 60s. Recent logs:" >&2
docker compose logs --tail=60 app >&2
exit 1

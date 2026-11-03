#!/bin/bash
# Installed on the VPS as /srv/reservas/post-deploy.sh (root:root 755).
# Run by deploy-project after the containers are up: the Django steps.
set -euo pipefail
cd /srv/reservas

manage() {
    docker compose exec -T web python manage.py "$@"
}

manage migrate --noinput
manage createcachetable
manage collectstatic --noinput
manage check --deploy --fail-level ERROR

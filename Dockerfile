# Production image: Django + Gunicorn. Used by deploy/docker-compose.prod.yml.
# Two stages: the first compiles mysqlclient (needs a compiler); the second only
# carries the result, so the final image is small and has no build tools.

# --- 1. Build the Python packages --------------------------------------------
FROM python:3.14-slim AS build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt


# --- 2. The image that runs --------------------------------------------------
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# Only the MySQL client library (no compiler).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmariadb3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# The app never runs as root. A fixed uid, so the server can give it the
# staticfiles/ and media/ folders (see deploy/docker-compose.prod.yml).
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY --chown=app:app . .
USER app

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", "--access-logfile", "-"]

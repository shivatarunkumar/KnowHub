# Image for the one-off `init` job and the Make targets: runs database/ and infra/ scripts.
# The repo is mounted at /workspace at runtime, so only dependencies are baked in.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# postgresql-client provides psql, used by database/scripts/init_db.sh and dump_schema
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /workspace

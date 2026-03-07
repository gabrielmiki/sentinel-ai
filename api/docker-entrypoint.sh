#!/bin/sh
set -e

# Build connection URLs from Docker secrets at runtime
# This prevents hardcoding passwords in environment variables

# Read secrets from mounted files
REDIS_PASS=$(cat /run/secrets/redis_password)
DB_PASS=$(cat /run/secrets/db_password)
VECTORDB_PASS=$(cat /run/secrets/vectordb_password)

# Export connection URLs with passwords from secrets
export REDIS_URL="redis://:${REDIS_PASS}@redis:6379/0"
export CELERY_BROKER_URL="redis://:${REDIS_PASS}@redis:6379/1"
export CELERY_RESULT_BACKEND="redis://:${REDIS_PASS}@redis:6379/2"
export VECTORDB_URL="postgresql+asyncpg://vectoradmin:${VECTORDB_PASS}@vectordb:5432/vectordb"
export DATABASE_URL="postgresql+asyncpg://sentinel:${DB_PASS}@postgres:5432/sentinelai"

# Execute the command passed to the container
exec "$@"

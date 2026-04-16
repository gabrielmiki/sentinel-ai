#!/bin/sh
set -e

# Build connection URLs from Docker secrets at runtime
# This prevents hardcoding passwords in environment variables

# Read secrets from mounted files
REDIS_PASS=$(cat /run/secrets/redis_password)
DB_PASS=$(cat /run/secrets/db_password)
VECTORDB_PASS=$(cat /run/secrets/vectordb_password)

# Read API keys from secrets (allow empty if not configured)
export GOOGLE_API_KEY=$(cat /run/secrets/google_api_key 2>/dev/null || echo "")
export ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_api_key 2>/dev/null || echo "")
export JWT_SECRET_KEY=$(cat /run/secrets/jwt_secret_key 2>/dev/null || echo "")

# Export connection URLs with passwords from secrets
export REDIS_URL="redis://:${REDIS_PASS}@redis:6379/0"
export CELERY_BROKER_URL="redis://:${REDIS_PASS}@redis:6379/1"
export CELERY_RESULT_BACKEND="redis://:${REDIS_PASS}@redis:6379/2"
export VECTORDB_URL="postgresql+asyncpg://vectoradmin:${VECTORDB_PASS}@vectordb:5432/vectordb"
export DATABASE_URL="postgresql+asyncpg://sentinel:${DB_PASS}@postgres:5432/sentinelai"

# Print startup info (without exposing secrets)
echo "Starting Sentinel AI Backend..."
echo "GOOGLE_API_KEY configured: $([ -n "$GOOGLE_API_KEY" ] && echo "yes" || echo "no")"

# Execute the command passed to the container
exec "$@"

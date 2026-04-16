#!/bin/bash
set -e

# Load secrets from Docker secrets into environment variables
export GOOGLE_API_KEY=$(cat /run/secrets/google_api_key 2>/dev/null || echo "")
export ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_api_key 2>/dev/null || echo "")
export JWT_SECRET_KEY=$(cat /run/secrets/jwt_secret_key 2>/dev/null || echo "")

# Build database URLs from secrets
DB_PASSWORD=$(cat /run/secrets/db_password)
VECTORDB_PASSWORD=$(cat /run/secrets/vectordb_password)
REDIS_PASSWORD=$(cat /run/secrets/redis_password)

export DATABASE_URL="postgresql+asyncpg://sentinel:${DB_PASSWORD}@postgres:5432/sentinel"
export VECTORDB_URL="postgresql+asyncpg://vectoradmin:${VECTORDB_PASSWORD}@vectordb:5432/vectordb"
export REDIS_URL="redis://:${REDIS_PASSWORD}@redis:6379/0"

# Print startup info (without exposing secrets)
echo "Starting Sentinel AI Backend..."
echo "DATABASE_URL configured: ${DATABASE_URL%%:*}://***@postgres:5432/sentinel"
echo "VECTORDB_URL configured: ${VECTORDB_URL%%:*}://***@vectordb:5432/vectordb"
echo "REDIS_URL configured: redis://***@redis:6379/0"
echo "GOOGLE_API_KEY configured: $([ -n "$GOOGLE_API_KEY" ] && echo "yes" || echo "no")"
echo "ANTHROPIC_API_KEY configured: $([ -n "$ANTHROPIC_API_KEY" ] && echo "yes" || echo "no")"

# Execute the main command
exec "$@"

#!/bin/bash
set -e

# Read passwords from secrets
DB_PASS=$(cat secrets/db_password.txt)
VDB_PASS=$(cat secrets/vectordb_password.txt)

# Export environment variables
export DATABASE_URL="postgresql+asyncpg://sentinel:${DB_PASS}@localhost:15432/sentinel_test"
export VECTORDB_URL="postgresql+asyncpg://vectoradmin:${VDB_PASS}@localhost:15433/vectordb_test"

# Run tests
uv run pytest "$@"

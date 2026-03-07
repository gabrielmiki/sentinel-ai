# Docker Secrets Directory

This directory contains sensitive credentials used by Docker Swarm secrets.

## Setup

1. **Development**: Run the setup script to generate random secrets:
   ```bash
   ./scripts/generate-secrets.sh
   ```

2. **Production**: Manually create secret files with your actual credentials:
   ```bash
   echo "your-actual-password" > secrets/db_password.txt
   echo "your-api-key" > secrets/openai_api_key.txt
   # ... etc
   ```

## Required Secret Files

- `db_password.txt` - PostgreSQL database password
- `vectordb_password.txt` - Vector database (pgvector) password
- `redis_password.txt` - Redis password
- `openai_api_key.txt` - OpenAI API key
- `anthropic_api_key.txt` - Anthropic API key
- `jwt_secret_key.txt` - JWT signing secret
- `grafana_admin_password.txt` - Grafana admin password

## Security Notes

- **NEVER** commit actual secret files to git
- All `*.txt` files are gitignored by default
- Use strong, randomly generated passwords in production
- Rotate secrets regularly
- Use environment-specific secrets (dev/staging/prod)

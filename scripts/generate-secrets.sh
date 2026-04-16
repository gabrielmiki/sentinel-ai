#!/bin/bash
set -e

SECRETS_DIR="./secrets"

echo "🔐 Generating Docker Swarm secrets for development..."

# Function to generate random password
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

# Function to generate JWT secret
generate_jwt_secret() {
    openssl rand -hex 32
}

# Create secrets directory if it doesn't exist
mkdir -p "$SECRETS_DIR"

# Generate database passwords
echo "$(generate_password)" > "$SECRETS_DIR/db_password.txt"
echo "$(generate_password)" > "$SECRETS_DIR/vectordb_password.txt"
echo "$(generate_password)" > "$SECRETS_DIR/redis_password.txt"
echo "$(generate_password)" > "$SECRETS_DIR/grafana_admin_password.txt"

# Generate JWT secret
echo "$(generate_jwt_secret)" > "$SECRETS_DIR/jwt_secret_key.txt"

# Create placeholder API key files (user must replace these)
if [ ! -f "$SECRETS_DIR/openai_api_key.txt" ]; then
    echo "sk-REPLACE_WITH_YOUR_GOOGLE_API_KEY" > "$SECRETS_DIR/openai_api_key.txt"
    echo "⚠️  GOOGLE_API_KEY: Please replace placeholder in secrets/openai_api_key.txt"
fi

if [ ! -f "$SECRETS_DIR/anthropic_api_key.txt" ]; then
    echo "sk-ant-REPLACE_WITH_YOUR_ANTHROPIC_API_KEY" > "$SECRETS_DIR/anthropic_api_key.txt"
    echo "⚠️  ANTHROPIC_API_KEY: Please replace placeholder in secrets/anthropic_api_key.txt"
fi

# Set appropriate permissions
chmod 600 "$SECRETS_DIR"/*.txt

echo ""
echo "✅ Secrets generated successfully!"
echo ""
echo "Generated secrets:"
echo "  - db_password.txt"
echo "  - vectordb_password.txt"
echo "  - redis_password.txt"
echo "  - grafana_admin_password.txt"
echo "  - jwt_secret_key.txt"
echo ""
echo "⚠️  IMPORTANT: Update these files with your actual API keys:"
echo "  - secrets/openai_api_key.txt"
echo "  - secrets/anthropic_api_key.txt"
echo ""
echo "🔒 All secret files are gitignored and should NEVER be committed."

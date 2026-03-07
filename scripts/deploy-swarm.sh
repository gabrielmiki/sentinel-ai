#!/bin/bash
set -e

STACK_NAME="sentinel"
COMPOSE_FILE="docker-compose.yml"

echo "🚀 Deploying SentinelAI to Docker Swarm..."

# Check if Docker Swarm is initialized
if ! docker info | grep -q "Swarm: active"; then
    echo "⚠️  Docker Swarm is not active. Initializing..."
    docker swarm init
    echo "✅ Docker Swarm initialized"
fi

# Check if secrets exist
if [ ! -f "./secrets/db_password.txt" ]; then
    echo "❌ Secrets not found. Please run ./scripts/generate-secrets.sh first"
    exit 1
fi

# Create Docker secrets (ignore if they already exist)
echo "🔐 Creating Docker secrets..."
docker secret create db_password ./secrets/db_password.txt 2>/dev/null || echo "  - db_password already exists"
docker secret create vectordb_password ./secrets/vectordb_password.txt 2>/dev/null || echo "  - vectordb_password already exists"
docker secret create redis_password ./secrets/redis_password.txt 2>/dev/null || echo "  - redis_password already exists"
docker secret create openai_api_key ./secrets/openai_api_key.txt 2>/dev/null || echo "  - openai_api_key already exists"
docker secret create anthropic_api_key ./secrets/anthropic_api_key.txt 2>/dev/null || echo "  - anthropic_api_key already exists"
docker secret create jwt_secret_key ./secrets/jwt_secret_key.txt 2>/dev/null || echo "  - jwt_secret_key already exists"
docker secret create grafana_admin_password ./secrets/grafana_admin_password.txt 2>/dev/null || echo "  - grafana_admin_password already exists"

# Deploy the stack
echo ""
echo "📦 Deploying stack '$STACK_NAME'..."
docker stack deploy -c "$COMPOSE_FILE" "$STACK_NAME"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📊 Check status:"
echo "  docker stack services $STACK_NAME"
echo "  docker stack ps $STACK_NAME"
echo ""
echo "📝 View logs:"
echo "  docker service logs ${STACK_NAME}_backend -f"
echo "  docker service logs ${STACK_NAME}_celery-worker -f"
echo ""
echo "🌐 Endpoints:"
echo "  - API: http://localhost"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana: http://localhost:3000 (admin/[check secrets/grafana_admin_password.txt])"

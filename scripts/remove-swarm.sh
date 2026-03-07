#!/bin/bash
set -e

STACK_NAME="sentinel"

echo "🗑️  Removing SentinelAI stack from Docker Swarm..."

# Remove the stack
docker stack rm "$STACK_NAME"

echo "⏳ Waiting for services to shut down..."
sleep 10

echo ""
echo "✅ Stack removed successfully!"
echo ""
echo "🔐 To also remove secrets, run:"
echo "  docker secret rm db_password vectordb_password redis_password openai_api_key anthropic_api_key jwt_secret_key grafana_admin_password"
echo ""
echo "💾 To remove volumes, run:"
echo "  docker volume rm ${STACK_NAME}_postgres_data ${STACK_NAME}_vectordb_data ${STACK_NAME}_redis_data ${STACK_NAME}_prometheus_data ${STACK_NAME}_grafana_data"

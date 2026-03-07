#!/bin/bash
set -e

STACK_NAME="sentinel"
SERVICE_NAME=$1

if [ -z "$SERVICE_NAME" ]; then
    echo "Usage: ./scripts/update-swarm.sh <service-name>"
    echo ""
    echo "Available services:"
    echo "  - backend"
    echo "  - celery-worker"
    echo "  - nginx"
    echo "  - all (update all services)"
    exit 1
fi

echo "🔄 Updating service(s)..."

if [ "$SERVICE_NAME" = "all" ]; then
    echo "📦 Updating entire stack..."
    docker stack deploy -c docker-compose.yml "$STACK_NAME"
else
    echo "📦 Forcing update for ${STACK_NAME}_${SERVICE_NAME}..."
    docker service update --force "${STACK_NAME}_${SERVICE_NAME}"
fi

echo ""
echo "✅ Update initiated!"
echo ""
echo "📊 Monitor the update:"
echo "  docker service ps ${STACK_NAME}_${SERVICE_NAME}"

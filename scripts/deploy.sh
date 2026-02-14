#!/bin/bash
set -e

# Deployment script for OVH bare metal server
# This script is called by GitHub Actions CI/CD pipeline

DEPLOY_PATH="${DEPLOY_PATH:-.}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yml}"
COMPOSE_TRAEFIK="${COMPOSE_TRAEFIK:-compose.traefik.yml}"

echo "🚀 Starting deployment..."

# Change to deployment directory
cd "$DEPLOY_PATH"

# Pull latest code
echo "📥 Pulling latest code..."
git fetch origin
git checkout "$GIT_BRANCH"
git pull origin "$GIT_BRANCH"

# Log in to container registry
echo "🔐 Logging in to container registry..."
echo "$REGISTRY_TOKEN" | docker login ghcr.io -u "$REGISTRY_USER" --password-stdin

# Pull latest images
echo "📦 Pulling latest Docker images..."
docker pull "$DOCKER_IMAGE_BACKEND" || true
docker pull "$DOCKER_IMAGE_FRONTEND" || true

# Stop old containers
echo "🛑 Stopping old containers..."
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_TRAEFIK" down || true

# Start new containers
echo "▶️  Starting new containers..."
docker compose -f "$COMPOSE_FILE" -f "$COMPOSE_TRAEFIK" up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check backend health
echo "🏥 Checking backend health..."
if docker compose -f "$COMPOSE_FILE" exec -T backend curl -f http://localhost:8000/api/v1/utils/health-check/ > /dev/null 2>&1; then
    echo "✅ Backend is healthy"
else
    echo "⚠️  Backend health check failed, but continuing..."
fi

# Clean up old images
echo "🧹 Cleaning up old Docker images..."
docker image prune -f --filter "until=72h"

# Log deployment info
echo "📊 Deployment info:"
docker compose -f "$COMPOSE_FILE" ps

echo "✨ Deployment completed successfully!"

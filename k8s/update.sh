#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CogMem Kubernetes Update Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Default values
SERVICE="all"
TAG="latest"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --service)
      SERVICE="$2"
      shift 2
      ;;
    --tag)
      TAG="$2"
      shift 2
      ;;
    --help)
      echo "Usage: ./update.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --service <name>   Update specific service (backend|frontend|all)"
      echo "  --tag <tag>        Docker image tag to deploy (default: latest)"
      echo "  --help             Show this help message"
      echo ""
      echo "Examples:"
      echo "  ./update.sh                           # Update all services with latest tag"
      echo "  ./update.sh --service backend         # Update only backend"
      echo "  ./update.sh --tag v1.0.1              # Update all with specific tag"
      echo "  ./update.sh --service frontend --tag v1.0.1"
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
done

update_backend() {
    echo -e "${YELLOW}Updating backend to tag: ${TAG}${NC}"
    kubectl set image deployment/backend backend=ghcr.io/cogmemai/cogmem-backend:${TAG} -n cogmem
    kubectl rollout status deployment/backend -n cogmem
    echo -e "${GREEN}✓ Backend updated${NC}"
}

update_frontend() {
    echo -e "${YELLOW}Updating frontend to tag: ${TAG}${NC}"
    kubectl set image deployment/frontend frontend=ghcr.io/cogmemai/cogmem-frontend:${TAG} -n cogmem
    kubectl rollout status deployment/frontend -n cogmem
    echo -e "${GREEN}✓ Frontend updated${NC}"
}

case $SERVICE in
  backend)
    update_backend
    ;;
  frontend)
    update_frontend
    ;;
  all)
    update_backend
    echo ""
    update_frontend
    ;;
  *)
    echo -e "${RED}Invalid service: $SERVICE${NC}"
    echo "Valid options: backend, frontend, all"
    exit 1
    ;;
esac

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Update Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Current pod status:${NC}"
kubectl get pods -n cogmem
echo ""

#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}CogMem Kubernetes Deployment Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl is not installed or not in PATH${NC}"
    exit 1
fi

# Check if secrets.yaml exists
if [ ! -f "k8s/base/secrets.yaml" ]; then
    echo -e "${RED}Error: k8s/base/secrets.yaml not found!${NC}"
    echo -e "${YELLOW}Please copy k8s/base/secrets.yaml.template to k8s/base/secrets.yaml${NC}"
    echo -e "${YELLOW}and fill in your base64-encoded secrets.${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Creating namespace and base resources...${NC}"
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/storage-class.yaml
kubectl apply -f k8s/base/configmap.yaml
kubectl apply -f k8s/base/secrets.yaml
echo -e "${GREEN}✓ Base resources created${NC}"
echo ""

echo -e "${YELLOW}Step 2: Creating persistent volumes...${NC}"
kubectl apply -f k8s/base/postgres-pvc.yaml
kubectl apply -f k8s/base/neo4j-pvc.yaml
kubectl apply -f k8s/base/qdrant-pvc.yaml
kubectl apply -f k8s/base/surrealdb-pvc.yaml
echo -e "${GREEN}✓ Persistent volumes created${NC}"
echo ""

echo -e "${YELLOW}Step 3: Deploying databases...${NC}"
kubectl apply -f k8s/databases/postgres.yaml
kubectl apply -f k8s/databases/neo4j.yaml
kubectl apply -f k8s/databases/qdrant.yaml
kubectl apply -f k8s/databases/surrealdb.yaml
echo -e "${GREEN}✓ Database deployments created${NC}"
echo ""

echo -e "${YELLOW}Step 4: Waiting for PostgreSQL to be ready...${NC}"
kubectl wait --namespace cogmem \
  --for=condition=ready pod \
  --selector=app=postgres \
  --timeout=300s
echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
echo ""

echo -e "${YELLOW}Step 5: Running database migrations...${NC}"
kubectl delete job prestart-migration -n cogmem --ignore-not-found=true
kubectl apply -f k8s/services/prestart-job.yaml
kubectl wait --namespace cogmem \
  --for=condition=complete job/prestart-migration \
  --timeout=300s || {
    echo -e "${RED}Migration job failed. Check logs with:${NC}"
    echo -e "${YELLOW}kubectl logs -n cogmem job/prestart-migration${NC}"
    exit 1
}
echo -e "${GREEN}✓ Database migrations completed${NC}"
echo ""

echo -e "${YELLOW}Step 6: Deploying application services...${NC}"
kubectl apply -f k8s/services/backend.yaml
kubectl apply -f k8s/services/frontend.yaml
kubectl apply -f k8s/services/adminer.yaml
echo -e "${GREEN}✓ Application services deployed${NC}"
echo ""

echo -e "${YELLOW}Step 7: Configuring cert-manager...${NC}"
kubectl apply -f k8s/ingress/cert-manager.yaml
echo -e "${GREEN}✓ Cert-manager configured${NC}"
echo ""

echo -e "${YELLOW}Step 8: Deploying ingress...${NC}"
kubectl apply -f k8s/ingress/ingress.yaml
echo -e "${GREEN}✓ Ingress deployed${NC}"
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Checking deployment status...${NC}"
echo ""
kubectl get pods -n cogmem
echo ""
echo -e "${YELLOW}To view logs:${NC}"
echo "  kubectl logs -n cogmem -l app=backend --tail=100"
echo "  kubectl logs -n cogmem -l app=frontend --tail=100"
echo ""
echo -e "${YELLOW}To check ingress:${NC}"
echo "  kubectl get ingress -n cogmem"
echo ""
echo -e "${YELLOW}To check certificates:${NC}"
echo "  kubectl get certificate -n cogmem"
echo ""
echo -e "${GREEN}Your application should be accessible at:${NC}"
echo "  https://dashboard.yourdomain.com"
echo "  https://api.yourdomain.com"
echo ""

#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}========================================${NC}"
echo -e "${RED}CogMem Kubernetes Teardown Script${NC}"
echo -e "${RED}========================================${NC}"
echo ""
echo -e "${YELLOW}WARNING: This will delete all CogMem resources!${NC}"
echo -e "${YELLOW}This includes all data in databases!${NC}"
echo ""
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${GREEN}Aborted.${NC}"
    exit 0
fi

echo -e "${YELLOW}Deleting ingress...${NC}"
kubectl delete -f k8s/ingress/ingress.yaml --ignore-not-found=true
kubectl delete -f k8s/ingress/cert-manager.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Ingress deleted${NC}"

echo -e "${YELLOW}Deleting application services...${NC}"
kubectl delete -f k8s/services/backend.yaml --ignore-not-found=true
kubectl delete -f k8s/services/frontend.yaml --ignore-not-found=true
kubectl delete -f k8s/services/adminer.yaml --ignore-not-found=true
kubectl delete -f k8s/services/prestart-job.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Application services deleted${NC}"

echo -e "${YELLOW}Deleting databases...${NC}"
kubectl delete -f k8s/databases/postgres.yaml --ignore-not-found=true
kubectl delete -f k8s/databases/neo4j.yaml --ignore-not-found=true
kubectl delete -f k8s/databases/qdrant.yaml --ignore-not-found=true
kubectl delete -f k8s/databases/surrealdb.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Databases deleted${NC}"

echo -e "${YELLOW}Deleting persistent volumes...${NC}"
kubectl delete -f k8s/base/postgres-pvc.yaml --ignore-not-found=true
kubectl delete -f k8s/base/neo4j-pvc.yaml --ignore-not-found=true
kubectl delete -f k8s/base/qdrant-pvc.yaml --ignore-not-found=true
kubectl delete -f k8s/base/surrealdb-pvc.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Persistent volumes deleted${NC}"

echo -e "${YELLOW}Deleting base resources...${NC}"
kubectl delete -f k8s/base/configmap.yaml --ignore-not-found=true
kubectl delete -f k8s/base/secrets.yaml --ignore-not-found=true
kubectl delete -f k8s/base/storage-class.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Base resources deleted${NC}"

echo -e "${YELLOW}Deleting namespace...${NC}"
kubectl delete -f k8s/base/namespace.yaml --ignore-not-found=true
echo -e "${GREEN}✓ Namespace deleted${NC}"

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Teardown Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Note: Data on the host at /data/* still exists.${NC}"
echo -e "${YELLOW}To completely remove data, run on the server:${NC}"
echo "  sudo rm -rf /data/postgres /data/neo4j /data/qdrant /data/surrealdb"
echo ""

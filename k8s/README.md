# Kubernetes Deployment for CogMem

This directory contains all Kubernetes manifests for deploying the CogMem application to a Rancher/RKE2 cluster.

## Directory Structure

```
k8s/
├── base/                    # Base configuration
│   ├── namespace.yaml       # Namespace definition
│   ├── storage-class.yaml   # Storage class for PVs
│   ├── configmap.yaml       # Application configuration
│   ├── secrets.yaml.template # Secrets template (DO NOT COMMIT secrets.yaml)
│   ├── postgres-pvc.yaml    # PostgreSQL persistent volume
│   ├── neo4j-pvc.yaml       # Neo4j persistent volumes
│   ├── qdrant-pvc.yaml      # Qdrant persistent volume
│   └── surrealdb-pvc.yaml   # SurrealDB persistent volume
├── databases/               # Database deployments
│   ├── postgres.yaml        # PostgreSQL deployment
│   ├── neo4j.yaml           # Neo4j deployment
│   ├── qdrant.yaml          # Qdrant deployment
│   └── surrealdb.yaml       # SurrealDB deployment
├── services/                # Application services
│   ├── backend.yaml         # FastAPI backend
│   ├── frontend.yaml        # React frontend
│   ├── adminer.yaml         # Database admin tool
│   └── prestart-job.yaml    # Database migration job
├── ingress/                 # Ingress configuration
│   ├── cert-manager.yaml    # Let's Encrypt configuration
│   └── ingress.yaml         # Nginx Ingress rules
└── README.md                # This file
```

## Prerequisites

1. **Rancher/RKE2 cluster** running (see RANCHER_SETUP.md)
2. **kubectl** configured to access your cluster
3. **Docker images** built and pushed to a registry
4. **DNS records** configured for your domains

## Quick Start

### 1. Configure Your Environment

Edit the following files with your actual values:

**`k8s/base/configmap.yaml`:**
- Change all `yourdomain.com` to your actual domain
- Update `FIRST_SUPERUSER` email
- Update CORS origins

**`k8s/ingress/ingress.yaml`:**
- Replace all `yourdomain.com` with your actual domain

**`k8s/ingress/cert-manager.yaml`:**
- Update email address for Let's Encrypt

**`k8s/services/backend.yaml` and `k8s/services/frontend.yaml`:**
- Update Docker image URLs to your registry

### 2. Create Secrets

```bash
# Copy the template
cp k8s/base/secrets.yaml.template k8s/base/secrets.yaml

# Generate base64 encoded secrets
echo -n "your-postgres-password" | base64
echo -n "your-neo4j-password" | base64
echo -n "your-qdrant-api-key" | base64
echo -n "your-surreal-password" | base64
echo -n "your-secret-key" | base64
echo -n "your-superuser-password" | base64

# Edit secrets.yaml and replace all <BASE64_ENCODED_*> values
nano k8s/base/secrets.yaml
```

**IMPORTANT:** Add `k8s/base/secrets.yaml` to `.gitignore`!

### 3. Install Prerequisites on Cluster

```bash
# Install Nginx Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/cloud/deploy.yaml

# Wait for ingress controller to be ready
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

# Install cert-manager for automatic SSL
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Wait for cert-manager to be ready
kubectl wait --namespace cert-manager \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/instance=cert-manager \
  --timeout=120s
```

### 4. Deploy the Application

```bash
# Create namespace and base resources
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/storage-class.yaml
kubectl apply -f k8s/base/configmap.yaml
kubectl apply -f k8s/base/secrets.yaml

# Create persistent volumes
kubectl apply -f k8s/base/postgres-pvc.yaml
kubectl apply -f k8s/base/neo4j-pvc.yaml
kubectl apply -f k8s/base/qdrant-pvc.yaml
kubectl apply -f k8s/base/surrealdb-pvc.yaml

# Deploy databases
kubectl apply -f k8s/databases/postgres.yaml
kubectl apply -f k8s/databases/neo4j.yaml
kubectl apply -f k8s/databases/qdrant.yaml
kubectl apply -f k8s/databases/surrealdb.yaml

# Wait for databases to be ready
kubectl wait --namespace cogmem \
  --for=condition=ready pod \
  --selector=app=postgres \
  --timeout=300s

# Run database migrations
kubectl apply -f k8s/services/prestart-job.yaml

# Wait for migration job to complete
kubectl wait --namespace cogmem \
  --for=condition=complete job/prestart-migration \
  --timeout=300s

# Deploy application services
kubectl apply -f k8s/services/backend.yaml
kubectl apply -f k8s/services/frontend.yaml
kubectl apply -f k8s/services/adminer.yaml

# Configure cert-manager
kubectl apply -f k8s/ingress/cert-manager.yaml

# Deploy ingress (this will trigger SSL certificate generation)
kubectl apply -f k8s/ingress/ingress.yaml
```

### 5. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n cogmem

# Check services
kubectl get svc -n cogmem

# Check ingress
kubectl get ingress -n cogmem

# Check certificate status
kubectl get certificate -n cogmem

# View logs
kubectl logs -n cogmem -l app=backend --tail=100
kubectl logs -n cogmem -l app=frontend --tail=100
```

## Building and Pushing Docker Images

### Option 1: GitHub Container Registry (Recommended)

```bash
# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Build and push backend
docker build -t ghcr.io/cogmemai/cogmem-backend:latest -f backend/Dockerfile .
docker push ghcr.io/cogmemai/cogmem-backend:latest

# Build and push frontend
docker build -t ghcr.io/cogmemai/cogmem-frontend:latest -f frontend/Dockerfile .
docker push ghcr.io/cogmemai/cogmem-frontend:latest
```

### Option 2: Rancher's Built-in Registry

```bash
# Access Rancher registry (usually at rancher-registry.yourdomain.com)
docker login rancher-registry.yourdomain.com

# Build and push
docker build -t rancher-registry.yourdomain.com/cogmem/backend:latest -f backend/Dockerfile .
docker push rancher-registry.yourdomain.com/cogmem/backend:latest

docker build -t rancher-registry.yourdomain.com/cogmem/frontend:latest -f frontend/Dockerfile .
docker push rancher-registry.yourdomain.com/cogmem/frontend:latest
```

## Updating the Application

```bash
# Build and push new images with a version tag
docker build -t ghcr.io/cogmemai/cogmem-backend:v1.0.1 -f backend/Dockerfile .
docker push ghcr.io/cogmemai/cogmem-backend:v1.0.1

# Update the deployment
kubectl set image deployment/backend backend=ghcr.io/cogmemai/cogmem-backend:v1.0.1 -n cogmem

# Or apply updated manifests
kubectl apply -f k8s/services/backend.yaml

# Watch rollout status
kubectl rollout status deployment/backend -n cogmem
```

## Scaling

```bash
# Scale backend
kubectl scale deployment backend --replicas=4 -n cogmem

# Scale frontend
kubectl scale deployment frontend --replicas=3 -n cogmem

# Auto-scaling (optional)
kubectl autoscale deployment backend --cpu-percent=70 --min=2 --max=10 -n cogmem
```

## Troubleshooting

### Pods not starting

```bash
# Describe pod to see events
kubectl describe pod <pod-name> -n cogmem

# Check logs
kubectl logs <pod-name> -n cogmem

# Check if secrets exist
kubectl get secrets -n cogmem
```

### Database connection issues

```bash
# Test database connectivity
kubectl run -it --rm debug --image=postgres:18 --restart=Never -n cogmem -- psql -h postgres-service -U postgres -d app

# Check service endpoints
kubectl get endpoints -n cogmem
```

### SSL certificate issues

```bash
# Check certificate status
kubectl describe certificate cogmem-tls -n cogmem

# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager

# Force certificate renewal
kubectl delete certificate cogmem-tls -n cogmem
kubectl apply -f k8s/ingress/ingress.yaml
```

### Ingress not working

```bash
# Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/component=controller

# Check ingress status
kubectl describe ingress cogmem-ingress -n cogmem

# Verify DNS is pointing to your server
dig api.yourdomain.com
```

## Backup and Restore

### Backup Databases

```bash
# PostgreSQL
kubectl exec -n cogmem postgres-<pod-id> -- pg_dump -U postgres app > backup-postgres.sql

# Neo4j
kubectl exec -n cogmem neo4j-<pod-id> -- neo4j-admin dump --to=/tmp/backup.dump
kubectl cp cogmem/neo4j-<pod-id>:/tmp/backup.dump ./backup-neo4j.dump
```

### Restore Databases

```bash
# PostgreSQL
kubectl exec -i -n cogmem postgres-<pod-id> -- psql -U postgres app < backup-postgres.sql

# Neo4j
kubectl cp ./backup-neo4j.dump cogmem/neo4j-<pod-id>:/tmp/backup.dump
kubectl exec -n cogmem neo4j-<pod-id> -- neo4j-admin load --from=/tmp/backup.dump
```

## Monitoring with Rancher

1. Open Rancher UI
2. Navigate to your cluster
3. Go to **Workloads** to see all deployments
4. Go to **Service Discovery** → **Ingresses** to manage ingress rules
5. Go to **Storage** → **Persistent Volumes** to manage storage
6. Use **kubectl Shell** in Rancher for quick access

## Differences from Docker Compose

| Docker Compose | Kubernetes |
|----------------|------------|
| `docker-compose up` | `kubectl apply -f k8s/` |
| `docker-compose down` | `kubectl delete -f k8s/` |
| `docker-compose logs` | `kubectl logs` |
| `docker-compose ps` | `kubectl get pods` |
| `.env` file | ConfigMaps + Secrets |
| `docker-compose restart` | `kubectl rollout restart` |
| Traefik labels | Ingress resources |
| Docker networks | Kubernetes Services |
| Docker volumes | PersistentVolumeClaims |

## Support

For issues or questions:
1. Check pod logs: `kubectl logs -n cogmem <pod-name>`
2. Check events: `kubectl get events -n cogmem --sort-by='.lastTimestamp'`
3. Use Rancher UI for visual debugging
4. Check this README for common troubleshooting steps

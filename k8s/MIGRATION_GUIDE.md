# Migration Guide: Docker Compose to Kubernetes

This guide helps you migrate your existing CogMem deployment from Docker Compose to Kubernetes/Rancher.

## Overview

You're transitioning from:
- **Docker Compose** with Traefik reverse proxy
- **Manual container management**
- **Docker volumes** for persistence

To:
- **Kubernetes** with Nginx Ingress
- **Declarative resource management**
- **PersistentVolumes** for data

## Pre-Migration Checklist

- [ ] Rancher and RKE2 installed (see [RANCHER_SETUP.md](./RANCHER_SETUP.md))
- [ ] kubectl configured and working
- [ ] DNS records configured for your domains
- [ ] Docker images built and pushed to a registry
- [ ] Backup of existing data (if needed)

## Step-by-Step Migration

### 1. Backup Existing Data (Optional)

If you have important data in your current Docker setup:

```bash
# On your server, backup Docker volumes
docker run --rm -v app-db-data:/data -v $(pwd):/backup ubuntu tar czf /backup/postgres-backup.tar.gz /data
docker run --rm -v neo4j-data:/data -v $(pwd):/backup ubuntu tar czf /backup/neo4j-backup.tar.gz /data
docker run --rm -v qdrant-data:/data -v $(pwd):/backup ubuntu tar czf /backup/qdrant-backup.tar.gz /data
docker run --rm -v surrealdb-data:/data -v $(pwd):/backup ubuntu tar czf /backup/surrealdb-backup.tar.gz /data

# Download backups to your local machine
scp user@server:/path/to/*-backup.tar.gz ./backups/
```

### 2. Build and Push Docker Images

Your Dockerfiles don't need changes! Just build and push to a registry.

#### Option A: GitHub Container Registry

```bash
# From your local machine (in the repo root)

# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin

# Build backend
docker build -t ghcr.io/YOUR_ORG/cogmem-backend:latest -f backend/Dockerfile .
docker push ghcr.io/YOUR_ORG/cogmem-backend:latest

# Build frontend  
docker build -t ghcr.io/YOUR_ORG/cogmem-frontend:latest \
  --build-arg VITE_API_URL=https://api.yourdomain.com \
  -f frontend/Dockerfile .
docker push ghcr.io/YOUR_ORG/cogmem-frontend:latest
```

#### Option B: Docker Hub

```bash
# Login to Docker Hub
docker login

# Build and push
docker build -t YOUR_USERNAME/cogmem-backend:latest -f backend/Dockerfile .
docker push YOUR_USERNAME/cogmem-backend:latest

docker build -t YOUR_USERNAME/cogmem-frontend:latest -f frontend/Dockerfile .
docker push YOUR_USERNAME/cogmem-frontend:latest
```

### 3. Configure Kubernetes Manifests

#### 3.1 Update ConfigMap

Edit `k8s/base/configmap.yaml`:

```yaml
DOMAIN: "yourdomain.com"  # Replace with your actual domain
FRONTEND_HOST: "https://dashboard.yourdomain.com"
BACKEND_CORS_ORIGINS: "https://dashboard.yourdomain.com,https://api.yourdomain.com"
FIRST_SUPERUSER: "admin@yourdomain.com"  # Your email
```

#### 3.2 Create Secrets

```bash
# Copy the template
cp k8s/base/secrets.yaml.template k8s/base/secrets.yaml

# Generate secrets (use your actual values from .env file)
echo -n "your-postgres-password" | base64
echo -n "your-neo4j-password" | base64
echo -n "your-qdrant-api-key" | base64
echo -n "your-surreal-password" | base64
echo -n "your-secret-key" | base64
echo -n "your-superuser-password" | base64

# Edit secrets.yaml and paste the base64 values
nano k8s/base/secrets.yaml
```

**IMPORTANT:** The secrets.yaml file is in .gitignore. Never commit it!

#### 3.3 Update Image References

Edit these files to use your registry:

**`k8s/services/backend.yaml`:**
```yaml
image: ghcr.io/YOUR_ORG/cogmem-backend:latest
```

**`k8s/services/frontend.yaml`:**
```yaml
image: ghcr.io/YOUR_ORG/cogmem-frontend:latest
```

**`k8s/services/prestart-job.yaml`:**
```yaml
image: ghcr.io/YOUR_ORG/cogmem-backend:latest
```

#### 3.4 Update Ingress Domains

Edit `k8s/ingress/ingress.yaml` and replace all `yourdomain.com` with your actual domain.

Edit `k8s/ingress/cert-manager.yaml` and update the email address for Let's Encrypt.

### 4. Deploy to Kubernetes

#### Option A: Using the Deploy Script (Recommended)

```bash
# From your local machine (in the repo root)
./k8s/deploy.sh
```

This script will:
1. Create namespace and base resources
2. Create persistent volumes
3. Deploy databases
4. Wait for PostgreSQL
5. Run migrations
6. Deploy application services
7. Configure ingress and SSL

#### Option B: Manual Deployment

```bash
# Prerequisites (one-time setup)
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/cloud/deploy.yaml
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Deploy application
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/storage-class.yaml
kubectl apply -f k8s/base/configmap.yaml
kubectl apply -f k8s/base/secrets.yaml
kubectl apply -f k8s/base/postgres-pvc.yaml
kubectl apply -f k8s/base/neo4j-pvc.yaml
kubectl apply -f k8s/base/qdrant-pvc.yaml
kubectl apply -f k8s/base/surrealdb-pvc.yaml
kubectl apply -f k8s/databases/
kubectl wait --namespace cogmem --for=condition=ready pod --selector=app=postgres --timeout=300s
kubectl apply -f k8s/services/prestart-job.yaml
kubectl wait --namespace cogmem --for=condition=complete job/prestart-migration --timeout=300s
kubectl apply -f k8s/services/
kubectl apply -f k8s/ingress/
```

### 5. Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n cogmem

# Check services
kubectl get svc -n cogmem

# Check ingress
kubectl get ingress -n cogmem

# Check certificates (may take 1-2 minutes to issue)
kubectl get certificate -n cogmem

# View backend logs
kubectl logs -n cogmem -l app=backend --tail=50

# View frontend logs
kubectl logs -n cogmem -l app=frontend --tail=50
```

### 6. Update DNS Records

Make sure your DNS records point to your server:

```
Type: A
Name: api
Value: your-server-ip

Type: A
Name: dashboard
Value: your-server-ip

Type: A
Name: neo4j
Value: your-server-ip

Type: A
Name: qdrant
Value: your-server-ip

Type: A
Name: surrealdb
Value: your-server-ip

Type: A
Name: adminer
Value: your-server-ip
```

Or use a wildcard:
```
Type: A
Name: *
Value: your-server-ip
```

### 7. Test Your Application

1. Open `https://dashboard.yourdomain.com` - should show your frontend
2. Open `https://api.yourdomain.com/docs` - should show API documentation
3. Open `https://neo4j.yourdomain.com` - should show Neo4j browser
4. Open `https://qdrant.yourdomain.com/dashboard` - should show Qdrant dashboard
5. Open `https://adminer.yourdomain.com` - should show Adminer

All should have valid SSL certificates (green padlock).

### 8. Restore Data (If Needed)

If you backed up data in Step 1:

```bash
# Copy backups to server
scp ./backups/*-backup.tar.gz user@server:/tmp/

# SSH into server
ssh user@server

# Get pod names
kubectl get pods -n cogmem

# Restore PostgreSQL
kubectl exec -i -n cogmem postgres-XXXXX -- tar xzf - -C / < /tmp/postgres-backup.tar.gz

# Restore Neo4j
kubectl exec -i -n cogmem neo4j-XXXXX -- tar xzf - -C / < /tmp/neo4j-backup.tar.gz

# Restart pods to pick up restored data
kubectl rollout restart deployment/postgres -n cogmem
kubectl rollout restart deployment/neo4j -n cogmem
```

### 9. Clean Up Old Docker Compose Setup

Once everything is working in Kubernetes:

```bash
# On your server
docker-compose -f compose.yml -f compose.traefik.yml down -v

# Optional: Remove old images
docker image prune -a
```

## Key Differences

### Environment Variables

**Docker Compose:**
```yaml
env_file:
  - .env
environment:
  - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

**Kubernetes:**
```yaml
envFrom:
  - configMapRef:
      name: cogmem-config
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: cogmem-secrets
        key: postgres-password
```

### Networking

**Docker Compose:**
- Services communicate via service names on Docker networks
- Traefik labels for routing

**Kubernetes:**
- Services communicate via Kubernetes Services (e.g., `postgres-service`)
- Ingress resources for routing

### Persistence

**Docker Compose:**
```yaml
volumes:
  - app-db-data:/var/lib/postgresql/data
```

**Kubernetes:**
```yaml
volumes:
  - name: postgres-storage
    persistentVolumeClaim:
      claimName: postgres-pvc
```

### Scaling

**Docker Compose:**
```bash
docker-compose up --scale backend=3
```

**Kubernetes:**
```bash
kubectl scale deployment backend --replicas=3 -n cogmem
```

## Common Issues and Solutions

### Pods stuck in "Pending"

```bash
# Check events
kubectl describe pod <pod-name> -n cogmem

# Common causes:
# - PersistentVolume not bound
# - Insufficient resources
# - Image pull errors
```

### SSL certificates not issuing

```bash
# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager

# Check certificate status
kubectl describe certificate cogmem-tls -n cogmem

# Common causes:
# - DNS not pointing to server
# - Port 80 not accessible (needed for HTTP-01 challenge)
# - Rate limit hit (use staging issuer first)
```

### Database connection errors

```bash
# Check if database pods are running
kubectl get pods -n cogmem

# Check database logs
kubectl logs -n cogmem postgres-XXXXX

# Test connectivity
kubectl run -it --rm debug --image=postgres:18 --restart=Never -n cogmem -- \
  psql -h postgres-service -U postgres -d app
```

### Image pull errors

```bash
# Check if you're logged into the registry
docker login ghcr.io

# For private registries, create an image pull secret
kubectl create secret docker-registry regcred \
  --docker-server=ghcr.io \
  --docker-username=YOUR_USERNAME \
  --docker-password=YOUR_TOKEN \
  -n cogmem

# Add to deployment:
# spec:
#   imagePullSecrets:
#   - name: regcred
```

## Rollback Plan

If something goes wrong and you need to rollback to Docker Compose:

```bash
# On your server
cd /path/to/cogmem

# Start Docker Compose
docker-compose -f compose.yml -f compose.traefik.yml up -d

# Your data should still be in Docker volumes if you didn't remove them
```

## Next Steps

- Set up monitoring with Rancher
- Configure automated backups
- Set up CI/CD for automatic deployments
- Configure horizontal pod autoscaling
- Set up log aggregation

## Support

If you encounter issues:

1. Check pod logs: `kubectl logs -n cogmem <pod-name>`
2. Check events: `kubectl get events -n cogmem --sort-by='.lastTimestamp'`
3. Use Rancher UI for visual debugging
4. Refer to [README.md](./README.md) for detailed troubleshooting

## Useful Commands

```bash
# Watch pod status
kubectl get pods -n cogmem -w

# Get all resources
kubectl get all -n cogmem

# Restart a deployment
kubectl rollout restart deployment/backend -n cogmem

# View recent events
kubectl get events -n cogmem --sort-by='.lastTimestamp' | tail -20

# Execute command in pod
kubectl exec -it -n cogmem backend-XXXXX -- bash

# Port forward for local testing
kubectl port-forward -n cogmem svc/backend-service 8000:8000
```

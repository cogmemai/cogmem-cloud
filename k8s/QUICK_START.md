# Quick Start Guide

Get your CogMem application running on Kubernetes in 5 steps.

## Prerequisites

- ✅ Rancher and RKE2 installed on your server
- ✅ kubectl configured (`kubectl get nodes` works)
- ✅ Docker images built and pushed to a registry

## 5-Step Deployment

### 1. Configure Your Settings

```bash
# Edit domain names
nano k8s/base/configmap.yaml
nano k8s/ingress/ingress.yaml
nano k8s/ingress/cert-manager.yaml

# Update Docker image URLs
nano k8s/services/backend.yaml
nano k8s/services/frontend.yaml
nano k8s/services/prestart-job.yaml
```

### 2. Create Secrets

```bash
# Copy template
cp k8s/base/secrets.yaml.template k8s/base/secrets.yaml

# Generate base64 secrets
echo -n "your-password" | base64

# Edit and fill in all secrets
nano k8s/base/secrets.yaml
```

### 3. Install Prerequisites (One-Time)

```bash
# Nginx Ingress Controller
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/cloud/deploy.yaml

# cert-manager for SSL
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Wait for them to be ready (2-3 minutes)
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=120s
kubectl wait --namespace cert-manager --for=condition=ready pod --selector=app.kubernetes.io/instance=cert-manager --timeout=120s
```

### 4. Deploy Application

```bash
# Run the deployment script
./k8s/deploy.sh

# Or manually:
# kubectl apply -f k8s/base/
# kubectl apply -f k8s/databases/
# kubectl apply -f k8s/services/
# kubectl apply -f k8s/ingress/
```

### 5. Verify

```bash
# Check pods
kubectl get pods -n cogmem

# Check ingress
kubectl get ingress -n cogmem

# Check certificates (may take 1-2 minutes)
kubectl get certificate -n cogmem

# View logs
kubectl logs -n cogmem -l app=backend --tail=50
```

## Access Your Application

- **Frontend:** https://dashboard.yourdomain.com
- **API Docs:** https://api.yourdomain.com/docs
- **Neo4j:** https://neo4j.yourdomain.com
- **Qdrant:** https://qdrant.yourdomain.com/dashboard
- **Adminer:** https://adminer.yourdomain.com

## Common Commands

```bash
# Update application
./k8s/update.sh --service backend --tag v1.0.1

# Scale services
kubectl scale deployment backend --replicas=4 -n cogmem

# View logs
kubectl logs -n cogmem -l app=backend -f

# Restart service
kubectl rollout restart deployment/backend -n cogmem

# Delete everything
./k8s/destroy.sh
```

## Troubleshooting

**Pods not starting?**
```bash
kubectl describe pod <pod-name> -n cogmem
kubectl logs <pod-name> -n cogmem
```

**SSL not working?**
```bash
kubectl describe certificate cogmem-tls -n cogmem
kubectl logs -n cert-manager -l app=cert-manager
```

**Need help?**
- See [README.md](./README.md) for detailed docs
- See [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) for migration help
- Use Rancher UI for visual debugging

## Next Steps

1. Set up automated backups
2. Configure monitoring in Rancher
3. Set up CI/CD pipeline
4. Configure auto-scaling
5. Review security settings

---

**Need more details?** Check out:
- [README.md](./README.md) - Full documentation
- [MIGRATION_GUIDE.md](./MIGRATION_GUIDE.md) - Migration from Docker Compose
- [RANCHER_SETUP.md](./RANCHER_SETUP.md) - Rancher installation

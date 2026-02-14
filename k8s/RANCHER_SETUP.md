# Rancher Installation Guide for OVH Bare Metal Server

This guide walks you through installing Rancher and RKE2 on your OVH bare metal server.

## Prerequisites

- OVH bare metal server with root/sudo access
- Ubuntu 20.04+ or similar Linux distribution
- At least 4GB RAM, 2 CPU cores
- Docker installed
- Domain name with DNS access

## Step 1: Clean Up Existing Docker Environment

**WARNING:** This will delete all existing containers, volumes, and data!

```bash
# SSH into your OVH server
ssh user@your-server-ip

# Stop all running containers
docker stop $(docker ps -aq)

# Remove all containers
docker rm $(docker ps -aq)

# Remove all volumes (THIS DELETES ALL DATA!)
docker volume rm $(docker volume ls -q)

# Remove all networks (except default ones)
docker network prune -f

# Optional: Remove all images to free up space
docker image prune -a -f

# Optional: Clean up everything
docker system prune -a --volumes -f
```

## Step 2: Install Rancher Server

Rancher runs as a Docker container and provides the management UI for Kubernetes.

```bash
# Create a directory for Rancher data
sudo mkdir -p /opt/rancher

# Run Rancher server with Let's Encrypt support
docker run -d --restart=unless-stopped \
  -p 80:80 -p 443:443 \
  -v /opt/rancher:/var/lib/rancher \
  --privileged \
  --name rancher \
  rancher/rancher:latest \
  --acme-domain rancher.yourdomain.com

# If you want to use IP instead of domain, omit the --acme-domain flag:
# docker run -d --restart=unless-stopped \
#   -p 80:80 -p 443:443 \
#   -v /opt/rancher:/var/lib/rancher \
#   --privileged \
#   --name rancher \
#   rancher/rancher:latest

# Wait for Rancher to start (takes 2-3 minutes)
docker logs -f rancher

# Get the bootstrap password
docker logs rancher 2>&1 | grep "Bootstrap Password:"
```

## Step 3: Configure DNS (Optional but Recommended)

If using a domain for Rancher:

1. Log into your DNS provider (OVH, Cloudflare, etc.)
2. Create an A record:
   - **Type:** A
   - **Name:** rancher
   - **Value:** your-server-ip
   - **TTL:** 300

3. Wait 5-10 minutes for DNS propagation
4. Verify: `dig rancher.yourdomain.com`

## Step 4: Access Rancher UI

1. Open browser to:
   - With domain: `https://rancher.yourdomain.com`
   - With IP: `https://your-server-ip`

2. Accept the self-signed certificate warning (if not using --acme-domain)

3. Enter the bootstrap password from Step 2

4. Set a new admin password (save this securely!)

5. Set the Rancher Server URL:
   - With domain: `https://rancher.yourdomain.com`
   - With IP: `https://your-server-ip`
   - You can change this later in **Global Settings** → **server-url**

## Step 5: Install RKE2 Kubernetes

RKE2 is Rancher's Kubernetes distribution, optimized for security and compliance.

```bash
# Install RKE2
curl -sfL https://get.rke2.io | sudo sh -

# Enable and start RKE2 server
sudo systemctl enable rke2-server.service
sudo systemctl start rke2-server.service

# Watch the logs to see when it's ready (takes 2-5 minutes)
sudo journalctl -u rke2-server -f
# Press Ctrl+C when you see "Node registered successfully" or logs stabilize

# Verify RKE2 is running
sudo systemctl status rke2-server
```

## Step 6: Configure kubectl Access

```bash
# Create kubectl config directory
mkdir -p ~/.kube

# Copy RKE2 kubeconfig
sudo cp /etc/rancher/rke2/rke2.yaml ~/.kube/config

# Set correct ownership
sudo chown $(id -u):$(id -g) ~/.kube/config

# Add RKE2 binaries to PATH
export PATH=$PATH:/var/lib/rancher/rke2/bin

# Make it permanent
echo 'export PATH=$PATH:/var/lib/rancher/rke2/bin' >> ~/.bashrc
echo 'export KUBECONFIG=~/.kube/config' >> ~/.bashrc

# Reload shell config
source ~/.bashrc

# Verify kubectl works
kubectl get nodes
```

You should see output like:
```
NAME        STATUS   ROLES                       AGE   VERSION
ns5034729   Ready    control-plane,etcd,worker   5m    v1.34.3+rke2r1
```

## Step 7: Import Cluster into Rancher

The RKE2 cluster should automatically register with Rancher since they're on the same server. To verify:

1. In Rancher UI, go to **Cluster Management**
2. You should see a cluster named "local" or your hostname
3. Click on it to explore

If the cluster doesn't appear:

```bash
# Get the cluster registration command from Rancher UI:
# 1. Click "Import Existing" in Cluster Management
# 2. Select "Generic"
# 3. Copy the kubectl command
# 4. Run it on your server

# Example (use the actual command from Rancher):
curl --insecure -sfL https://rancher.yourdomain.com/v3/import/xxx.yaml | kubectl apply -f -
```

## Step 8: Install Nginx Ingress Controller

```bash
# Install Nginx Ingress
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.0/deploy/static/provider/cloud/deploy.yaml

# Wait for it to be ready
kubectl wait --namespace ingress-nginx \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/component=controller \
  --timeout=120s

# Verify
kubectl get pods -n ingress-nginx
```

## Step 9: Install cert-manager for SSL

```bash
# Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Wait for it to be ready
kubectl wait --namespace cert-manager \
  --for=condition=ready pod \
  --selector=app.kubernetes.io/instance=cert-manager \
  --timeout=120s

# Verify
kubectl get pods -n cert-manager
```

## Verification Checklist

- [ ] Rancher UI accessible
- [ ] RKE2 cluster running (`kubectl get nodes` shows Ready)
- [ ] Cluster visible in Rancher UI
- [ ] Nginx Ingress Controller running
- [ ] cert-manager running
- [ ] DNS records configured (if using domains)

## Next Steps

Now you're ready to deploy your application! See the main [README.md](./README.md) for deployment instructions.

## Troubleshooting

### Rancher container won't start

```bash
# Check logs
docker logs rancher

# Check if ports are already in use
sudo netstat -tulpn | grep -E ':(80|443)'

# If ports are in use, stop conflicting services
sudo systemctl stop apache2  # or nginx, or whatever is using the ports
```

### RKE2 won't start

```bash
# Check logs
sudo journalctl -u rke2-server -n 100

# Check system resources
free -h
df -h

# Restart RKE2
sudo systemctl restart rke2-server
```

### kubectl command not found

```bash
# Make sure PATH is set
export PATH=$PATH:/var/lib/rancher/rke2/bin

# Or use full path
/var/lib/rancher/rke2/bin/kubectl get nodes
```

### Can't access Rancher UI

```bash
# Check if Rancher is running
docker ps | grep rancher

# Check if firewall is blocking ports
sudo ufw status
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Check DNS resolution
dig rancher.yourdomain.com
```

## Updating Rancher Server URL

If you started with an IP and want to switch to a domain:

1. Configure DNS first (Step 3)
2. In Rancher UI, click **☰** menu → **Global Settings**
3. Find **server-url**
4. Click **⋮** → **Edit**
5. Change to `https://rancher.yourdomain.com`
6. Click **Save**

## Security Recommendations

1. **Change default passwords** immediately
2. **Enable 2FA** in Rancher (User Settings → Security)
3. **Restrict Rancher access** with firewall rules or VPN
4. **Regular backups** of `/opt/rancher` directory
5. **Keep Rancher updated**: `docker pull rancher/rancher:latest && docker restart rancher`

## Backup Rancher

```bash
# Stop Rancher
docker stop rancher

# Backup data
sudo tar -czf rancher-backup-$(date +%Y%m%d).tar.gz /opt/rancher

# Start Rancher
docker start rancher
```

## Restore Rancher

```bash
# Stop and remove Rancher
docker stop rancher
docker rm rancher

# Restore backup
sudo tar -xzf rancher-backup-YYYYMMDD.tar.gz -C /

# Start Rancher
docker run -d --restart=unless-stopped \
  -p 80:80 -p 443:443 \
  -v /opt/rancher:/var/lib/rancher \
  --privileged \
  --name rancher \
  rancher/rancher:latest
```

## Support Resources

- Rancher Documentation: https://rancher.com/docs/
- RKE2 Documentation: https://docs.rke2.io/
- Rancher Forums: https://forums.rancher.com/
- Rancher Slack: https://slack.rancher.io/

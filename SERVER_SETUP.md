# OVH Bare Metal Server Setup Guide

Complete instructions for setting up a fresh OVH bare metal server with Docker, SSH, and firewall configuration.

## Prerequisites

- OVH bare metal server (Ubuntu 22.04 LTS recommended)
- Root or sudo access
- Local machine with SSH client

## Step 1: Initial Server Access

### 1.1 Connect to Your Server

```bash
# SSH into your OVH server using the credentials provided
ssh root@your-ovh-server-ip

# Or if you have a specific user
ssh jkane@your-ovh-server-ip
```

### 1.2 Update System

```bash
# Update package lists
sudo apt update

# Upgrade all packages
sudo apt upgrade -y

# Install essential tools
sudo apt install -y curl wget git vim htop net-tools
```

## Step 2: SSH Configuration (Skip if already set up)

Your SSH key should already be configured for the `jkane` user from initial server setup. Verify by connecting:

```bash
ssh jkane@your-ovh-server-ip
```

## Step 3: Firewall Configuration

### 3.1 Enable UFW (Uncomplicated Firewall)

```bash
# Enable UFW
sudo ufw enable

# Verify status
sudo ufw status
```

### 3.2 Configure Firewall Rules

```bash
# Allow SSH (do this FIRST to avoid lockout)
sudo ufw allow 22/tcp

# Allow HTTP
sudo ufw allow 80/tcp

# Allow HTTPS
sudo ufw allow 443/tcp

# Deny everything else by default (already set, but confirm)
sudo ufw default deny incoming
sudo ufw default allow outgoing

# View all rules
sudo ufw status verbose
```

### 3.3 Optional: Limit SSH Connections

```bash
# Rate limit SSH to prevent brute force
sudo ufw limit 22/tcp

# Verify
sudo ufw status verbose
```

## Step 4: Docker Installation

### 4.1 Install Docker

```bash
# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo \
  "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Update package lists
sudo apt update

# Install Docker
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Verify installation
docker --version
docker compose version
```

### 4.2 Configure Docker for Non-Root User

```bash
# Add jkane user to docker group
sudo usermod -aG docker jkane

# Apply group changes - IMPORTANT: You must logout and login for this to take effect
exit
# Then SSH back in

# Verify (should work without sudo)
docker ps
```

### 4.3 Enable Docker Service

```bash
# Enable Docker to start on boot
sudo systemctl enable docker

# Start Docker
sudo systemctl start docker

# Verify status
sudo systemctl status docker
```

### 4.4 Install Docker Compose (Standalone)

```bash
# Download latest Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# Make executable
sudo chmod +x /usr/local/bin/docker-compose

# Verify
docker-compose --version
```

## Step 5: Create Deployment Directory

**Perform this step as the jkane user:**

```bash
# Create deployment directory
sudo mkdir -p /opt/cogmem
sudo chown jkane:jkane /opt/cogmem

# Create data directories for persistence
mkdir -p /opt/cogmem/data/{postgres,neo4j,qdrant}

# Set proper permissions
chmod 755 /opt/cogmem/data/*

# Verify ownership and permissions
ls -la /opt/cogmem
```

**Expected output:**
```
drwxr-xr-x jkane jkane /opt/cogmem
drwxr-xr-x jkane jkane /opt/cogmem/data
drwxr-xr-x jkane jkane /opt/cogmem/data/postgres
drwxr-xr-x jkane jkane /opt/cogmem/data/neo4j
drwxr-xr-x jkane jkane /opt/cogmem/data/qdrant
```

## Step 6: Create Traefik Network

```bash
# Create the external Traefik network
docker network create traefik-public

# Verify
docker network ls | grep traefik-public
```

## Step 7: Install GitHub CLI (Optional but Recommended)

**On the OVH server (as root or with sudo):**

```bash
# Remove any existing gh repository entries
sudo rm -f /etc/apt/sources.list.d/github-cli.list

# Download and install GitHub CLI directly
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg

# Add repository with stable release (not noble-specific)
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null

sudo apt update
sudo apt install -y gh

# Verify installation
  gh --version
```

**Authenticate with GitHub:**

```bash
# As deploy user
gh auth login

# Follow the prompts:
# 1. Choose "GitHub.com"
# 2. Choose "HTTPS"
# 3. Choose "Paste an authentication token" or "Login with a web browser"
# 4. If using web browser, it will open a link - approve it
```

## Step 8: Clone Repository

**On the OVH server (as jkane user):**

```bash
# Navigate to deployment directory
cd /opt/cogmem

# Initialize git and pull from GitHub
git init
git remote add origin https://github.com/cogmemai/cogmem.git
git fetch origin main
git checkout -b main origin/main

# Verify structure
ls -la
```

**Note:** With `gh` authenticated, you can use HTTPS without SSH keys. Git will automatically use your GitHub credentials.

## Step 8: Configure Environment Variables

```bash
# Create .env file
nano .env

# Add all required variables (see DEPLOYMENT_CICD.md for full list)
# Example:
DOMAIN=your-domain.com
FRONTEND_HOST=https://dashboard.your-domain.com
ENVIRONMENT=production
SECRET_KEY=your-secret-key
POSTGRES_PASSWORD=your-postgres-password
NEO4J_PASSWORD=your-neo4j-password
QDRANT_API_KEY=your-qdrant-api-key
# ... (add all other variables)

# Set proper permissions
chmod 600 .env
```

## Step 9: Test Docker Compose

```bash
# Navigate to deployment directory
cd /opt/cogmem

# Test the configuration (don't start yet)
docker compose -f compose.yml config

# If no errors, you're ready to deploy
```

## Step 10: Set Up Systemd Service (Optional but Recommended)

```bash
# Copy systemd service file
sudo cp scripts/cogmem.service /etc/systemd/system/

# Edit the service file if needed
sudo nano /etc/systemd/system/cogmem.service

# Reload systemd daemon
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable cogmem.service

# Start the service
sudo systemctl start cogmem.service

# Check status
sudo systemctl status cogmem.service
```

## Step 11: Verify Server Setup

```bash
# Check Docker is running
docker ps

# Check Traefik network exists
docker network ls

# Check firewall rules
sudo ufw status verbose

# Check SSH key authentication works
# (from local machine)
ssh -i ~/.ssh/cogmem_deploy deploy@your-ovh-server-ip "echo 'SSH works!'"
```

## Step 12: Set Up Log Rotation (Optional)

```bash
# Create log rotation config
sudo nano /etc/logrotate.d/cogmem

# Add this content:
/opt/cogmem/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 deploy deploy
    sharedscripts
}
```

## Troubleshooting

### SSH Connection Issues

```bash
# Check SSH service status
sudo systemctl status ssh

# Check SSH logs
sudo tail -f /var/log/auth.log

# Verify SSH config syntax
sudo sshd -t
```

### Docker Permission Issues

```bash
# Verify docker group membership
groups deploy

# If not in docker group, add again:
sudo usermod -aG docker deploy

# Then logout and login
```

### Firewall Blocking Connections

```bash
# Check firewall status
sudo ufw status verbose

# If ports are blocked, add them:
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp

# Reload firewall
sudo ufw reload
```

### Docker Daemon Issues

```bash
# Check Docker status
sudo systemctl status docker

# View Docker logs
sudo journalctl -u docker -f

# Restart Docker
sudo systemctl restart docker
```

## Security Checklist

- [ ] SSH password authentication disabled
- [ ] Root login disabled
- [ ] SSH key-based authentication enabled
- [ ] Firewall enabled and configured
- [ ] Only necessary ports open (22, 80, 443)
- [ ] Docker user permissions configured
- [ ] `.env` file has restricted permissions (600)
- [ ] Regular system updates scheduled
- [ ] Backups configured

## Next Steps

Once server setup is complete:

1. Return to `DEPLOYMENT_CICD.md`
2. Add GitHub secrets
3. Push to main branch to trigger first deployment
4. Monitor logs: `docker compose logs -f`

## Useful Commands for Daily Operations

```bash
# SSH into server
ssh cogmem-deploy

# View running containers
docker ps

# View all containers (including stopped)
docker ps -a

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Stop all services
docker compose down

# Start all services
docker compose up -d

# Restart specific service
docker compose restart backend

# Update and redeploy
cd /opt/cogmem
git pull origin main
docker compose pull
docker compose up -d

# Check disk usage
df -h

# Check Docker disk usage
docker system df
```

## Support

For issues specific to:
- **OVH**: Contact OVH support or check their documentation
- **Docker**: See https://docs.docker.com/
- **Ubuntu**: See https://ubuntu.com/support
- **This project**: Check DEPLOYMENT_CICD.md or project README

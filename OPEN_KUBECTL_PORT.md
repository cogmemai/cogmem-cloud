# Open Kubernetes API Port for Remote Access

## Option 1: Using UFW (Ubuntu Firewall)
 (on local machine get your local ip)curl ifconfig.me

SSH to your server and run:

```bash
ssh jkane@148.113.224.191

# Check if UFW is active
sudo ufw status

# Allow port 6443 from your IP only (more secure)
sudo ufw allow from YOUR_LOCAL_IP to any port 6443

# Or allow from anywhere (less secure, but simpler)
sudo ufw allow 6443/tcp

# Reload UFW
sudo ufw reload

# Verify
sudo ufw status numbered
```

## Option 2: Using iptables

```bash
ssh jkane@148.113.224.191

# Allow port 6443
sudo iptables -A INPUT -p tcp --dport 6443 -j ACCEPT

# Save the rule (Ubuntu/Debian)
sudo netfilter-persistent save

# Or on CentOS/RHEL
sudo service iptables save
```

## Option 3: OVH Firewall (if enabled)

1. Log into OVH Control Panel
2. Go to your server
3. Click **Network** → **Firewall**
4. Add a rule:
   - Protocol: TCP
   - Port: 6443
   - Source: Your IP or 0.0.0.0/0 (anywhere)
   - Action: Allow

## After Opening the Port

Test the connection from your Mac:

```bash
# Test if port is open
nc -zv 148.113.224.191 6443

# Should show: Connection to 148.113.224.191 port 6443 [tcp/*] succeeded!
```

Then try kubectl:

```bash
export KUBECONFIG=~/.kube/config-cogmem
kubectl get nodes
```

## Security Recommendation

**Best practice:** Only allow your specific IP address:

```bash
# Find your public IP
curl ifconfig.me

# Allow only your IP (replace with your actual IP)
sudo ufw allow from YOUR_IP to any port 6443
```

This prevents unauthorized access to your Kubernetes API.

## Alternative: Use kubectl Port Forward via SSH

If you don't want to open the port, you can use SSH tunneling:

```bash
# Create SSH tunnel
ssh -L 6443:localhost:6443 jkane@148.113.224.191

# In another terminal, use kubectl
export KUBECONFIG=~/.kube/config-cogmem
# Edit config to use localhost instead of server IP
sed -i.bak 's/148.113.224.191/127.0.0.1/g' ~/.kube/config-cogmem
kubectl get nodes
```

This is more secure as it doesn't expose the Kubernetes API publicly.

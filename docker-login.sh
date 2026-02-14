#!/bin/bash

# GitHub Container Registry Login Script
# Usage: ./docker-login.sh YOUR_GITHUB_TOKEN

if [ -z "$1" ]; then
    echo "Usage: ./docker-login.sh YOUR_GITHUB_TOKEN"
    echo ""
    echo "Example:"
    echo "  ./docker-login.sh ghp_xxxxxxxxxxxxxxxxxxxx"
    exit 1
fi

TOKEN=$1

echo "$TOKEN" | docker login ghcr.io -u cogmemai --password-stdin

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Successfully logged into GitHub Container Registry"
    echo ""
    echo "You can now build and push images:"
    echo "  docker build -t ghcr.io/cogmemai/cogmem-backend:latest -f backend/Dockerfile ."
    echo "  docker push ghcr.io/cogmemai/cogmem-backend:latest"
else
    echo ""
    echo "✗ Login failed. Please check your token."
fi

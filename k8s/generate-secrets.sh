#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Generating random secrets and creating secrets.yaml${NC}"
echo ""

# Generate random passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
NEO4J_PASSWORD=$(openssl rand -base64 32)
QDRANT_API_KEY=$(openssl rand -base64 32)
SURREAL_PASSWORD=$(openssl rand -base64 32)
SECRET_KEY=$(openssl rand -base64 32)
SUPERUSER_PASSWORD=$(openssl rand -base64 32)

# Base64 encode them
POSTGRES_PASSWORD_B64=$(echo -n "$POSTGRES_PASSWORD" | base64)
NEO4J_PASSWORD_B64=$(echo -n "$NEO4J_PASSWORD" | base64)
QDRANT_API_KEY_B64=$(echo -n "$QDRANT_API_KEY" | base64)
SURREAL_PASSWORD_B64=$(echo -n "$SURREAL_PASSWORD" | base64)
SECRET_KEY_B64=$(echo -n "$SECRET_KEY" | base64)
SUPERUSER_PASSWORD_B64=$(echo -n "$SUPERUSER_PASSWORD" | base64)

# Create secrets.yaml
cat > k8s/base/secrets.yaml <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: cogmem-secrets
  namespace: cogmem
type: Opaque
data:
  # Database passwords (base64 encoded)
  postgres-password: ${POSTGRES_PASSWORD_B64}
  neo4j-password: ${NEO4J_PASSWORD_B64}
  qdrant-api-key: ${QDRANT_API_KEY_B64}
  surreal-password: ${SURREAL_PASSWORD_B64}
  
  # Application secrets (base64 encoded)
  secret-key: ${SECRET_KEY_B64}
  first-superuser-password: ${SUPERUSER_PASSWORD_B64}
  
  # SMTP (base64 encoded, optional - empty for now)
  smtp-password: ""
  
  # Sentry DSN (base64 encoded, optional - empty for now)
  sentry-dsn: ""
EOF

echo -e "${GREEN}✓ secrets.yaml created with randomly generated passwords${NC}"
echo ""
echo -e "${YELLOW}IMPORTANT: Save these decoded passwords somewhere safe!${NC}"
echo ""
echo "PostgreSQL Password: $POSTGRES_PASSWORD"
echo "Neo4j Password: $NEO4J_PASSWORD"
echo "Qdrant API Key: $QDRANT_API_KEY"
echo "SurrealDB Password: $SURREAL_PASSWORD"
echo "Secret Key: $SECRET_KEY"
echo "Superuser Password: $SUPERUSER_PASSWORD"
echo ""
echo -e "${YELLOW}You can also decode them later from secrets.yaml:${NC}"
echo "  echo 'BASE64_STRING' | base64 -d"
echo ""

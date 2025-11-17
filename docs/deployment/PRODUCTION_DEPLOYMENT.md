# Production Deployment Guide

Complete guide for deploying the ReAct Agent Memory System to production environments.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Database Configuration](#database-configuration)
4. [Application Deployment](#application-deployment)
5. [Monitoring & Observability](#monitoring--observability)
6. [Security Best Practices](#security-best-practices)
7. [Scaling Strategies](#scaling-strategies)
8. [Backup & Recovery](#backup--recovery)

---

## Prerequisites

### Infrastructure Requirements

- **Python 3.8+** on production servers
- **PostgreSQL 15+** (managed service recommended)
- **SSL/TLS certificates** for secure connections
- **Load balancer** (for multi-instance deployment)
- **Container orchestration** (Docker, Kubernetes) - optional but recommended

### Minimum Resource Requirements

**Single Instance:**
- CPU: 2 cores
- RAM: 4GB
- Storage: 20GB SSD
- Network: 100Mbps

**Production Scale (per instance):**
- CPU: 4+ cores
- RAM: 8GB+
- Storage: 50GB+ SSD
- Network: 1Gbps

---

## Environment Setup

### 1. Virtual Environment

```bash
# Create production virtual environment
python3 -m venv /opt/react-agent/.venv

# Activate
source /opt/react-agent/.venv/bin/activate

# Install production dependencies
pip install -r requirements.txt --no-cache-dir

# Verify installation
pip list | grep langgraph
```

### 2. Environment Variables

**Production `.env` file:**

```bash
# Application
APP_ENV=production
APP_NAME=react-agent-memory
LOG_LEVEL=INFO

# OpenAI Configuration
OPENAI_API_KEY=<your-production-api-key>
OPENAI_API_BASE=https://api.openai.com/v1
LLM_MODEL=openai:gpt-4-turbo

# Database - Use connection pooling
DATABASE_URL=postgresql://user:password@prod-db-host:5432/react_agent
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30

# Redis (for distributed caching) - Optional
REDIS_URL=redis://prod-redis-host:6379/0

# Monitoring
SENTRY_DSN=<your-sentry-dsn>
PROMETHEUS_PORT=9090

# Security
SECRET_KEY=<generate-strong-secret-key>
ALLOWED_HOSTS=api.yourdomain.com,app.yourdomain.com
CORS_ORIGINS=https://yourdomain.com

# Rate Limiting
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000
```

### 3. System Service Configuration

**Create systemd service** (`/etc/systemd/system/react-agent.service`):

```ini
[Unit]
Description=ReAct Agent Memory Service
After=network.target postgresql.service

[Service]
Type=simple
User=react-agent
Group=react-agent
WorkingDirectory=/opt/react-agent
Environment="PATH=/opt/react-agent/.venv/bin"
EnvironmentFile=/opt/react-agent/.env
ExecStart=/opt/react-agent/.venv/bin/python /opt/react-agent/main.py
Restart=on-failure
RestartSec=5s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**Enable and start:**

```bash
sudo systemctl daemon-reload
sudo systemctl enable react-agent
sudo systemctl start react-agent
sudo systemctl status react-agent
```

---

## Database Configuration

### 1. Managed PostgreSQL Setup

#### AWS RDS

```bash
# Create RDS instance
aws rds create-db-instance \
    --db-instance-identifier react-agent-prod \
    --db-instance-class db.t3.medium \
    --engine postgres \
    --engine-version 15.4 \
    --allocated-storage 100 \
    --storage-type gp3 \
    --master-username postgres \
    --master-user-password <secure-password> \
    --backup-retention-period 7 \
    --preferred-backup-window "03:00-04:00" \
    --preferred-maintenance-window "mon:04:00-mon:05:00" \
    --storage-encrypted \
    --enable-performance-insights \
    --publicly-accessible false
```

#### Google Cloud SQL

```bash
gcloud sql instances create react-agent-prod \
    --database-version=POSTGRES_15 \
    --tier=db-custom-2-7680 \
    --region=us-central1 \
    --backup-start-time=03:00 \
    --enable-bin-log \
    --storage-auto-increase \
    --storage-size=100GB
```

### 2. Database Initialization

```python
# production_setup.py
import asyncio
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres import AsyncPostgresStore
import os

async def setup_production_database():
    """Initialize production database schema"""

    db_uri = os.getenv("DATABASE_URL")

    print("Setting up production database...")

    async with (
        AsyncPostgresSaver.from_conn_string(db_uri) as checkpointer,
        AsyncPostgresStore.from_conn_string(db_uri) as store
    ):
        await checkpointer.setup()
        print("✓ Checkpointer tables created")

        await store.setup()
        print("✓ Store tables created")

    print("✓ Database setup complete!")

if __name__ == "__main__":
    asyncio.run(setup_production_database())
```

### 3. Database Optimization

**PostgreSQL Configuration** (`postgresql.conf`):

```ini
# Connection Settings
max_connections = 200
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 10MB
min_wal_size = 1GB
max_wal_size = 4GB

# Logging
log_destination = 'stderr'
logging_collector = on
log_directory = 'log'
log_filename = 'postgresql-%Y-%m-%d_%H%M%S.log'
log_rotation_age = 1d
log_rotation_size = 100MB
log_min_duration_statement = 1000  # Log slow queries
log_line_prefix = '%t [%p]: [%l-1] user=%u,db=%d,app=%a,client=%h '
```

**Create Indexes:**

```sql
-- Optimize checkpoint queries
CREATE INDEX CONCURRENTLY idx_checkpoints_thread_timestamp
ON checkpoints(thread_id, (checkpoint->>'ts') DESC);

-- Optimize store searches
CREATE INDEX CONCURRENTLY idx_store_prefix_pattern
ON store USING gin(to_tsvector('english', value::text));

-- Add partitioning for large tables
CREATE TABLE checkpoints_2025_01 PARTITION OF checkpoints
FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

---

## Application Deployment

### 1. Docker Deployment

**Dockerfile:**

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python healthcheck.py || exit 1

# Run application
CMD ["python", "main.py"]
```

**docker-compose.prod.yml:**

```yaml
version: '3.8'

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env.production
    restart: unless-stopped
    depends_on:
      - postgres
      - redis
    networks:
      - app-network
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G

  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: react_agent
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app-network
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data
    networks:
      - app-network
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - app
    networks:
      - app-network
    restart: unless-stopped

networks:
  app-network:
    driver: bridge

volumes:
  postgres_data:
  redis_data:
```

### 2. Kubernetes Deployment

**deployment.yaml:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: react-agent
  namespace: production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: react-agent
  template:
    metadata:
      labels:
        app: react-agent
    spec:
      containers:
      - name: react-agent
        image: your-registry/react-agent:1.0.0
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: react-agent-secrets
              key: database-url
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: react-agent-secrets
              key: openai-api-key
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

---

## Monitoring & Observability

### 1. Application Metrics

**metrics.py:**

```python
from prometheus_client import Counter, Histogram, Gauge
import time

# Define metrics
agent_requests = Counter('agent_requests_total', 'Total agent requests')
agent_errors = Counter('agent_errors_total', 'Total agent errors')
agent_duration = Histogram('agent_duration_seconds', 'Agent processing time')
active_threads = Gauge('active_threads', 'Number of active conversation threads')
memory_operations = Counter('memory_operations_total', 'Total memory operations', ['operation', 'type'])

# Usage in code
@agent_duration.time()
async def process_request(message):
    agent_requests.inc()
    try:
        result = await agent.ainvoke(message)
        memory_operations.labels(operation='read', type='short_term').inc()
        return result
    except Exception as e:
        agent_errors.inc()
        raise
```

### 2. Logging Configuration

**logging_config.py:**

```python
import logging
import json
from pythonjsonlogger import jsonlogger

def setup_production_logging():
    """Configure structured JSON logging for production"""

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(message)s',
        timestamp=True
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

# Usage
logger = setup_production_logging()
logger.info("Agent processing started", extra={
    "thread_id": thread_id,
    "user_id": user_id,
    "action": "agent_invoke"
})
```

### 3. Error Tracking with Sentry

```python
import sentry_sdk
from sentry_sdk.integrations.asyncio import AsyncioIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    environment="production",
    traces_sample_rate=0.1,
    integrations=[AsyncioIntegration()],
    before_send=lambda event, hint: event if should_send_to_sentry(event) else None
)
```

---

## Security Best Practices

### 1. API Key Management

```python
# Use AWS Secrets Manager
import boto3
import json

def get_secret(secret_name):
    """Retrieve secrets from AWS Secrets Manager"""
    client = boto3.client('secretsmanager', region_name='us-east-1')
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response['SecretString'])

# Usage
secrets = get_secret('react-agent/production')
api_key = secrets['OPENAI_API_KEY']
```

### 2. Input Validation

```python
from pydantic import BaseModel, validator
from typing import Optional

class AgentRequest(BaseModel):
    message: str
    thread_id: str
    user_id: str
    metadata: Optional[dict] = None

    @validator('message')
    def message_length(cls, v):
        if len(v) > 10000:
            raise ValueError('Message too long')
        return v

    @validator('thread_id', 'user_id')
    def validate_ids(cls, v):
        if not v.isalnum():
            raise ValueError('Invalid ID format')
        return v
```

### 3. Rate Limiting

```python
from redis import Redis
from datetime import datetime, timedelta

redis_client = Redis.from_url(os.getenv('REDIS_URL'))

async def check_rate_limit(user_id: str, limit: int = 60) -> bool:
    """Check if user has exceeded rate limit"""
    key = f"rate_limit:{user_id}:{datetime.now().strftime('%Y%m%d%H%M')}"
    current = redis_client.incr(key)

    if current == 1:
        redis_client.expire(key, 60)

    return current <= limit
```

---

## Scaling Strategies

### 1. Horizontal Scaling

```bash
# Scale application instances
docker-compose up --scale app=5

# Kubernetes scaling
kubectl scale deployment react-agent --replicas=10 -n production
```

### 2. Database Connection Pooling

```python
from psycopg_pool import AsyncConnectionPool

# Create connection pool
pool = AsyncConnectionPool(
    conninfo=os.getenv("DATABASE_URL"),
    min_size=5,
    max_size=20,
    timeout=30,
    max_idle=300,
    max_lifetime=3600
)

# Usage
async with pool.connection() as conn:
    # Use connection
    pass
```

### 3. Caching Strategy

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def get_cached_memory(user_id: str, cache_key: str):
    """Cache frequently accessed memories"""
    # Implementation
    pass
```

---

## Backup & Recovery

### 1. Database Backups

```bash
#!/bin/bash
# backup.sh - Daily backup script

BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="react_agent"

# Create backup
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME \
    -F custom -b -v \
    -f "${BACKUP_DIR}/backup_${DATE}.dump"

# Upload to S3
aws s3 cp "${BACKUP_DIR}/backup_${DATE}.dump" \
    "s3://your-backups/postgres/${DATE}/"

# Cleanup old backups (keep last 30 days)
find "$BACKUP_DIR" -name "backup_*.dump" -mtime +30 -delete
```

### 2. Disaster Recovery

```bash
# Restore from backup
pg_restore -h $DB_HOST -U $DB_USER -d $DB_NAME \
    -v backup_20250111_120000.dump

# Point-in-time recovery (PITR)
aws rds restore-db-instance-to-point-in-time \
    --source-db-instance-identifier react-agent-prod \
    --target-db-instance-identifier react-agent-restored \
    --restore-time 2025-01-11T12:00:00Z
```

---

## Performance Tuning Checklist

- [ ] Enable PostgreSQL query performance insights
- [ ] Configure connection pooling (20-50 connections per instance)
- [ ] Implement Redis caching for frequently accessed data
- [ ] Use CDN for static assets
- [ ] Enable gzip compression
- [ ] Optimize database indexes
- [ ] Monitor slow queries (>1s)
- [ ] Implement circuit breakers for external API calls
- [ ] Use async/await throughout the application
- [ ] Enable HTTP/2 on load balancer

---

## Deployment Checklist

- [ ] All environment variables configured
- [ ] Database initialized and migrated
- [ ] SSL/TLS certificates installed
- [ ] Monitoring and alerting configured
- [ ] Backup strategy implemented
- [ ] Load testing completed
- [ ] Security audit performed
- [ ] Documentation updated
- [ ] Rollback plan documented
- [ ] On-call rotation established

---

**Last Updated**: 2025-01-11

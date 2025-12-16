# Deployment Guide

This guide covers deploying SigmaPilot Lens in various environments.

---

## Prerequisites

- Docker 24.0+ and Docker Compose 2.20+
- PostgreSQL 15+ (if not using container)
- Redis 7+ (if not using container)
- API keys for AI providers (OpenAI, Google AI)

---

## Quick Start (Docker Compose)

### 1. Clone and Configure

```bash
git clone https://github.com/fzheng/SigmaPilot-Lens.git
cd SigmaPilot-Lens

# Copy environment template
cp .env.example .env
```

### 2. Edit Environment Variables

Edit `.env` with your configuration:

```bash
# Set AI model API keys
MODEL_CHATGPT_API_KEY=sk-your-openai-key
MODEL_GEMINI_API_KEY=your-google-ai-key

# Database password (optional, defaults to 'lens')
DB_PASSWORD=your-secure-db-password
```

**Note**: SigmaPilot Lens uses network-level security. No API keys are required for authentication - all services are isolated within the Docker network.

### 3. Start Services

```bash
# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

### 4. Initialize Database

```bash
# Run migrations
docker-compose exec gateway alembic upgrade head
```

### 5. Verify Installation

```bash
# Health check
curl http://localhost:8000/health

# Readiness check
curl http://localhost:8000/ready
```

---

## Service Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Compose                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   gateway   │  │   worker    │  │  publisher  │         │
│  │   :8000     │  │             │  │   :8001     │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          │                                  │
│         ┌────────────────┼────────────────┐                 │
│         │                │                │                 │
│  ┌──────▼──────┐  ┌──────▼──────┐                          │
│  │    redis    │  │  postgres   │                          │
│  │    :6379    │  │    :5432    │                          │
│  └─────────────┘  └─────────────┘                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Docker Compose Configuration

### Production Configuration

**docker-compose.yml**:

```yaml
version: '3.8'

services:
  gateway:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: lens-gateway
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://lens:${DB_PASSWORD}@postgres:5432/lens
      - REDIS_URL=redis://redis:6379
      - LOG_LEVEL=INFO
      - LOG_FORMAT=json
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 10s
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 512M

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: lens-worker
    restart: unless-stopped
    command: python -m src.workers.main
    environment:
      - DATABASE_URL=postgresql://lens:${DB_PASSWORD}@postgres:5432/lens
      - REDIS_URL=redis://redis:6379
      - FEATURE_PROFILE=${FEATURE_PROFILE:-trend_follow_v1}
      - AI_MODELS=${AI_MODELS:-chatgpt,gemini}
      - MODEL_CHATGPT_API_KEY=${MODEL_CHATGPT_API_KEY}
      - MODEL_GEMINI_API_KEY=${MODEL_GEMINI_API_KEY}
      - LOG_LEVEL=INFO
      - LOG_FORMAT=json
    depends_on:
      redis:
        condition: service_healthy
      postgres:
        condition: service_healthy
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G

  redis:
    image: redis:7-alpine
    container_name: lens-redis
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:15-alpine
    container_name: lens-postgres
    restart: unless-stopped
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=lens
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=lens
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lens"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  redis_data:
  postgres_data:
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 lens && chown -R lens:lens /app
USER lens

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Environment Variables

Create a `.env` file with production values:

```bash
# Database
DB_PASSWORD=your-secure-db-password

# AI Models
AI_MODELS=chatgpt,gemini,claude,deepseek
MODEL_CHATGPT_API_KEY=sk-your-openai-key
MODEL_GEMINI_API_KEY=your-google-ai-key
MODEL_CLAUDE_API_KEY=sk-ant-your-anthropic-key
MODEL_DEEPSEEK_API_KEY=your-deepseek-key

# Feature Profile
FEATURE_PROFILE=trend_follow_v1
```

**Note**: Network-level security is used instead of API keys. The API is only accessible from within the Docker network.

---

## Scaling

### Horizontal Scaling (Workers)

Workers use Redis consumer groups for distributed processing:

```yaml
# docker-compose.scale.yml
services:
  worker:
    deploy:
      replicas: 3
```

```bash
docker-compose -f docker-compose.yml -f docker-compose.scale.yml up -d
```

### Vertical Scaling

Adjust resource limits in docker-compose.yml:

```yaml
services:
  worker:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 2G
```

---

## Database Migrations

### Run Migrations

```bash
# Inside container
docker-compose exec gateway alembic upgrade head

# Or from host (if DATABASE_URL is set)
alembic upgrade head
```

### Create New Migration

```bash
docker-compose exec gateway alembic revision --autogenerate -m "description"
```

### Rollback Migration

```bash
docker-compose exec gateway alembic downgrade -1
```

---

## Backup and Recovery

### PostgreSQL Backup

```bash
# Backup
docker-compose exec postgres pg_dump -U lens lens > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20240115.sql | docker-compose exec -T postgres psql -U lens lens
```

### Redis Backup

Redis with AOF persistence backs up automatically. For manual backup:

```bash
docker-compose exec redis redis-cli BGSAVE
docker cp lens-redis:/data/dump.rdb ./redis_backup.rdb
```

---

## Monitoring

### Prometheus Integration

Add Prometheus to your stack:

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
```

**prometheus.yml**:
```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'lens-gateway'
    static_configs:
      - targets: ['gateway:8000']
    metrics_path: '/metrics'
```

### Log Aggregation

Logs are output in JSON format by default. Configure your log aggregator to collect from Docker:

```bash
# View logs with timestamps
docker-compose logs -f --timestamps

# Follow specific service
docker-compose logs -f gateway
```

---

## Security Checklist

### Pre-Deployment

- [ ] Change default database password
- [ ] Secure AI provider API keys
- [ ] Review rate limiting settings
- [ ] Ensure docker-compose.override.yml is NOT used in production

### Network Security

- [ ] Verify no ports are exposed externally (production)
- [ ] Use internal Docker network for all services
- [ ] Configure firewall rules
- [ ] Consider VPN for accessing the Docker network

### Runtime Security

- [ ] Run containers as non-root user
- [ ] Set resource limits
- [ ] Enable read-only filesystem where possible
- [ ] Scan images for vulnerabilities

---

## Reverse Proxy (Nginx)

Example Nginx configuration for HTTPS:

```nginx
upstream lens_gateway {
    server localhost:8000;
}

server {
    listen 443 ssl http2;
    server_name lens.yourdomain.com;

    ssl_certificate /etc/ssl/certs/lens.crt;
    ssl_certificate_key /etc/ssl/private/lens.key;

    location / {
        proxy_pass http://lens_gateway;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws/ {
        proxy_pass http://lens_gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

---

## Troubleshooting

### Common Issues

**Container won't start**:
```bash
# Check logs
docker-compose logs gateway

# Check environment variables
docker-compose config
```

**Database connection failed**:
```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Check connectivity
docker-compose exec gateway python -c "from src.models.database import engine; print(engine.connect())"
```

**Redis connection failed**:
```bash
# Verify Redis is running
docker-compose exec redis redis-cli ping
```

**AI model errors**:
```bash
# Check API key is set
docker-compose exec worker env | grep MODEL_

# Test API connectivity
curl -H "Authorization: Bearer $MODEL_CHATGPT_API_KEY" https://api.openai.com/v1/models
```

### Performance Tuning

**High latency**:
- Increase worker count
- Check AI model timeout settings
- Review queue depth metrics

**Memory issues**:
- Adjust Redis maxmemory
- Increase container memory limits
- Review connection pool sizes

---

## Kubernetes Deployment

For Kubernetes deployment, convert docker-compose to K8s manifests:

```bash
# Using kompose
kompose convert -f docker-compose.yml -o k8s/
```

See [Kubernetes Guide](./kubernetes.md) for detailed K8s deployment instructions (future document).

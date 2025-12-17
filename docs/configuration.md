# Configuration Guide

This document describes all configuration options for SigmaPilot Lens.

## Environment Variables

### Core Application

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `APP_NAME` | Application name | `SigmaPilot Lens` | No |
| `DEBUG` | Enable debug mode | `false` | No |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARN, ERROR) | `INFO` | No |
| `LOG_FORMAT` | Log format (json, text) | `json` | No |

### Database

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string | - | **Yes** |
| `DB_POOL_SIZE` | Connection pool size | `5` | No |
| `DB_MAX_OVERFLOW` | Max overflow connections | `10` | No |
| `RETENTION_DAYS` | Data retention period in days | `180` | No |

**Example**:
```
DATABASE_URL=postgresql://lens:password@localhost:5432/lens
```

### Redis

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` | No |
| `REDIS_MAX_CONNECTIONS` | Max Redis connections | `10` | No |

**Example**:
```
REDIS_URL=redis://:password@localhost:6379/0
```

### Security

SigmaPilot Lens uses **network-level security** instead of API keys:

- All services are isolated within the Docker network (`lens-network`)
- No ports are exposed to the host machine
- External requests are rejected at the application level
- No API keys required

This is configured automatically in `docker-compose.yml` - no additional configuration needed.

### Rate Limiting

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `RATE_LIMIT_PER_MIN` | Requests per minute per key | `60` | No |
| `RATE_LIMIT_BURST` | Burst limit per key | `120` | No |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` | No |

### Queue Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `RETRY_MAX` | Maximum retry attempts | `5` | No |
| `RETRY_BACKOFF` | Backoff strategy | `exponential_jitter` | No |
| `RETRY_BASE_DELAY_MS` | Base delay for retries | `2000` | No |
| `RETRY_MAX_DELAY_MS` | Maximum retry delay | `30000` | No |
| `DLQ_ENABLED` | Enable dead letter queue | `true` | No |
| `CONSUMER_GROUP` | Redis consumer group name | `lens-workers` | No |
| `CONSUMER_BATCH_SIZE` | Messages per batch | `10` | No |

### Feature Profiles

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `FEATURE_PROFILE` | Active feature profile | `trend_follow_v1` | No |
| `TIMEFRAMES` | Comma-separated timeframes | `15m,1h,4h` | No |

**Available Profiles**:
- `trend_follow_v1` - Minimal trend-following (EMA, MACD, RSI, ATR)
- `crypto_perps_v1` - Adds funding rate, OI, mark price
- `full_v1` - Full feature set with S/R levels and OBI

### Stale Data Thresholds

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `STALE_MID_S` | Mid price staleness threshold (seconds) | `5` | No |
| `STALE_L2_S` | L2 book staleness threshold (seconds) | `10` | No |
| `STALE_CTX_S` | Context data staleness threshold (seconds) | `60` | No |
| `STALE_CANDLE_MULTIPLIER` | Candle staleness (N x interval) | `2` | No |

### Market Data Providers

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `PROVIDER_PRIMARY` | Primary data provider | `hyperliquid` | No |
| `PROVIDER_TIMEOUT_MS` | Provider request timeout | `10000` | No |
| `PROVIDER_RETRY_COUNT` | Provider retry attempts | `3` | No |

#### Hyperliquid Configuration

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `HYPERLIQUID_BASE_URL` | Hyperliquid API base URL | `https://api.hyperliquid.xyz` | No |
| `HYPERLIQUID_WS_URL` | Hyperliquid WebSocket URL | `wss://api.hyperliquid.xyz/ws` | No |

### AI Models

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AI_MODELS` | Comma-separated model names | `chatgpt,gemini` | No |
| `USE_REAL_AI` | Enable real AI evaluation | `false` | **Yes for production** |

> **⚠️ IMPORTANT**: `USE_REAL_AI` defaults to `false` for safety. When `false`, the system returns deterministic stub decisions instead of calling AI APIs. **You must set `USE_REAL_AI=true` in production** to use real AI models.

**Evaluation Modes**:
- `USE_REAL_AI=false` (default): Stub mode - returns deterministic decisions for testing/development
- `USE_REAL_AI=true`: Real mode - calls configured AI models in parallel

#### Per-Model Configuration

For each model in `AI_MODELS`, configure:

| Variable Pattern | Description | Default | Required |
|-----------------|-------------|---------|----------|
| `MODEL_{NAME}_PROVIDER` | API provider | - | **Yes** |
| `MODEL_{NAME}_API_KEY` | API key | - | **Yes** |
| `MODEL_{NAME}_MODEL_ID` | Specific model ID | varies | No |
| `MODEL_{NAME}_TIMEOUT_MS` | Request timeout | `30000` | No |
| `MODEL_{NAME}_MAX_TOKENS` | Max response tokens | `1000` | No |
| `MODEL_{NAME}_PROMPT_PATH` | Path to prompt file | `prompts/{name}_v1.md` | No |

**Example (ChatGPT)**:
```
MODEL_CHATGPT_PROVIDER=openai
MODEL_CHATGPT_API_KEY=sk-your-openai-key
MODEL_CHATGPT_MODEL_ID=gpt-4o
MODEL_CHATGPT_TIMEOUT_MS=30000
MODEL_CHATGPT_MAX_TOKENS=1000
MODEL_CHATGPT_PROMPT_PATH=/app/prompts/chatgpt_v1.md
```

**Example (Gemini)**:
```
MODEL_GEMINI_PROVIDER=google
MODEL_GEMINI_API_KEY=your-google-ai-key
MODEL_GEMINI_MODEL_ID=gemini-1.5-pro
MODEL_GEMINI_TIMEOUT_MS=30000
MODEL_GEMINI_MAX_TOKENS=1000
MODEL_GEMINI_PROMPT_PATH=/app/prompts/gemini_v1.md
```

**Example (Claude)**:
```
MODEL_CLAUDE_PROVIDER=anthropic
MODEL_CLAUDE_API_KEY=sk-ant-your-anthropic-key
MODEL_CLAUDE_MODEL_ID=claude-sonnet-4-20250514
MODEL_CLAUDE_TIMEOUT_MS=30000
MODEL_CLAUDE_MAX_TOKENS=1000
```

**Example (DeepSeek)**:
```
MODEL_DEEPSEEK_PROVIDER=deepseek
MODEL_DEEPSEEK_API_KEY=your-deepseek-key
MODEL_DEEPSEEK_MODEL_ID=deepseek-chat
MODEL_DEEPSEEK_TIMEOUT_MS=30000
MODEL_DEEPSEEK_MAX_TOKENS=1000
```

### WebSocket

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `WS_ENABLED` | Enable WebSocket server | `true` | No |
| `WS_PORT` | WebSocket port (if separate) | `8000` | No |
| `WS_PING_INTERVAL_S` | Ping interval | `30` | No |
| `WS_PING_TIMEOUT_S` | Ping timeout | `10` | No |
| `WS_MAX_CONNECTIONS` | Max concurrent connections | `100` | No |

### Observability

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `METRICS_ENABLED` | Enable Prometheus metrics | `true` | No |
| `METRICS_PATH` | Metrics endpoint path | `/metrics` | No |
| `HEALTH_PATH` | Health check path | `/health` | No |
| `READY_PATH` | Readiness check path | `/ready` | No |

---

## Configuration Files

### Policy Configuration

**File**: `config/policy.yaml`

Defines trading constraints applied during enrichment.

```yaml
# Global defaults
defaults:
  min_hold_minutes: 15
  one_direction_only: true
  max_trades_per_hour: 4
  max_position_size_pct: 25
  max_leverage: 10

# Per-symbol overrides
symbols:
  BTC:
    min_hold_minutes: 10
    max_position_size_pct: 30
  ETH:
    min_hold_minutes: 10
    max_position_size_pct: 30
  SOL:
    min_hold_minutes: 15
    max_position_size_pct: 20
```

### Feature Profiles

**File**: `config/feature_profiles.yaml`

Defines what data is collected for each profile.

```yaml
trend_follow_v1:
  description: "Minimal trend-following indicators"
  timeframes: ["15m", "1h", "4h"]
  indicators:
    - name: ema
      params:
        periods: [9, 21, 50]
    - name: macd
      params:
        fast: 12
        slow: 26
        signal: 9
    - name: rsi
      params:
        period: 14
    - name: atr
      params:
        period: 14
  market_data:
    - mid_price
    - spread_bps
    - price_drift_from_entry
  requires_derivs: false
  requires_levels: false

crypto_perps_v1:
  description: "Crypto perpetuals with funding/OI"
  extends: trend_follow_v1
  market_data:
    - funding_rate
    - predicted_funding
    - open_interest
    - oi_change_24h_pct
    - mark_price
    - oracle_price
  requires_derivs: true
  requires_levels: false

full_v1:
  description: "Full feature set with S/R and OBI"
  extends: crypto_perps_v1
  indicators:
    - name: support_resistance
      params:
        lookback: 100
        sensitivity: 0.02
    - name: order_book_imbalance
      params:
        depth_levels: [1, 2, 5]  # percent
  requires_levels: true
```

---

## Example .env File

```bash
# ===================
# Application
# ===================
APP_NAME=SigmaPilot Lens
DEBUG=false
LOG_LEVEL=INFO
LOG_FORMAT=json

# ===================
# Database
# ===================
DATABASE_URL=postgresql://lens:lens_password@localhost:5432/lens
DB_POOL_SIZE=5
RETENTION_DAYS=180

# ===================
# Redis
# ===================
REDIS_URL=redis://localhost:6379/0

# ===================
# Security
# ===================
# Network-based security: API is only accessible from internal Docker network
# No API keys required - all external requests are rejected at network level

# ===================
# Rate Limiting
# ===================
RATE_LIMIT_PER_MIN=60
RATE_LIMIT_BURST=120

# ===================
# Queue
# ===================
RETRY_MAX=5
RETRY_BACKOFF=exponential_jitter
DLQ_ENABLED=true

# ===================
# Feature Profile
# ===================
FEATURE_PROFILE=trend_follow_v1
TIMEFRAMES=15m,1h,4h

# ===================
# Stale Data Thresholds
# ===================
STALE_MID_S=5
STALE_L2_S=10
STALE_CTX_S=60

# ===================
# AI Models
# ===================
AI_MODELS=chatgpt,gemini,claude,deepseek

# ChatGPT Configuration
MODEL_CHATGPT_PROVIDER=openai
MODEL_CHATGPT_API_KEY=sk-your-openai-api-key
MODEL_CHATGPT_MODEL_ID=gpt-4o
MODEL_CHATGPT_TIMEOUT_MS=30000
MODEL_CHATGPT_MAX_TOKENS=1000

# Gemini Configuration
MODEL_GEMINI_PROVIDER=google
MODEL_GEMINI_API_KEY=your-google-ai-api-key
MODEL_GEMINI_MODEL_ID=gemini-1.5-pro
MODEL_GEMINI_TIMEOUT_MS=30000
MODEL_GEMINI_MAX_TOKENS=1000

# Claude Configuration
MODEL_CLAUDE_PROVIDER=anthropic
MODEL_CLAUDE_API_KEY=sk-ant-your-anthropic-api-key
MODEL_CLAUDE_MODEL_ID=claude-sonnet-4-20250514
MODEL_CLAUDE_TIMEOUT_MS=30000
MODEL_CLAUDE_MAX_TOKENS=1000

# DeepSeek Configuration
MODEL_DEEPSEEK_PROVIDER=deepseek
MODEL_DEEPSEEK_API_KEY=your-deepseek-api-key
MODEL_DEEPSEEK_MODEL_ID=deepseek-chat
MODEL_DEEPSEEK_TIMEOUT_MS=30000
MODEL_DEEPSEEK_MAX_TOKENS=1000

# ===================
# WebSocket
# ===================
WS_ENABLED=true
WS_PING_INTERVAL_S=30

# ===================
# Observability
# ===================
METRICS_ENABLED=true
```

---

## Docker Compose Override

For local development, you can use `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  gateway:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - .:/app
      - /app/.venv
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
    ports:
      - "8000:8000"
      - "5678:5678"  # debugpy

  worker:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - .:/app
      - /app/.venv
    environment:
      - DEBUG=true
      - LOG_LEVEL=DEBUG
```

---

## Configuration Validation

On startup, the application validates:

1. All required environment variables are set
2. Database connection is valid
3. Redis connection is valid
4. AI model API keys are present for configured models
5. Feature profile exists
6. Policy configuration is valid YAML

Validation errors will prevent startup and log detailed error messages.

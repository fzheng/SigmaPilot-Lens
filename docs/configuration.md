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

### Authentication

SigmaPilot Lens supports 3 authentication modes, allowing gradual migration from development to production:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AUTH_MODE` | Authentication mode: `none`, `psk`, or `jwt` | `none` | No |

**Authentication Modes**:

1. **`none`** (Development): No authentication required. All requests are allowed with full admin access.
2. **`psk`** (Docker Compose): Pre-shared key tokens. Simple setup for internal deployments.
3. **`jwt`** (Portable): JWT validation. Enterprise-ready, integrates with external identity providers.

#### Scopes

| Scope | Description | Endpoints |
|-------|-------------|-----------|
| `lens:submit` | Submit signals | `POST /signals` |
| `lens:read` | Read events, decisions, DLQ | `GET /events/*`, `GET /decisions/*`, `GET /dlq/*`, `WS /ws/stream` |
| `lens:admin` | Administrative operations (includes all scopes) | `POST /dlq/*/retry`, `POST /dlq/*/resolve`, `/llm-configs/*`, `/prompts/*` |

#### PSK Mode Configuration

Pre-shared key mode uses fixed tokens configured via environment variables:

| Variable | Description | Granted Scope |
|----------|-------------|---------------|
| `AUTH_TOKEN_SUBMIT` | Token for signal submission | `lens:submit` |
| `AUTH_TOKEN_READ` | Token for read operations | `lens:read` |
| `AUTH_TOKEN_ADMIN` | Token for admin operations | `lens:admin` (all scopes) |

**Example**:
```bash
AUTH_MODE=psk
AUTH_TOKEN_SUBMIT=submit-secret-token-abc123
AUTH_TOKEN_READ=read-secret-token-def456
AUTH_TOKEN_ADMIN=admin-secret-token-ghi789
```

**Usage**:
```bash
# Submit a signal with submit token
curl -X POST http://gateway:8000/api/v1/signals \
  -H "Authorization: Bearer submit-secret-token-abc123" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC-PERP", ...}'

# Read events with read token
curl http://gateway:8000/api/v1/events \
  -H "Authorization: Bearer read-secret-token-def456"

# Admin operations with admin token
curl http://gateway:8000/api/v1/llm-configs \
  -H "Authorization: Bearer admin-secret-token-ghi789"
```

#### JWT Mode Configuration

JWT mode validates tokens against external identity providers:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `AUTH_JWT_PUBLIC_KEY` | PEM-encoded public key for validation | - | Conditional* |
| `AUTH_JWT_JWKS_URL` | URL to JWKS endpoint | - | Conditional* |
| `AUTH_JWT_ISSUER` | Expected `iss` claim | - | No |
| `AUTH_JWT_AUDIENCE` | Expected `aud` claim | - | No |
| `AUTH_JWT_SCOPE_CLAIM` | Claim containing scopes | `scope` | No |

*Either `AUTH_JWT_PUBLIC_KEY` or `AUTH_JWT_JWKS_URL` is required in JWT mode.

**Example**:
```bash
AUTH_MODE=jwt
AUTH_JWT_JWKS_URL=https://your-idp.com/.well-known/jwks.json
AUTH_JWT_ISSUER=https://your-idp.com
AUTH_JWT_AUDIENCE=lens-api
AUTH_JWT_SCOPE_CLAIM=scope
```

**JWT Requirements**:
- Algorithm: RS256, ES256, or HS256
- Required claims: `exp`, `iat`
- Scopes must be space-separated in the scope claim: `"scope": "lens:submit lens:read"`

#### WebSocket Authentication

WebSocket connections authenticate via the `Sec-WebSocket-Protocol` header:

```
Sec-WebSocket-Protocol: bearer,<token>
```

The server echoes back `bearer` in the response protocol if authentication succeeds.

**Example (JavaScript)**:
```javascript
const ws = new WebSocket('ws://gateway:8000/api/v1/ws/stream', ['bearer', 'your-token-here']);

ws.onopen = () => {
  // Protocol will be 'bearer' if auth succeeded
  console.log('Connected with protocol:', ws.protocol);
};
```

### Network Security

In addition to authentication, SigmaPilot Lens uses network-level security:

- All services are isolated within the Docker network (`lens-network`)
- No ports are exposed to the host machine by default
- External requests are rejected at the application level
- Health check endpoints (`/health`, `/ready`) are always accessible

This is configured automatically in `docker-compose.yml`.

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
| `USE_REAL_AI` | Enable real AI evaluation | - | **Yes** |

> **⚠️ IMPORTANT**: `USE_REAL_AI` must be explicitly set. When `false`, the system returns deterministic stub decisions instead of calling AI APIs. **Set `USE_REAL_AI=true` in production** to use real AI models.

**Evaluation Modes**:
- `USE_REAL_AI=false`: Stub mode - returns deterministic decisions for testing/development
- `USE_REAL_AI=true`: Real mode - calls configured AI models in parallel

#### LLM Configuration Management

LLM configurations (API keys, model IDs, enabled status) are managed at **runtime via API endpoints**, not environment variables. This allows:

- **Hot reload**: Change API keys without container restart
- **Dynamic enable/disable**: Turn models on/off without redeployment
- **API key testing**: Validate keys before enabling
- **Secure storage**: Keys stored in PostgreSQL, masked in API responses

**Supported Models**:

| Model Name | Provider | Default Model ID |
|------------|----------|------------------|
| `chatgpt` | OpenAI | `gpt-4o` |
| `gemini` | Google | `gemini-1.5-pro` |
| `claude` | Anthropic | `claude-sonnet-4-20250514` |
| `deepseek` | DeepSeek | `deepseek-chat` |

**Configuration via API**:

```bash
# Configure ChatGPT
curl -X PUT http://gateway:8000/api/v1/llm-configs/chatgpt \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-...", "enabled": true}'

# Test the API key
curl -X POST http://gateway:8000/api/v1/llm-configs/chatgpt/test

# List all configurations
curl http://gateway:8000/api/v1/llm-configs

# Disable a model
curl -X PATCH http://gateway:8000/api/v1/llm-configs/chatgpt \
  -H "Content-Type: application/json" \
  -d '{"enabled": false}'
```

See [API Reference](api-reference.md#llm-configuration) for full endpoint documentation.

#### Prompt Management

AI prompts are stored in the database and managed via API endpoints. This enables:

- **Versioning**: Multiple prompt versions can coexist (v1, v2, etc.)
- **Hot reload**: Update prompts without container restart
- **Audit trail**: Track who created/modified prompts and when
- **Core + Wrapper pattern**: Shared core logic with model-specific wrappers

**Prompt Types**:
- `core`: Shared decision-making logic (e.g., `core_decision`)
- `wrapper`: Model-specific formatting (e.g., `chatgpt_wrapper`, `claude_wrapper`)

**Configuration via API**:

```bash
# List all prompts
curl http://gateway:8000/api/v1/prompts \
  -H "Authorization: Bearer <admin-token>"

# Create a new prompt version
curl -X POST http://gateway:8000/api/v1/prompts \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "core_decision",
    "version": "v2",
    "prompt_type": "core",
    "content": "# Trading Decision Framework v2..."
  }'

# Deactivate a prompt version
curl -X PATCH http://gateway:8000/api/v1/prompts/core_decision/v1 \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{"is_active": false}'
```

On first startup, if no prompts exist in the database, the service automatically seeds from the `prompts/` directory.

See [API Reference](api-reference.md#prompt-management) for full endpoint documentation.

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
# Authentication
# ===================
# AUTH_MODE: none (dev), psk (Docker Compose), jwt (portable)
AUTH_MODE=none

# PSK Mode tokens (uncomment and set for psk mode)
# AUTH_TOKEN_SUBMIT=your-submit-token
# AUTH_TOKEN_READ=your-read-token
# AUTH_TOKEN_ADMIN=your-admin-token

# JWT Mode (uncomment for jwt mode)
# AUTH_JWT_JWKS_URL=https://your-idp.com/.well-known/jwks.json
# AUTH_JWT_ISSUER=https://your-idp.com
# AUTH_JWT_AUDIENCE=lens-api

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
# Set to true for production, false for stub decisions
USE_REAL_AI=false
# LLM API keys are configured via API: /api/v1/llm-configs

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
4. `USE_REAL_AI` is explicitly set (true or false)
5. Feature profile exists
6. Policy configuration is valid YAML

LLM configurations are loaded from the database on startup. If no models are configured, the system will log a warning but continue running. Configure models via the `/api/v1/llm-configs` endpoints.

Validation errors will prevent startup and log detailed error messages.

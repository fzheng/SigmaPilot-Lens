# Architecture Overview

## System Architecture

SigmaPilot Lens follows an event-driven architecture with clear separation of concerns across containerized services.

```
                                    ┌─────────────────────────────────────────────────────────────┐
                                    │                     SigmaPilot Lens                         │
                                    └─────────────────────────────────────────────────────────────┘

┌──────────────┐          ┌──────────────────────────────────────────────────────────────────────────────────┐
│              │          │                                                                                  │
│   External   │          │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │
│   Systems    │─────────▶│  │   Signal    │───▶│   Redis     │───▶│ Enrichment  │───▶│     AI      │       │
│  (Signals)   │   HTTP   │  │   Gateway   │    │   Streams   │    │   Worker    │    │   Engine    │       │
│              │          │  └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘       │
└──────────────┘          │         │                  │                  │                  │              │
                          │         │                  │                  │                  │              │
                          │         ▼                  ▼                  ▼                  ▼              │
┌──────────────┐          │  ┌────────────────────────────────────────────────────────────────────┐         │
│              │          │  │                        PostgreSQL                                  │         │
│  Downstream  │◀─────────│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │         │
│  Executors   │    WS    │  │  │  events  │ │ enriched │ │decisions │ │   dlq    │ │  timeline│ │         │
│              │          │  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │         │
└──────────────┘          │  └────────────────────────────────────────────────────────────────────┘         │
                          │         ▲                                                                       │
                          │         │                                                                       │
                          │  ┌─────────────┐                                                                │
                          │  │  WebSocket  │◀───────────────────────────────────────────────────────────────│
                          │  │  Publisher  │                                                                │
                          │  └─────────────┘                                                                │
                          │                                                                                  │
                          └──────────────────────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Signal Gateway

**Responsibility**: API entry point for trading signals

- FastAPI application with async request handling
- Schema validation using Pydantic
- 3-mode authentication: `none` / `psk` / `jwt`
- Scope-based authorization (`lens:submit`, `lens:read`, `lens:admin`)
- Rate limiting (60 req/min, burst 120)
- Assigns `event_id`, `received_ts`, and validates `source`

**Endpoints**:
- `POST /api/v1/signals` - Submit trading signal (scope: `lens:submit`)
- `GET /api/v1/events` - List events with filtering (scope: `lens:read`)
- `GET /api/v1/events/{event_id}` - Get event details with timeline (scope: `lens:read`)
- `GET /api/v1/events/{event_id}/status` - Get processing status (scope: `lens:read`)
- `GET /api/v1/decisions` - List AI decisions with filtering (scope: `lens:read`)
- `GET /api/v1/decisions/{id}` - Get decision details (scope: `lens:read`)
- `GET /api/v1/dlq` - List dead letter queue entries (scope: `lens:read`)
- `GET /api/v1/dlq/{id}` - Get DLQ entry details (scope: `lens:read`)
- `POST /api/v1/dlq/{id}/retry` - Retry failed entry (scope: `lens:admin`)
- `POST /api/v1/dlq/{id}/resolve` - Mark entry as resolved (scope: `lens:admin`)
- `GET /api/v1/llm-configs` - List LLM configurations (scope: `lens:admin`)
- `PUT /api/v1/llm-configs/{model}` - Configure LLM model (scope: `lens:admin`)
- `GET /api/v1/prompts` - List AI prompts (scope: `lens:admin`)
- `POST /api/v1/prompts` - Create AI prompt (scope: `lens:admin`)
- `PUT /api/v1/prompts/{name}/{version}` - Update AI prompt (scope: `lens:admin`)
- `GET /api/v1/health` - Health check (no auth)
- `GET /api/v1/ready` - Readiness check (no auth)
- `GET /api/v1/metrics` - Prometheus metrics

### 2. Redis Streams Queue

**Responsibility**: Durable message queue with ordering guarantees

- Stream: `lens:signals:pending` - Incoming signals
- Stream: `lens:signals:enriched` - Enriched signals ready for AI
- Stream: `lens:dlq` - Dead letter queue
- Consumer groups for scalable processing

**Features**:
- At-least-once delivery
- Automatic acknowledgment tracking
- 5 retries with exponential backoff + jitter
- Message persistence across restarts

### 3. Enrichment Worker

**Responsibility**: Validate signals and enrich with market data

**Signal Validation** (before enrichment):
- Early price validation: Rejects signals with >2% price drift from current market
- Signal age validation: Rejects signals older than 5 minutes
- Optimization: Age check runs first (no API call needed)
- Rejected signals marked with status="rejected" in database

**Enrichment Flow**:
- Consumes from `lens:signals:pending`
- Validates signal entry price against live market
- Fetches data from Hyperliquid (primary provider)
- Computes TA indicators based on feature profile
- Produces to `lens:signals:enriched`
- Handles provider failures with retry logic

**Feature Profiles**:
- `trend_follow_v1` - EMA, MACD, RSI, ATR across 15m/1h/4h timeframes
- `crypto_perps_v1` - Above + funding rate, OI, mark price
- `full_v1` - Above + support/resistance, OBI (S/R and OBI not yet implemented)

### 4. AI Evaluation Engine

**Responsibility**: Run multiple AI models in parallel

- Consumes from `lens:signals:enriched`
- Parallel model execution (failures isolated)
- Strict output schema validation
- Token economy controls per model
- Fallback decisions for failed evaluations (IGNORE with 0 confidence)
- **Database-backed prompts**: Prompts loaded from PostgreSQL with in-memory caching (5-min TTL)
- Prompt versioning and hash tracking for reproducibility

**Supported Models**:
- **ChatGPT** (OpenAI API) - GPT-4o default
- **Gemini** (Google AI API) - Gemini 1.5 Pro default
- **Claude** (Anthropic API) - Claude Sonnet 4 default
- **DeepSeek** (DeepSeek API) - DeepSeek Chat default

**Adapter Pattern**: Each provider has a dedicated adapter implementing `BaseModelAdapter`:
- `OpenAIAdapter` - For ChatGPT and compatible APIs
- `GoogleAdapter` - For Gemini models
- `AnthropicAdapter` - For Claude models
- `DeepSeekAdapter` - For DeepSeek models (OpenAI-compatible)

### 5. WebSocket Publisher

**Responsibility**: Real-time decision delivery

- Plain WebSocket server (scope: `lens:read`)
- Authentication via `Sec-WebSocket-Protocol: bearer,<token>`
- Subscription filters: model, symbol, event_type
- Broadcast to matching subscribers

### 6. PostgreSQL Storage

**Responsibility**: Audit trail and queryable history

**Tables**:
- `events` - Raw incoming signals
- `enriched_events` - Enriched signal data
- `model_decisions` - Per-model decisions
- `dlq_entries` - Failed processing records
- `processing_timeline` - Status transitions
- `llm_configs` - Runtime LLM configuration (API keys, model IDs, enabled status)
- `prompts` - Versioned AI prompts (core + wrapper pattern)

## Data Flow

```
1. Signal Received
   └─▶ Validate schema
   └─▶ Verify internal network
   └─▶ Rate limit check
   └─▶ Assign event_id, received_ts
   └─▶ Persist to events table (status=received)
   └─▶ Enqueue to Redis (lens:signals:pending)
   └─▶ Return event_id to caller

2. Signal Validation (early rejection)
   └─▶ Check signal age (>5 min = reject, no API call)
   └─▶ Fetch current price from Hyperliquid
   └─▶ Calculate drift: |current - entry| / entry
   └─▶ If drift > 2%: reject signal, skip enrichment
   └─▶ Update events.status = 'rejected' with reason
   └─▶ Log rejection for metrics

3. Enrichment (if validation passes)
   └─▶ Consume from lens:signals:pending
   └─▶ Fetch market data (Hyperliquid)
   └─▶ Compute TA indicators per timeframe
   └─▶ Add quality flags (staleness, missing data)
   └─▶ Persist enriched data with signal_age_seconds
   └─▶ Enqueue to lens:signals:enriched
   └─▶ On failure: retry or DLQ

4. AI Evaluation
   └─▶ Consume from lens:signals:enriched
   └─▶ Load prompts from database cache (core + wrapper)
   └─▶ Render prompts with enriched data
   └─▶ Call models in parallel
   └─▶ Validate output schemas
   └─▶ Persist decisions with prompt version/hash
   └─▶ Trigger publish

5. Publishing
   └─▶ Match decision to subscriptions
   └─▶ Broadcast via WebSocket
   └─▶ Log publish confirmation
```

## Deployment Architecture

### Docker Compose (MVP)

```yaml
services:
  gateway:      # Signal Gateway + API
  worker:       # Enrichment + AI Engine
  publisher:    # WebSocket server
  redis:        # Queue
  postgres:     # Storage
```

### Kubernetes-Ready Design

- Stateless services (all state in Redis/Postgres)
- Environment-based configuration
- Health check endpoints (`/health`, `/ready`)
- Prometheus metrics (`/metrics`)
- Horizontal scaling ready (consumer groups)

## Security Model

### Authentication

SigmaPilot Lens implements a flexible 3-mode authentication system designed for gradual migration from development to production:

| Mode | Use Case | Description |
|------|----------|-------------|
| `none` | Development | No authentication required |
| `psk` | Docker Compose | Pre-shared key tokens |
| `jwt` | Production | JWT validation with external IdP |

### Authorization Scopes

Role-based access control with 3 scopes:

| Scope | Permissions | Endpoints |
|-------|-------------|-----------|
| `lens:submit` | Submit signals | `POST /signals` |
| `lens:read` | Read data | `GET /events/*`, `/decisions/*`, `/dlq/*`, `WS /ws/stream` |
| `lens:admin` | Admin + all above | `POST /dlq/*/retry`, `/dlq/*/resolve`, `/llm-configs/*`, `/prompts/*` |

**Scope Hierarchy**: `lens:admin` includes all other scopes.

### PSK Mode (Docker Compose)

```bash
AUTH_MODE=psk
AUTH_TOKEN_SUBMIT=<token>  # Grants lens:submit
AUTH_TOKEN_READ=<token>    # Grants lens:read
AUTH_TOKEN_ADMIN=<token>   # Grants lens:admin (all scopes)
```

Usage: `Authorization: Bearer <token>`

### JWT Mode (Production)

- Validates signature against JWKS endpoint or public key
- Checks `exp`, `iat` claims
- Reads scopes from configurable claim (default: `scope`)
- Supports RS256, ES256, HS256 algorithms

```bash
AUTH_MODE=jwt
AUTH_JWT_JWKS_URL=https://idp.example.com/.well-known/jwks.json
AUTH_JWT_ISSUER=https://idp.example.com
AUTH_JWT_AUDIENCE=lens-api
AUTH_JWT_SCOPE_CLAIM=scope
```

### WebSocket Authentication

WebSocket connections authenticate via subprotocol header:

```
Sec-WebSocket-Protocol: bearer,<token>
```

### Network-Level Security
- All services run inside isolated Docker network (`lens-network`)
- No ports exposed to host machine in production
- Health endpoints (`/health`, `/ready`) bypass authentication

### Rate Limiting
- Per-client rate limiting
- Sliding window algorithm
- Configurable limits via environment

### Network Architecture
- All services on private Docker network
- Gateway, Redis, Postgres only accessible internally
- Use `docker-compose.override.yml` to expose ports during development

## Observability

### Metrics (Prometheus)
- `lens_signals_received_total` - Signals received by source/symbol
- `lens_signals_enqueued_total` - Signals enqueued to Redis
- `lens_signals_rejected_total` - Signals rejected (by reason: price_drift, signal_too_old)
- `lens_signals_enriched_total` - Signals successfully enriched
- `lens_enrichment_duration_seconds` - Enrichment latency histogram
- `lens_model_evaluation_duration_seconds` - AI model latency histogram
- `lens_decisions_published_total` - Decisions published via WebSocket
- `lens_dlq_entries_total` - Failed processing records
- `lens_queue_depth` - Current queue depth gauge

### Logging
- Structured JSON logs
- Trace ID (`event_id`) across all stages
- Log levels: DEBUG, INFO, WARN, ERROR

### Health Checks
- `/health` - Liveness probe
- `/ready` - Readiness probe (checks Redis, Postgres)
- `/metrics` - Prometheus metrics

## Technology Stack

| Component | Technology |
|-----------|------------|
| API Framework | FastAPI (Python 3.11+) |
| Queue | Redis Streams 7+ |
| Database | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 |
| Migrations | Alembic |
| WebSocket | FastAPI WebSocket |
| AI Clients | OpenAI SDK, Google GenAI SDK, Anthropic SDK |
| TA Library | pandas-ta, ta-lib |
| Metrics | prometheus-client |
| Containerization | Docker, Docker Compose |

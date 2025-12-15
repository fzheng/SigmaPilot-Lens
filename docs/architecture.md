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
│  Executors   │    WS    │  │  │ api_keys │ │  events  │ │ enriched │ │decisions │ │   dlq    │ │         │
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
- API key authentication middleware
- Rate limiting (60 req/min, burst 120)
- Assigns `event_id`, `received_ts`, and validates `source`

**Endpoints**:
- `POST /api/v1/signals` - Submit trading signal
- `GET /api/v1/signals/{event_id}` - Get signal status
- `POST /api/v1/keys` - Create API key (admin)
- `GET /api/v1/keys` - List API keys (admin)
- `DELETE /api/v1/keys/{key_id}` - Delete API key (admin)

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

**Responsibility**: Fetch market data and compute technical features

- Consumes from `lens:signals:pending`
- Fetches data from Hyperliquid (primary provider)
- Computes TA indicators based on feature profile
- Produces to `lens:signals:enriched`
- Handles provider failures with retry logic

**Feature Profiles**:
- `trend_follow_v1` - EMA, MACD, RSI, ATR (minimal)
- `crypto_perps_v1` - Above + funding, OI, mark price
- `full_v1` - Above + support/resistance, OBI, order flow

### 4. AI Evaluation Engine

**Responsibility**: Run multiple AI models in parallel

- Consumes from `lens:signals:enriched`
- Parallel model execution (failures isolated)
- Strict output schema validation
- Token economy controls per model

**Supported Models**:
- ChatGPT (OpenAI API)
- Gemini (Google AI API)
- Extensible for additional models

### 5. WebSocket Publisher

**Responsibility**: Real-time decision delivery

- Plain WebSocket server
- Subscription filters: model, symbol, event_type
- Same API key authentication
- Broadcast to matching subscribers

### 6. PostgreSQL Storage

**Responsibility**: Audit trail and queryable history

**Tables**:
- `api_keys` - API key management
- `events` - Raw incoming signals
- `enriched_events` - Enriched signal data
- `model_decisions` - Per-model decisions
- `dlq_entries` - Failed processing records
- `processing_timeline` - Status transitions

## Data Flow

```
1. Signal Received
   └─▶ Validate schema
   └─▶ Authenticate API key
   └─▶ Rate limit check
   └─▶ Assign event_id, received_ts
   └─▶ Persist to events table
   └─▶ Enqueue to Redis (lens:signals:pending)
   └─▶ Return event_id to caller

2. Enrichment
   └─▶ Consume from lens:signals:pending
   └─▶ Fetch market data (Hyperliquid)
   └─▶ Compute TA indicators
   └─▶ Add quality flags
   └─▶ Persist enriched data
   └─▶ Enqueue to lens:signals:enriched
   └─▶ On failure: retry or DLQ

3. AI Evaluation
   └─▶ Consume from lens:signals:enriched
   └─▶ Load prompts for configured models
   └─▶ Call models in parallel
   └─▶ Validate output schemas
   └─▶ Persist decisions
   └─▶ Trigger publish

4. Publishing
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
- API key in `X-API-Key` header
- Admin key for key management endpoints
- Keys stored hashed in PostgreSQL
- Expiration support

### Rate Limiting
- Per-key rate limiting
- Sliding window algorithm
- Configurable limits via environment

### Network
- Internal services on private network
- Only gateway exposed externally
- WebSocket on separate port (optional)

## Observability

### Metrics (Prometheus)
- `lens_signals_received_total`
- `lens_signals_enqueued_total`
- `lens_enrichment_duration_seconds`
- `lens_model_evaluation_duration_seconds`
- `lens_decisions_published_total`
- `lens_dlq_entries_total`
- `lens_queue_depth`

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
| AI Clients | OpenAI SDK, Google GenAI SDK |
| TA Library | pandas-ta, ta-lib |
| Metrics | prometheus-client |
| Containerization | Docker, Docker Compose |

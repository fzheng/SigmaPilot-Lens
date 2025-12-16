# Implementation Plan

## Overview

This document outlines the phased implementation plan for SigmaPilot Lens MVP. The plan follows a **vertical slice** approach: Phase 1 delivers a minimal but complete E2E flow, and subsequent phases deepen functionality without changing core plumbing.

## Phase Summary

| Phase | Description | Key Deliverable |
|-------|-------------|-----------------|
| **1** | E2E Skeleton | Working "Hello Lens" path: signal → enrich (stub) → evaluate (stub) → publish |
| **2** | Signal Gateway (Full) | Production auth, rate limiting, schema validation, idempotency |
| **3** | Enrichment (Full) | Hyperliquid provider, TA indicators, feature profiles |
| **4** | AI Evaluation (Full) | Multi-model engine, prompt management, output validation |
| **5** | Polish & Hardening | Metrics, audit queries, load testing, deployment optimization |

---

## Phase 1: E2E Skeleton ("Hello Lens")

**Goal**: Establish a working end-to-end flow from signal submission to WebSocket publish. All components are stubs, but the plumbing works.

### 1.1 Phase 1 Completion Criteria

Phase 1 is DONE only when:

- [ ] `docker compose up` starts all services (gateway, worker, redis, postgres)
- [ ] `POST /api/v1/signals` validates schema and enqueues to Redis Stream
- [ ] Worker consumes from queue and writes `events.status = enriched` (stub enrichment)
- [ ] Evaluation stub writes one `model_decisions` row with deterministic response
- [ ] WebSocket broadcasts the stub decision to connected clients
- [ ] `GET /health` returns ok
- [ ] `GET /ready` shows queue lag and confirms redis/postgres connectivity

### 1.2 Minimal Components for Phase 1

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Gateway   │───▶│   Redis     │───▶│   Worker    │───▶│  WebSocket  │
│  (FastAPI)  │    │  (Stream)   │    │   (Stub)    │    │  Publisher  │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                                      │                  │
      └──────────────────────────────────────┴──────────────────┘
                                             │
                                    ┌─────────────────┐
                                    │   PostgreSQL    │
                                    └─────────────────┘
```

### 1.3 Phase 1 Implementation Tasks

#### 1.3.1 Database Setup
- [x] Create initial Alembic migration with all tables
- [x] Verify tables: events, enriched_events, model_decisions, processing_timeline, dlq_entries
- [x] Add indexes for event_id, symbol, status, received_at

#### 1.3.2 Gateway (Minimal)
- [x] `POST /api/v1/signals` - Accept signal, validate schema, assign event_id
- [x] Network-level security (Docker network isolation)
- [x] Persist to `events` table with status='queued'
- [x] Enqueue to Redis Stream `lens:signals:pending`
- [x] Return event_id

#### 1.3.3 Redis Queue
- [ ] Initialize Redis Stream and consumer group on startup
- [ ] Producer: enqueue signal with event_id, payload, timestamp
- [ ] Consumer: read from stream with XREADGROUP

#### 1.3.4 Worker (Stub)
- [ ] Consume from `lens:signals:pending`
- [ ] **Stub Enrichment**: Add `mid_price` from signal's `entry_price` (no real provider)
- [ ] Update `events.status = 'enriched'`, set `enriched_at`
- [ ] **Stub Evaluation**: Return deterministic decision:
  ```json
  {
    "decision": "IGNORE",
    "confidence": 0.5,
    "reasons": ["stub_evaluation"],
    "model_meta": {"model_name": "stub", "latency_ms": 10, "status": "SUCCESS"}
  }
  ```
- [ ] Write to `model_decisions` table
- [ ] Update `events.status = 'evaluated'`, set `evaluated_at`
- [ ] Trigger WebSocket publish

#### 1.3.5 WebSocket Publisher (Minimal)
- [ ] WebSocket endpoint at `/ws/decisions`
- [ ] Accept connections (no auth in Phase 1)
- [ ] Broadcast all decisions to all connected clients
- [ ] Update `events.status = 'published'`, set `published_at`

#### 1.3.6 Health Endpoints
- [ ] `GET /health` - Return {"status": "ok"}
- [ ] `GET /ready` - Check Redis ping, Postgres connectivity, return queue depth

#### 1.3.7 Docker Compose
- [ ] Configure all services: gateway, worker, redis, postgres
- [ ] Verify startup order with health checks
- [ ] Test `docker compose up` brings up working system

### 1.4 Phase 1 Testing

- [ ] Manual test: POST signal → verify WebSocket receives decision
- [ ] Verify database has event with status='published'
- [ ] Verify all lifecycle timestamps populated
- [ ] Simple integration test script

---

## Phase 2: Signal Gateway (Production-Ready)

**Goal**: Harden the gateway with rate limiting and error handling.

### 2.1 Security (Completed)
- [x] Network-level security via Docker network isolation
- [x] No API keys required - all services internal only
- [x] External requests rejected at application level

### 2.2 Rate Limiting
- [ ] Redis-based sliding window limiter
- [ ] 60 req/min, burst 120
- [ ] Per-client rate limiting
- [ ] Return 429 with Retry-After header

### 2.4 Idempotency
- [ ] Accept optional `idempotency_key` in request
- [ ] Reject duplicate signals with same idempotency_key
- [ ] Return existing event_id for duplicates

### 2.5 Event Query Endpoints
- [ ] `GET /api/v1/events` - List with filters
- [ ] `GET /api/v1/events/{event_id}` - Full details with timeline
- [ ] `GET /api/v1/events/{event_id}/status` - Current status

### 2.6 Error Handling
- [ ] Structured error responses
- [ ] Validation error details
- [ ] Request ID tracking

### 2.7 Phase 2 Deliverables
- [ ] Full authentication flow working
- [ ] Rate limiting active
- [ ] All gateway endpoints implemented
- [ ] Swagger UI functional for API testing

---

## Phase 3: Data Enrichment (Full) ✅ COMPLETED

**Goal**: Replace stub enrichment with real market data and technical analysis.

### 3.1 Hyperliquid Provider ✅
- [x] REST client for Hyperliquid API (POST to /info endpoint)
- [x] `get_ticker()` - Mid price, bid, ask, spread (via allMids + l2Book)
- [x] `get_ohlcv()` - Candlestick data for TA (via candleSnapshot)
- [x] `get_orderbook()` - L2 order book (via l2Book)
- [x] `get_funding_rate()` - Funding and predicted funding (via metaAndAssetCtxs)
- [x] `get_open_interest()` - OI in contracts and USD (via metaAndAssetCtxs)
- [x] `get_mark_price()` - Mark price for derivatives
- [x] `get_24h_volume()` - 24h notional volume
- [x] Error handling (ProviderError with HTTP details)
- [x] Response caching (5s TTL for asset contexts)

### 3.2 Technical Analysis ✅
- [x] EMA calculation (configurable periods, default 9, 21, 50)
- [x] MACD (configurable, default 12, 26, 9)
- [x] RSI (configurable, default 14 period)
- [x] ATR (configurable, default 14 period)
- [ ] Support/Resistance detection (optional, for full_v1) - TODO
- [ ] Order book imbalance (optional, for full_v1) - TODO

### 3.3 Feature Profiles ✅
- [x] Load profile from config/feature_profiles.yaml
- [x] `trend_follow_v1`: Basic indicators (15m, 1h, 4h timeframes)
- [x] `crypto_perps_v1`: Add derivatives data (funding, OI)
- [x] `full_v1`: Extends crypto_perps_v1 with all indicators
- [x] Profile-based data fetching
- [x] Profile inheritance support (extends keyword)

### 3.4 Quality Flags ✅
- [x] Detect missing data from provider
- [x] Detect stale data (configurable thresholds per data type)
- [x] Detect out-of-range values (spread, bid/ask, RSI, ATR)
- [x] Include flags in enriched event

### 3.5 Signal Validation ✅ (NEW)
- [x] Early price validation before enrichment
- [x] Reject signals with >2% price drift from current market
- [x] Reject signals older than 5 minutes
- [x] Metrics for rejection tracking (by reason)
- [x] Database status "rejected" with timeline entry

### 3.6 Enrichment Worker ✅
- [x] Consume from `lens:signals:pending`
- [x] Early validation before database lookup (optimization)
- [x] Fetch data based on feature profile
- [x] Compute TA indicators per timeframe
- [x] Build compact enriched payload (< 4KB)
- [x] Store data_timestamps for each component
- [x] Track signal_age_seconds
- [x] Handle failures: retry or DLQ

### 3.7 Phase 3 Deliverables ✅
- [x] Real market data flowing (~1.5s enrichment time)
- [x] TA indicators computed correctly (57+ unit tests)
- [x] Quality flags working (staleness, range validation)
- [x] Signal validation preventing bad signals
- [x] DLQ capturing failures

---

## Phase 4: AI Evaluation (Full)

**Goal**: Replace stub evaluation with real multi-model AI evaluation.

### 4.1 Model Interface
- [ ] Abstract base class for AI models
- [ ] `evaluate(enriched_event, prompt)` method
- [ ] Timeout handling
- [ ] Token tracking

### 4.2 ChatGPT Implementation
- [ ] OpenAI SDK integration
- [ ] Configurable model (gpt-4o default)
- [ ] JSON mode for structured output
- [ ] Error handling (rate limits, timeouts)

### 4.3 Gemini Implementation
- [ ] Google GenAI SDK integration
- [ ] Configurable model (gemini-1.5-pro default)
- [ ] JSON output enforcement
- [ ] Error handling

### 4.4 Prompt Management
- [ ] Core + wrapper prompt structure
- [ ] Prompt version tracking
- [ ] Prompt hash for reproducibility
- [ ] Dynamic prompt rendering

### 4.5 Output Validation
- [ ] Parse model response as JSON
- [ ] Validate against ModelDecision schema
- [ ] Handle invalid outputs:
  - Store raw response
  - Mark status as 'invalid_json'
  - Use fallback decision

### 4.6 Parallel Evaluation
- [ ] Run all configured models concurrently
- [ ] Isolate failures (one model failing doesn't block others)
- [ ] Collect results from all models
- [ ] Write N decisions per event

### 4.7 Evaluation Worker
- [ ] Consume from `lens:signals:enriched`
- [ ] Load prompts for each model
- [ ] Call models in parallel
- [ ] Validate and store decisions
- [ ] Trigger publish for each decision

### 4.8 Phase 4 Deliverables
- [ ] Multi-model evaluation working
- [ ] Prompt versioning tracked
- [ ] Invalid output handling
- [ ] Per-model metrics

---

## Phase 5: Polish & Hardening

**Goal**: Production-ready observability, performance, and deployment.

### 5.1 Prometheus Metrics
- [ ] Signal counters (received, enqueued, enriched, evaluated, published)
- [ ] Latency histograms (enqueue, enrichment, evaluation, E2E)
- [ ] Queue depth gauges
- [ ] Error counters (DLQ, model errors)
- [ ] WebSocket connection gauge
- [ ] `/metrics` endpoint

### 5.2 Structured Logging
- [ ] JSON log format
- [ ] event_id as trace ID across all logs
- [ ] Stage transitions logged (RECEIVED → ENQUEUED → ENRICHED → ...)
- [ ] Log levels configured via env

### 5.3 Audit Endpoints
- [ ] `GET /api/v1/decisions` - Query decisions with filters
- [ ] `GET /api/v1/dlq` - Query DLQ entries
- [ ] `POST /api/v1/dlq/{id}/retry` - Retry DLQ entry

### 5.4 WebSocket Enhancement
- [x] Subscription filters (model, symbol, event_type)
- [x] Network-level security (Docker network isolation)
- [x] Ping/pong heartbeat
- [x] Connection limits

### 5.5 Performance Testing
- [ ] Load test script (target: 60 signals/min sustained)
- [ ] Verify p95 latencies:
  - End-to-end < 6s
  - Enrichment < 2s
  - Model evaluation < 3s
  - WebSocket fanout < 1s
- [ ] Stress test queue depth

### 5.6 Docker Optimization
- [ ] Multi-stage Dockerfile
- [ ] Resource limits configured
- [ ] Health check probes
- [ ] Graceful shutdown handling

### 5.7 Phase 5 Deliverables
- [ ] Full observability stack
- [ ] Load tested and verified
- [ ] Production-ready Docker config
- [ ] Operations documentation

---

## Database Schema Summary

### events (enhanced)
```
- id (uuid, pk)
- event_id (string, unique)
- idempotency_key (string, unique, nullable)
- event_type, symbol, signal_direction
- entry_price, size, liquidation_price
- ts_utc, source
- status (queued|enriched|evaluated|published|failed|dlq)
- feature_profile
- received_at, enriched_at, evaluated_at, published_at
- raw_payload (jsonb)
```

### enriched_events (enhanced)
```
- id (uuid, pk)
- event_id (fk)
- feature_profile
- provider, provider_version
- market_data, ta_data, levels_data, derivs_data (jsonb)
- constraints (jsonb)
- data_timestamps (jsonb) - per component timestamps
- quality_flags (jsonb)
- enriched_payload (jsonb) - compact payload for AI
- enrichment_duration_ms
```

### model_decisions (enhanced)
```
- id (uuid, pk)
- event_id (fk)
- model_name, model_version
- prompt_version, prompt_hash
- decision, confidence
- entry_plan, risk_plan, size_pct, reasons (jsonb)
- decision_payload (jsonb) - full output
- latency_ms, tokens_in, tokens_out
- status (ok|invalid_json|timeout|provider_error)
- error_code, error_message
- raw_response (text, nullable) - stored on error
```

### dlq_entries (enhanced)
```
- id (uuid, pk)
- event_id (nullable)
- stage (enqueue|enrich|evaluate|publish)
- reason_code, error_message
- payload (jsonb)
- retry_count
- last_retry_at
- resolved_at, resolution_note
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Hyperliquid rate limits | Caching, request batching, fallback provider research |
| AI model latency spikes | Timeouts, independent model failures, deterministic fallback |
| Redis data loss | AOF persistence, periodic backups |
| Invalid AI outputs | Schema validation, raw response storage, fallback decision |
| WebSocket scaling | Connection limits, consider Redis pub/sub for horizontal scaling |

---

## Success Criteria

### Phase 1 (E2E Skeleton)
- [ ] Full signal flow working with stubs
- [ ] Docker compose up → working system
- [ ] Can POST signal, receive decision on WebSocket

### Phase 2 (Gateway)
- [ ] Auth, rate limiting, idempotency working
- [ ] All API endpoints functional in Swagger

### Phase 3 (Enrichment) ✅
- [x] Real Hyperliquid data flowing
- [x] TA indicators verified correct
- [x] Quality flags detecting issues
- [x] Signal validation rejecting invalid signals

### Phase 4 (AI Evaluation)
- [ ] ChatGPT + Gemini producing decisions
- [ ] Invalid outputs handled gracefully
- [ ] Prompt versioning tracked

### Phase 5 (Polish)
- [ ] All p95 latency targets met
- [ ] Metrics dashboard showing healthy system
- [ ] 24h soak test passed

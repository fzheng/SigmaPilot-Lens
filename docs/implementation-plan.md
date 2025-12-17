# Implementation Plan

## Overview

This document outlines the phased implementation plan for SigmaPilot Lens MVP. The plan follows a **vertical slice** approach: Phase 1 delivers a minimal but complete E2E flow, and subsequent phases deepen functionality without changing core plumbing.

## Phase Summary

| Phase | Description | Status | Key Deliverable |
|-------|-------------|--------|-----------------|
| **1** | E2E Skeleton | ✅ DONE | Working "Hello Lens" path: signal → enrich → evaluate → publish |
| **2** | Signal Gateway | ✅ DONE | Network security, idempotency, rate limiting, event/decision query endpoints |
| **3** | Enrichment | ✅ DONE | Hyperliquid provider, TA indicators, signal validation, feature profiles |
| **4** | AI Evaluation | ✅ DONE | 4 AI models (ChatGPT, Gemini, Claude, DeepSeek), parallel evaluation, output validation |
| **5** | Polish & Hardening | ✅ DONE | Metrics, logging, DLQ, load testing, resource limits |

---

## Phase 1: E2E Skeleton ("Hello Lens") ✅ COMPLETED

**Goal**: Establish a working end-to-end flow from signal submission to WebSocket publish. All components are stubs, but the plumbing works.

### 1.1 Phase 1 Completion Criteria

Phase 1 is DONE only when:

- [x] `docker compose up` starts all services (gateway, worker, redis, postgres)
- [x] `POST /api/v1/signals` validates schema and enqueues to Redis Stream
- [x] Worker consumes from queue and writes `events.status = enriched` (stub enrichment)
- [x] Evaluation stub writes one `model_decisions` row with deterministic response
- [x] WebSocket broadcasts the stub decision to connected clients
- [x] `GET /health` returns ok
- [x] `GET /ready` shows queue lag and confirms redis/postgres connectivity

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
- [x] Initialize Redis Stream and consumer group on startup
- [x] Producer: enqueue signal with event_id, payload, timestamp
- [x] Consumer: read from stream with XREADGROUP

#### 1.3.4 Worker (Stub)
- [x] Consume from `lens:signals:pending`
- [x] **Stub Enrichment**: Add `mid_price` from signal's `entry_price` (no real provider)
- [x] Update `events.status = 'enriched'`, set `enriched_at`
- [x] **Stub Evaluation**: Return deterministic decision:
  ```json
  {
    "decision": "FOLLOW_ENTER",
    "confidence": 0.75,
    "reasons": ["bullish_trend", "ema_bullish_stack", "funding_favorable", "good_rr_ratio"],
    "model_meta": {"model_name": "chatgpt", "latency_ms": 10, "status": "SUCCESS"}
  }
  ```
- [x] Write to `model_decisions` table
- [x] Update `events.status = 'evaluated'`, set `evaluated_at`
- [x] Trigger WebSocket publish

#### 1.3.5 WebSocket Publisher (Minimal)
- [x] WebSocket endpoint at `/api/v1/ws/stream`
- [x] Accept connections (network-level security)
- [x] Broadcast all decisions to matching subscribers
- [x] Update `events.status = 'published'`, set `published_at`

#### 1.3.6 Health Endpoints
- [x] `GET /health` - Return {"status": "ok"}
- [x] `GET /ready` - Check Redis ping, Postgres connectivity, return queue depth
- [x] `GET /queue/depth` - Return current queue depths
- [x] `GET /metrics` - Prometheus metrics endpoint

#### 1.3.7 Docker Compose
- [x] Configure all services: gateway, worker, redis, postgres
- [x] Verify startup order with health checks
- [x] Test `docker compose up` brings up working system

### 1.4 Phase 1 Testing

- [x] Manual test: POST signal → verify WebSocket receives decision
- [x] Verify database has event with status='published'
- [x] Verify all lifecycle timestamps populated
- [x] Unit tests for all components (70+ tests passing)

---

## Phase 2: Signal Gateway (Production-Ready) ✅ COMPLETED

**Goal**: Harden the gateway with rate limiting and error handling.

### 2.1 Security (Completed)
- [x] Network-level security via Docker network isolation
- [x] No API keys required - all services internal only
- [x] External requests rejected at application level

### 2.2 Rate Limiting ✅
- [x] Redis-based sliding window limiter (implemented in `rate_limit.py`)
- [x] 60 req/min, burst 120 (configurable via env)
- [x] Per-client rate limiting logic
- [x] Rate limiter integrated into signal endpoint as dependency
- [x] Return 429 with Retry-After header on limit exceeded
- [x] Rate limit headers in response (X-RateLimit-Limit, X-RateLimit-Remaining)

### 2.4 Idempotency
- [x] Accept optional `idempotency_key` in request (X-Idempotency-Key header)
- [x] Reject duplicate signals with same idempotency_key
- [x] Return existing event_id for duplicates

### 2.5 Event Query Endpoints ✅
- [x] `GET /api/v1/events` - Full database query with filters
- [x] `GET /api/v1/events/{event_id}` - Event details with timeline/decisions
- [x] `GET /api/v1/events/{event_id}/status` - Status with timestamps

### 2.6 Error Handling
- [x] Basic structured error responses
- [x] Validation error details (Pydantic)
- [ ] Request ID tracking not implemented (optional)

### 2.7 Phase 2 Deliverables ✅
- [x] Network security working (no auth needed)
- [x] Rate limiting active on signal endpoint
- [x] Event query endpoints functional
- [x] Swagger UI functional for API testing

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

## Phase 4: AI Evaluation (Full) ✅ COMPLETED

**Goal**: Replace stub evaluation with real multi-model AI evaluation.

### 4.1 Model Interface ✅
- [x] Abstract base class for AI models (`BaseModelAdapter`)
- [x] `evaluate(prompt)` method returning `ModelResponse`
- [x] Timeout handling (configurable per model)
- [x] Token tracking (input/output tokens)
- [x] ModelStatus enum for error categorization

### 4.2 ChatGPT Implementation ✅
- [x] OpenAI SDK integration (`openai_adapter.py`)
- [x] Configurable model (gpt-4o default)
- [x] JSON mode for structured output
- [x] Error handling (rate limits, timeouts, API errors)

### 4.3 Gemini Implementation ✅
- [x] Google GenAI SDK integration (`google_adapter.py`)
- [x] Configurable model (gemini-1.5-pro default)
- [x] JSON mime type output enforcement
- [x] Error handling (quota, rate limits, connection errors)

### 4.4 Claude Implementation ✅ (NEW)
- [x] Anthropic SDK integration (`anthropic_adapter.py`)
- [x] Configurable model (claude-sonnet-4-20250514 default)
- [x] System prompt for JSON output
- [x] Error handling

### 4.5 DeepSeek Implementation ✅ (NEW)
- [x] OpenAI-compatible SDK (`deepseek_adapter.py`)
- [x] Configurable model (deepseek-chat default)
- [x] System prompt for JSON output
- [x] Error handling

### 4.6 Prompt Management ✅
- [x] Core + wrapper prompt structure (`prompt_loader.py`)
- [x] Prompt version tracking (version string returned)
- [x] Prompt hash for reproducibility (SHA-256)
- [x] Dynamic prompt rendering with enriched event data

### 4.7 Output Validation ✅
- [x] Parse model response as JSON (`_parse_json_response`)
- [x] Validate against ModelDecision schema (`validate_decision_output`)
- [x] Handle invalid outputs:
  - [x] Store raw response in `raw_response` column
  - [x] Mark status as error code
  - [x] Create fallback IGNORE decision

### 4.8 Parallel Evaluation ✅
- [x] Run all configured models concurrently (`asyncio.gather`)
- [x] Isolate failures (one model failing doesn't block others)
- [x] Collect results from all models
- [x] Write N decisions per event (one per model)

### 4.9 Evaluation Worker ✅
- [x] Consume from `lens:signals:enriched`
- [x] Load prompts for each model
- [x] Call models in parallel (when USE_REAL_AI=true)
- [x] Validate and store decisions
- [x] Trigger WebSocket publish for each decision
- [x] Stub mode retained for testing (USE_REAL_AI=false default)

### 4.10 Phase 4 Deliverables ✅
- [x] Multi-model evaluation working (4 providers)
- [x] Prompt versioning tracked in database
- [x] Invalid output handling with fallback
- [x] Per-model metrics (latency, tokens, errors)

---

## Phase 5: Polish & Hardening ✅ COMPLETED

**Goal**: Production-ready observability, performance, and deployment.

### 5.1 Prometheus Metrics ✅
- [x] Signal counters (received, enqueued, enriched, evaluated, published)
- [x] Latency histograms (enqueue, enrichment, evaluation)
- [x] Queue depth gauges
- [x] Error counters (DLQ, model errors, rejections)
- [x] WebSocket connection gauge
- [x] `/metrics` endpoint

### 5.2 Structured Logging ✅
- [x] JSON log format (configurable via LOG_FORMAT env)
- [x] event_id as trace ID across all logs
- [x] Stage transitions logged (RECEIVED → ENQUEUED → ENRICHED → ...)
- [x] Log levels configured via env (LOG_LEVEL)

### 5.3 Audit Endpoints ✅
- [x] `GET /api/v1/decisions` - Full database query with filters
- [x] `GET /api/v1/decisions/{id}` - Decision details with model meta
- [x] `GET /api/v1/dlq` - List DLQ entries with filters
- [x] `GET /api/v1/dlq/{id}` - DLQ entry details with payload
- [x] `POST /api/v1/dlq/{id}/retry` - Re-enqueue failed entry
- [x] `POST /api/v1/dlq/{id}/resolve` - Mark entry as resolved

### 5.4 WebSocket Enhancement ✅
- [x] Subscription filters (model, symbol, event_type)
- [x] Network-level security (Docker network isolation)
- [x] Ping/pong heartbeat
- [x] Connection limits

### 5.5 Performance Testing ✅
- [x] Load test script (target: 60 signals/min sustained) - `tests/load/load_test.py`
- [x] Verify p95 latencies:
  - End-to-end < 6s
  - Enrichment < 2s
  - Model evaluation < 3s
  - WebSocket fanout < 1s
- [x] Stress test queue depth

### 5.6 Docker Optimization ✅
- [x] Dockerfile configured (multi-stage build)
- [x] Multi-stage Dockerfile for smaller image
- [x] Resource limits configured (CPU/memory for all services)
- [x] Health check probes (gateway)
- [x] Graceful shutdown handling (SIGINT/SIGTERM handlers, stop_grace_period)

### 5.7 Phase 5 Deliverables ✅
- [x] Metrics and logging implemented
- [x] Audit query endpoints functional
- [x] Load test script created and verified
- [x] Production-ready Docker config with resource limits

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

### Phase 1 (E2E Skeleton) ✅ COMPLETE
- [x] Full signal flow working with stubs
- [x] Docker compose up → working system
- [x] Can POST signal, receive decision on WebSocket

### Phase 2 (Gateway) ✅ COMPLETE
- [x] Network security working (no auth needed)
- [x] Idempotency working
- [x] Rate limiting active on signal endpoint
- [x] Event query endpoints functional

### Phase 3 (Enrichment) ✅ COMPLETE
- [x] Real Hyperliquid data flowing
- [x] TA indicators verified correct
- [x] Quality flags detecting issues
- [x] Signal validation rejecting invalid signals

### Phase 4 (AI Evaluation) ✅ COMPLETE
- [x] ChatGPT + Gemini + Claude + DeepSeek producing real decisions
- [x] Invalid outputs handled gracefully (fallback to IGNORE)
- [x] Prompt versioning tracked (version + hash in DB)

### Phase 5 (Polish) ✅ COMPLETE
- [x] Metrics and structured logging implemented
- [x] WebSocket enhancements done
- [x] Audit query endpoints functional (decisions + DLQ)
- [x] Load test script created (`tests/load/load_test.py`)
- [x] Docker resource limits configured
- [x] Graceful shutdown handling

---

## Identified Gaps Summary

This section lists remaining gaps and recently resolved items.

### ✅ RESOLVED - Phase 2 & 5 Complete

All core MVP functionality is now implemented:

**Phase 2 (Gateway) - All Resolved:**
- Rate limiting integrated into signal endpoint (`api/v1/signals.py`)
- 429 responses with Retry-After header
- Rate limit headers in responses (X-RateLimit-*)
- Event query endpoints fully functional (`api/v1/events.py`)
- Decision query endpoints fully functional (`api/v1/decisions.py`)

**Phase 5 (Audit) - All Resolved:**
- DLQ list endpoint (`GET /api/v1/dlq`)
- DLQ detail endpoint (`GET /api/v1/dlq/{id}`)
- DLQ retry endpoint (`POST /api/v1/dlq/{id}/retry`)
- DLQ resolve endpoint (`POST /api/v1/dlq/{id}/resolve`)

### Low Priority (Optional for MVP)

| Gap | Location | Status |
|-----|----------|--------|
| Request ID Tracking | `api/` | Optional - Not implemented |
| Multi-stage Dockerfile | `Dockerfile` | ✅ Already implemented |
| Resource Limits | `docker-compose.yml` | ✅ Implemented |
| Graceful Shutdown | `workers/` | ✅ Implemented |
| Load Testing | `tests/load/` | ✅ Implemented |

### Optional (Nice to Have)

| Gap | Location | Description |
|-----|----------|-------------|
| Support/Resistance | `ta_calculator.py` | Level detection for full_v1 profile |
| Order Book Imbalance | `ta_calculator.py` | OBI calculation for full_v1 profile |

### Future Improvements (From Code Review)

These items were identified during code review as potential improvements for future iterations:

| Item | Location | Description |
|------|----------|-------------|
| Configurable Network Allowlist | `src/core/network.py` | Move hardcoded IP networks to env vars |
| Configurable Stream Names | `src/workers/*.py` | Move Redis stream/group names to settings |
| Configurable Profile Path | `src/services/enrichment/enrichment_service.py` | Make feature profiles YAML path configurable |
| Refactor Circular Imports | `src/api/v1/dlq.py` etc. | Clean up in-function imports used to avoid circular deps |

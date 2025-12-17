# API Reference

Base URL: `http://gateway:8000/api/v1` (from within Docker network)

## Security

**Network-Level Security**: All endpoints are protected by network isolation. Only requests from within the Docker network (`lens-network`) are accepted.

- No API keys required
- External requests are rejected with `403 Forbidden`
- Health endpoints (`/health`, `/ready`) are accessible for Docker health checks

---

## Signals

### Submit Signal

Submit a trading signal for analysis.

```
POST /signals
```

**Headers**:
| Header | Required | Description |
|--------|----------|-------------|
| `Content-Type` | Yes | `application/json` |
| `X-Idempotency-Key` | No | Prevent duplicate processing |

**Request Body**:
```json
{
  "event_type": "OPEN_SIGNAL",
  "symbol": "BTC",
  "signal_direction": "long",
  "entry_price": 42000.50,
  "size": 0.1,
  "liquidation_price": 38000.00,
  "ts_utc": "2024-01-15T10:30:00Z",
  "source": "strategy_alpha"
}
```

**Response** `201 Created`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ENQUEUED",
  "received_at": "2024-01-15T10:30:00.123Z"
}
```

**Error Responses**:

`400 Bad Request` - Invalid schema:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request body",
    "details": [
      { "field": "entry_price", "message": "must be greater than 0" }
    ]
  }
}
```

`403 Forbidden` - External network access:
```json
{
  "error": {
    "code": "FORBIDDEN",
    "message": "Access denied. This API is only accessible from internal network."
  }
}
```

`429 Too Many Requests` - Rate limited:
```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Rate limit exceeded",
    "retry_after": 45
  }
}
```

---

## Events

### List Events

Retrieve a list of submitted events.

```
GET /events
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | - | Filter by symbol |
| `event_type` | string | - | Filter by event type |
| `source` | string | - | Filter by source |
| `since` | datetime | - | Events after this time |
| `until` | datetime | - | Events before this time |
| `status` | string | - | Filter by status |
| `limit` | int | 50 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "event_type": "OPEN_SIGNAL",
      "symbol": "BTC",
      "signal_direction": "long",
      "entry_price": 42000.50,
      "size": 0.1,
      "status": "PUBLISHED",
      "source": "strategy_alpha",
      "received_at": "2024-01-15T10:30:00.123Z"
    }
  ],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

### Get Event

Retrieve a specific event with full details.

```
GET /events/{event_id}
```

**Response** `200 OK`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "event_type": "OPEN_SIGNAL",
  "symbol": "BTC",
  "signal_direction": "long",
  "entry_price": 42000.50,
  "size": 0.1,
  "liquidation_price": 38000.00,
  "ts_utc": "2024-01-15T10:30:00Z",
  "source": "strategy_alpha",
  "received_at": "2024-01-15T10:30:00.123Z",
  "status": "PUBLISHED",
  "timeline": [
    { "status": "RECEIVED", "timestamp": "2024-01-15T10:30:00.123Z" },
    { "status": "ENQUEUED", "timestamp": "2024-01-15T10:30:00.125Z" },
    { "status": "ENRICHED", "timestamp": "2024-01-15T10:30:01.850Z" },
    { "status": "MODEL_DONE", "timestamp": "2024-01-15T10:30:04.200Z", "details": { "model": "chatgpt" } },
    { "status": "MODEL_DONE", "timestamp": "2024-01-15T10:30:04.500Z", "details": { "model": "gemini" } },
    { "status": "PUBLISHED", "timestamp": "2024-01-15T10:30:04.510Z" }
  ],
  "enriched": {
    "feature_profile": "trend_follow_v1",
    "quality_flags": {
      "missing_data": [],
      "stale_data": [],
      "provider_errors": []
    }
  },
  "decisions": [
    {
      "model": "chatgpt",
      "decision": "FOLLOW_ENTER",
      "confidence": 0.78
    },
    {
      "model": "gemini",
      "decision": "FOLLOW_ENTER",
      "confidence": 0.72
    }
  ]
}
```

**Error Response** `404 Not Found`:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Event not found"
  }
}
```

### Get Event Status

Get the current processing status of an event.

```
GET /events/{event_id}/status
```

**Response** `200 OK`:
```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PUBLISHED",
  "current_stage": "COMPLETE",
  "duration_ms": 4387
}
```

---

## Decisions

### List Decisions

Query AI model decisions.

```
GET /decisions
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | string | - | Filter by model name |
| `symbol` | string | - | Filter by symbol |
| `event_type` | string | - | Filter by event type |
| `decision` | string | - | Filter by decision |
| `min_confidence` | float | - | Minimum confidence |
| `since` | datetime | - | Decisions after this time |
| `until` | datetime | - | Decisions before this time |
| `limit` | int | 50 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "dec-001",
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "symbol": "BTC",
      "event_type": "OPEN_SIGNAL",
      "model": "chatgpt",
      "decision": "FOLLOW_ENTER",
      "confidence": 0.78,
      "entry_plan": { "type": "limit", "offset_bps": -5 },
      "risk_plan": { "stop_method": "atr", "atr_multiple": 2.0 },
      "size_pct": 15,
      "reasons": ["bullish_ema_alignment", "positive_macd_crossover"],
      "evaluated_at": "2024-01-15T10:30:04.200Z"
    }
  ],
  "total": 500,
  "limit": 50,
  "offset": 0
}
```

### Get Decision

Get a specific decision by ID.

```
GET /decisions/{decision_id}
```

**Response** `200 OK`:
```json
{
  "id": "dec-001",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTC",
  "event_type": "OPEN_SIGNAL",
  "model": "chatgpt",
  "decision": "FOLLOW_ENTER",
  "confidence": 0.78,
  "entry_plan": { "type": "limit", "offset_bps": -5 },
  "risk_plan": { "stop_method": "atr", "atr_multiple": 2.0 },
  "size_pct": 15,
  "reasons": ["bullish_ema_alignment", "positive_macd_crossover"],
  "model_meta": {
    "model_name": "chatgpt",
    "model_version": "gpt-4o",
    "latency_ms": 1850,
    "status": "SUCCESS",
    "tokens_used": 1250
  },
  "evaluated_at": "2024-01-15T10:30:04.200Z"
}
```

---

## Health & Metrics

### Health Check

Liveness probe. Accessible from any IP (for Docker health checks).

```
GET /health
```

**Response** `200 OK`:
```json
{
  "status": "ok"
}
```

### Readiness Check

Readiness probe with dependency checks. Accessible from any IP.

```
GET /ready
```

**Response** `200 OK`:
```json
{
  "status": "ready",
  "dependencies": {
    "redis": "ok",
    "postgres": "ok"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Response** `503 Service Unavailable`:
```json
{
  "status": "not_ready",
  "dependencies": {
    "redis": "ok",
    "postgres": "error: connection refused"
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Metrics

Prometheus metrics endpoint.

```
GET /metrics
```

**Response**: Prometheus text format

---

## WebSocket

### Connect

From within the Docker network:

```
ws://gateway:8000/api/v1/ws/stream
```

### Messages

**Subscribe**:
```json
{
  "action": "subscribe",
  "filters": {
    "model": "chatgpt",
    "symbol": "BTC",
    "event_type": "OPEN_SIGNAL"
  }
}
```

**Unsubscribe**:
```json
{
  "action": "unsubscribe"
}
```

**Decision (server → client)**:
```json
{
  "type": "decision",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "symbol": "BTC",
  "event_type": "OPEN_SIGNAL",
  "model": "chatgpt",
  "decision": {
    "decision": "FOLLOW_ENTER",
    "confidence": 0.78,
    "entry_plan": { "type": "limit", "offset_bps": -5 },
    "risk_plan": { "stop_method": "atr", "atr_multiple": 2.0 },
    "size_pct": 15,
    "reasons": ["bullish_ema_alignment"]
  },
  "published_at": "2024-01-15T10:30:04.510Z"
}
```

**Error (server → client)**:
```json
{
  "type": "error",
  "code": "INVALID_FILTER",
  "message": "Unknown model: invalid_model"
}
```

**Heartbeat**:
```json
{ "type": "ping" }
{ "type": "pong" }
```

---

## Dead Letter Queue (DLQ)

### List DLQ Entries

Query failed processing entries.

```
GET /dlq
```

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `stage` | string | - | Filter by stage (enqueue\|enrich\|evaluate\|publish) |
| `reason_code` | string | - | Filter by reason code |
| `event_id` | string | - | Filter by event ID |
| `resolved` | boolean | - | Filter by resolution status |
| `since` | datetime | - | Entries after this time |
| `until` | datetime | - | Entries before this time |
| `limit` | int | 50 | Max results (1-100) |
| `offset` | int | 0 | Pagination offset |

**Response** `200 OK`:
```json
{
  "items": [
    {
      "id": "dlq-001",
      "event_id": "550e8400-e29b-41d4-a716-446655440000",
      "stage": "enrich",
      "reason_code": "PROVIDER_ERROR",
      "error_message": "Hyperliquid API timeout",
      "retry_count": 3,
      "created_at": "2024-01-15T10:30:00Z",
      "resolved_at": null
    }
  ],
  "total": 15,
  "limit": 50,
  "offset": 0
}
```

### Get DLQ Entry

Get full details of a DLQ entry including payload.

```
GET /dlq/{dlq_id}
```

**Response** `200 OK`:
```json
{
  "id": "dlq-001",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "stage": "enrich",
  "reason_code": "PROVIDER_ERROR",
  "error_message": "Hyperliquid API returned 503 Service Unavailable",
  "payload": {
    "symbol": "BTC",
    "entry_price": 42000.50,
    "signal_direction": "long"
  },
  "retry_count": 3,
  "last_retry_at": "2024-01-15T10:35:00Z",
  "resolved_at": null,
  "resolution_note": null,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Retry DLQ Entry

Re-enqueue a failed entry for processing.

```
POST /dlq/{dlq_id}/retry
```

**Response** `200 OK`:
```json
{
  "id": "dlq-001",
  "status": "retrying",
  "message": "Entry re-enqueued for enrich processing",
  "retry_count": 4
}
```

**Error Response** `400 Bad Request`:
```json
{
  "detail": "Cannot retry a resolved DLQ entry"
}
```

### Resolve DLQ Entry

Mark an entry as manually resolved.

```
POST /dlq/{dlq_id}/resolve
```

**Request Body**:
```json
{
  "resolution_note": "Manually fixed data issue and re-submitted signal"
}
```

**Response** `200 OK`:
```json
{
  "id": "dlq-001",
  "status": "resolved",
  "resolved_at": "2024-01-15T11:00:00Z"
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request body or parameters |
| `FORBIDDEN` | 403 | Access denied (external network) |
| `NOT_FOUND` | 404 | Resource not found |
| `RATE_LIMITED` | 429 | Rate limit exceeded |
| `INTERNAL_ERROR` | 500 | Internal server error |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |

# Data Contracts

This document defines all data schemas used in SigmaPilot Lens.

## 1. Input Schema: TradingSignalEvent

This is the primary input contract for signal ingestion.

### Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "TradingSignalEvent",
  "type": "object",
  "required": [
    "event_type",
    "symbol",
    "signal_direction",
    "entry_price",
    "size",
    "liquidation_price",
    "ts_utc",
    "source"
  ],
  "properties": {
    "event_type": {
      "type": "string",
      "enum": ["OPEN_SIGNAL", "CLOSE_SIGNAL"],
      "description": "Type of trading signal"
    },
    "symbol": {
      "type": "string",
      "minLength": 1,
      "maxLength": 20,
      "description": "Trading symbol (e.g., BTC, ETH, SOL)"
    },
    "signal_direction": {
      "type": "string",
      "enum": ["long", "short", "close_long", "close_short"],
      "description": "Direction of the signal"
    },
    "entry_price": {
      "type": "number",
      "exclusiveMinimum": 0,
      "description": "Entry price for the position"
    },
    "size": {
      "type": "number",
      "exclusiveMinimum": 0,
      "description": "Position size"
    },
    "liquidation_price": {
      "type": "number",
      "exclusiveMinimum": 0,
      "description": "Liquidation price level"
    },
    "ts_utc": {
      "type": "string",
      "format": "date-time",
      "description": "Signal timestamp in ISO 8601 format"
    },
    "source": {
      "type": "string",
      "minLength": 1,
      "maxLength": 100,
      "description": "Source identifier of the signal"
    }
  },
  "additionalProperties": false
}
```

### Example

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

### Validation Rules

| Field | Rule |
|-------|------|
| event_type | Must be exactly "OPEN_SIGNAL" or "CLOSE_SIGNAL" |
| symbol | 1-20 characters, alphanumeric |
| signal_direction | Must match event_type logic |
| entry_price | Positive number, max 8 decimal places |
| size | Positive number, max 8 decimal places |
| liquidation_price | Positive number, must be valid for direction |
| ts_utc | Valid ISO 8601 datetime |
| source | 1-100 characters |

---

## 2. Internal Schema: EnrichedSignalEvent

Produced by the enrichment worker, consumed by AI evaluation.

### Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "EnrichedSignalEvent",
  "type": "object",
  "required": [
    "event_id",
    "original",
    "market",
    "ta",
    "constraints",
    "quality_flags",
    "enriched_at"
  ],
  "properties": {
    "event_id": {
      "type": "string",
      "format": "uuid"
    },
    "original": {
      "$ref": "#/definitions/TradingSignalEvent"
    },
    "market": {
      "$ref": "#/definitions/MarketData"
    },
    "ta": {
      "$ref": "#/definitions/TAData"
    },
    "levels": {
      "$ref": "#/definitions/LevelsData"
    },
    "derivs": {
      "$ref": "#/definitions/DerivsData"
    },
    "constraints": {
      "$ref": "#/definitions/Constraints"
    },
    "quality_flags": {
      "$ref": "#/definitions/QualityFlags"
    },
    "enriched_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

### Sub-Schemas

#### MarketData

```json
{
  "title": "MarketData",
  "type": "object",
  "required": ["mid", "spread_bps", "price_drift_bps_from_entry"],
  "properties": {
    "mid": {
      "type": "number",
      "description": "Mid price"
    },
    "bid": {
      "type": "number",
      "description": "Best bid"
    },
    "ask": {
      "type": "number",
      "description": "Best ask"
    },
    "spread_bps": {
      "type": "number",
      "description": "Spread in basis points"
    },
    "price_drift_bps_from_entry": {
      "type": "number",
      "description": "Price drift from entry in basis points"
    },
    "obi_buckets": {
      "type": "object",
      "description": "Order book imbalance by depth",
      "properties": {
        "1pct": { "type": "number" },
        "2pct": { "type": "number" },
        "5pct": { "type": "number" }
      }
    },
    "fetched_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

#### TAData

```json
{
  "title": "TAData",
  "type": "object",
  "required": ["timeframes"],
  "properties": {
    "timeframes": {
      "type": "object",
      "additionalProperties": {
        "$ref": "#/definitions/TimeframeIndicators"
      }
    }
  }
}
```

#### TimeframeIndicators

```json
{
  "title": "TimeframeIndicators",
  "type": "object",
  "properties": {
    "ema": {
      "type": "object",
      "properties": {
        "ema_9": { "type": "number" },
        "ema_21": { "type": "number" },
        "ema_50": { "type": "number" }
      }
    },
    "macd": {
      "type": "object",
      "properties": {
        "macd_line": { "type": "number" },
        "signal_line": { "type": "number" },
        "histogram": { "type": "number" }
      }
    },
    "rsi": {
      "type": "number",
      "minimum": 0,
      "maximum": 100
    },
    "atr": {
      "type": "number",
      "minimum": 0
    }
  }
}
```

#### LevelsData (Optional)

```json
{
  "title": "LevelsData",
  "type": "object",
  "properties": {
    "supports": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "price": { "type": "number" },
          "strength": { "type": "number" }
        }
      },
      "maxItems": 5
    },
    "resistances": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "price": { "type": "number" },
          "strength": { "type": "number" }
        }
      },
      "maxItems": 5
    }
  }
}
```

#### DerivsData (Optional)

```json
{
  "title": "DerivsData",
  "type": "object",
  "properties": {
    "funding_rate": {
      "type": "number",
      "description": "Current funding rate"
    },
    "predicted_funding": {
      "type": "number",
      "description": "Predicted next funding rate"
    },
    "open_interest": {
      "type": "number",
      "description": "Open interest in USD"
    },
    "oi_change_24h_pct": {
      "type": "number",
      "description": "OI change in last 24h"
    },
    "mark_price": {
      "type": "number"
    },
    "oracle_price": {
      "type": "number"
    }
  }
}
```

#### Constraints

```json
{
  "title": "Constraints",
  "type": "object",
  "properties": {
    "min_hold_minutes": {
      "type": "integer",
      "minimum": 0
    },
    "one_direction_only": {
      "type": "boolean"
    },
    "max_trades_per_hour": {
      "type": "integer",
      "minimum": 1
    },
    "max_position_size_pct": {
      "type": "number",
      "minimum": 0,
      "maximum": 100
    }
  }
}
```

#### QualityFlags

```json
{
  "title": "QualityFlags",
  "type": "object",
  "properties": {
    "missing_data": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of missing data fields"
    },
    "stale_data": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of stale data fields"
    },
    "out_of_range": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of out-of-range values"
    },
    "provider_errors": {
      "type": "array",
      "items": { "type": "string" },
      "description": "List of provider error messages"
    }
  }
}
```

### Example

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "original": {
    "event_type": "OPEN_SIGNAL",
    "symbol": "BTC",
    "signal_direction": "long",
    "entry_price": 42000.50,
    "size": 0.1,
    "liquidation_price": 38000.00,
    "ts_utc": "2024-01-15T10:30:00Z",
    "source": "strategy_alpha"
  },
  "market": {
    "mid": 42050.25,
    "bid": 42049.00,
    "ask": 42051.50,
    "spread_bps": 0.59,
    "price_drift_bps_from_entry": 11.84,
    "obi_buckets": {
      "1pct": 0.15,
      "2pct": 0.08,
      "5pct": -0.02
    },
    "fetched_at": "2024-01-15T10:30:01Z"
  },
  "ta": {
    "timeframes": {
      "15m": {
        "ema": { "ema_9": 42010.5, "ema_21": 41980.2, "ema_50": 41850.0 },
        "macd": { "macd_line": 45.2, "signal_line": 38.1, "histogram": 7.1 },
        "rsi": 58.5,
        "atr": 180.5
      },
      "1h": {
        "ema": { "ema_9": 41950.0, "ema_21": 41800.5, "ema_50": 41500.0 },
        "macd": { "macd_line": 120.5, "signal_line": 95.2, "histogram": 25.3 },
        "rsi": 62.1,
        "atr": 350.2
      },
      "4h": {
        "ema": { "ema_9": 41700.0, "ema_21": 41200.0, "ema_50": 40500.0 },
        "macd": { "macd_line": 350.0, "signal_line": 280.0, "histogram": 70.0 },
        "rsi": 65.8,
        "atr": 850.0
      }
    }
  },
  "derivs": {
    "funding_rate": 0.0001,
    "predicted_funding": 0.00012,
    "open_interest": 5200000000,
    "oi_change_24h_pct": 2.5,
    "mark_price": 42048.50,
    "oracle_price": 42050.00
  },
  "constraints": {
    "min_hold_minutes": 15,
    "one_direction_only": true,
    "max_trades_per_hour": 4,
    "max_position_size_pct": 25
  },
  "quality_flags": {
    "missing_data": [],
    "stale_data": [],
    "out_of_range": [],
    "provider_errors": []
  },
  "enriched_at": "2024-01-15T10:30:02Z"
}
```

---

## 3. Output Schema: ModelDecision

Produced by AI evaluation, published via WebSocket.

### Schema Definition

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "ModelDecision",
  "type": "object",
  "required": [
    "decision",
    "confidence",
    "reasons",
    "model_meta"
  ],
  "properties": {
    "decision": {
      "type": "string",
      "enum": ["FOLLOW_ENTER", "IGNORE", "FOLLOW_EXIT", "HOLD", "TIGHTEN_STOP"],
      "description": "The AI model's recommendation"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1,
      "description": "Confidence score (0-1)"
    },
    "entry_plan": {
      "$ref": "#/definitions/EntryPlan"
    },
    "risk_plan": {
      "$ref": "#/definitions/RiskPlan"
    },
    "size_pct": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Suggested position size percentage"
    },
    "reasons": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1,
      "description": "Short reason tags"
    },
    "model_meta": {
      "$ref": "#/definitions/ModelMeta"
    }
  }
}
```

### Sub-Schemas

#### EntryPlan

```json
{
  "title": "EntryPlan",
  "type": "object",
  "required": ["type"],
  "properties": {
    "type": {
      "type": "string",
      "enum": ["market", "limit"]
    },
    "offset_bps": {
      "type": "number",
      "description": "Offset from current price in basis points (for limit orders)"
    }
  }
}
```

#### RiskPlan

```json
{
  "title": "RiskPlan",
  "type": "object",
  "required": ["stop_method"],
  "properties": {
    "stop_method": {
      "type": "string",
      "enum": ["fixed", "atr", "trailing"]
    },
    "stop_level": {
      "type": "number",
      "description": "Fixed stop price level"
    },
    "atr_multiple": {
      "type": "number",
      "minimum": 0.5,
      "maximum": 10,
      "description": "ATR multiple for stop calculation"
    },
    "trail_pct": {
      "type": "number",
      "minimum": 0,
      "maximum": 100,
      "description": "Trailing stop percentage"
    }
  }
}
```

#### ModelMeta

```json
{
  "title": "ModelMeta",
  "type": "object",
  "required": ["model_name", "latency_ms", "status"],
  "properties": {
    "model_name": {
      "type": "string",
      "description": "Name of the AI model"
    },
    "model_version": {
      "type": "string",
      "description": "Model version identifier"
    },
    "latency_ms": {
      "type": "integer",
      "minimum": 0,
      "description": "Evaluation latency in milliseconds"
    },
    "status": {
      "type": "string",
      "enum": ["SUCCESS", "TIMEOUT", "API_ERROR", "SCHEMA_ERROR", "RATE_LIMITED"],
      "description": "Evaluation status"
    },
    "error_code": {
      "type": "string",
      "description": "Error code if status is not SUCCESS"
    },
    "error_message": {
      "type": "string",
      "description": "Error message if status is not SUCCESS"
    },
    "tokens_used": {
      "type": "integer",
      "description": "Total tokens used (input + output)"
    }
  }
}
```

### Example (Success)

```json
{
  "decision": "FOLLOW_ENTER",
  "confidence": 0.78,
  "entry_plan": {
    "type": "limit",
    "offset_bps": -5
  },
  "risk_plan": {
    "stop_method": "atr",
    "atr_multiple": 2.0
  },
  "size_pct": 15,
  "reasons": [
    "bullish_ema_alignment",
    "positive_macd_crossover",
    "neutral_funding",
    "acceptable_spread"
  ],
  "model_meta": {
    "model_name": "chatgpt",
    "model_version": "gpt-4o",
    "latency_ms": 1850,
    "status": "SUCCESS",
    "tokens_used": 1250
  }
}
```

### Example (Failure)

```json
{
  "decision": "IGNORE",
  "confidence": 0,
  "reasons": ["model_error"],
  "model_meta": {
    "model_name": "gemini",
    "model_version": "gemini-1.5-pro",
    "latency_ms": 30000,
    "status": "TIMEOUT",
    "error_code": "TIMEOUT",
    "error_message": "Model evaluation timed out after 30000ms"
  }
}
```

---

## 4. API Response Schemas

### Signal Submission Response

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "ENQUEUED",
  "received_at": "2024-01-15T10:30:00.123Z"
}
```

### Event Status Response

```json
{
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "PUBLISHED",
  "timeline": [
    { "status": "RECEIVED", "timestamp": "2024-01-15T10:30:00.123Z" },
    { "status": "ENQUEUED", "timestamp": "2024-01-15T10:30:00.125Z" },
    { "status": "ENRICHED", "timestamp": "2024-01-15T10:30:01.850Z" },
    { "status": "MODEL_DONE", "timestamp": "2024-01-15T10:30:04.200Z", "details": { "model": "chatgpt" } },
    { "status": "MODEL_DONE", "timestamp": "2024-01-15T10:30:04.500Z", "details": { "model": "gemini" } },
    { "status": "PUBLISHED", "timestamp": "2024-01-15T10:30:04.510Z" }
  ],
  "decisions": [
    { "model": "chatgpt", "decision": "FOLLOW_ENTER", "confidence": 0.78 },
    { "model": "gemini", "decision": "FOLLOW_ENTER", "confidence": 0.72 }
  ]
}
```

### Error Response

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

---

## 5. WebSocket Message Schemas

### Subscribe Message

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

### Decision Broadcast

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
    "reasons": ["bullish_ema_alignment", "positive_macd_crossover"]
  },
  "published_at": "2024-01-15T10:30:04.510Z"
}
```

### Error Message

```json
{
  "type": "error",
  "code": "INVALID_FILTER",
  "message": "Unknown model: invalid_model"
}
```

### Heartbeat

```json
{
  "type": "ping"
}
```

```json
{
  "type": "pong"
}
```

---

## 6. DLQ Entry Schema

```json
{
  "id": "dlq-001",
  "event_id": "550e8400-e29b-41d4-a716-446655440000",
  "stage": "ENRICHMENT",
  "error_code": "PROVIDER_ERROR",
  "error_message": "Hyperliquid API returned 503",
  "payload": { /* original message */ },
  "retry_count": 5,
  "created_at": "2024-01-15T10:30:15.000Z"
}
```

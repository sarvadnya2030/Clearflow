"""Configuration for diagnostic agents."""

import os

# Service URLs
MCP_URL = os.getenv("MCP_URL", "http://localhost:8087")
ES_URL = os.getenv("ES_URL", "http://localhost:9200")
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:8080")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Agent configuration
MODEL_DIAGNOSTIC = "claude-haiku-4-5-20251001"  # Fast execution
MODEL_COMPLEX = "claude-sonnet-4-6"  # For complex cascade analysis
MAX_TOKENS_DIAGNOSTIC = 4096
MAX_TOKENS_COMPLEX = 8192

# Polling intervals
ALERT_POLL_INTERVAL_SECONDS = 30
CASCADE_DETECTION_WINDOW_MINUTES = 15

# Cascade detection thresholds
CASCADE_ERROR_COUNT_THRESHOLD = 5
CASCADE_SERVICE_COUNT_THRESHOLD = 3

# Redis for human-in-the-loop
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "clearflow123")

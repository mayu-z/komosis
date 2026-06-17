"""
Centralised configuration for the RIFT Agent service.

Every knob is driven by an environment variable with a sensible default.
"""
from __future__ import annotations

import os
from pathlib import Path


# ── LLM / AI (Groq — round-robin across multiple keys) ─────
GROQ_API_KEYS: list[str] = [
    k.strip()
    for k in os.getenv("GROQ_API_KEYS", "").split(",")
    if k.strip()
]
GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE: float = float(os.getenv("GROQ_TEMPERATURE", "0.2"))

# Legacy OpenAI — kept for backward compat but unused by default
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TEMPERATURE: float = float(os.getenv("OPENAI_TEMPERATURE", "0.2"))

# ── Infrastructure ──────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgres://rift:rift_secret@postgres:5432/rift",
)
REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
GATEWAY_BASE_URL: str = os.getenv("GATEWAY_BASE_URL", "http://gateway:3000")

# ── Agent behaviour ─────────────────────────────────────────
MAX_ITERATIONS: int = int(os.getenv("MAX_ITERATIONS", "5"))
POLL_CI_INTERVAL_SECS: int = int(os.getenv("POLL_CI_INTERVAL_SECS", "10"))
POLL_CI_TIMEOUT_SECS: int = int(os.getenv("POLL_CI_TIMEOUT_SECS", "300"))

# ── Filesystem ──────────────────────────────────────────────
REPOS_DIR: Path = Path(os.getenv("REPOS_DIR", "/tmp/repos"))
OUTPUTS_DIR: Path = Path(os.getenv("OUTPUTS_DIR", "/app/outputs"))

# ── Score formula constants (from SOURCE_OF_TRUTH §12) ──────
SCORE_BASE: int = 100
SCORE_SPEED_BONUS: int = 10
SCORE_SPEED_THRESHOLD_SECS: int = 300
SCORE_EFFICIENCY_PENALTY_PER_COMMIT: int = 2
SCORE_EFFICIENCY_FREE_COMMITS: int = 20

# ── Feature flags (match models.FeatureFlags defaults) ──────
DEFAULT_FEATURE_FLAGS: dict[str, bool] = {
    "ENABLE_KB_LOOKUP": True,
    "ENABLE_SPECULATIVE_BRANCHES": False,
    "ENABLE_ADVERSARIAL_TESTS": True,
    "ENABLE_CAUSAL_GRAPH": True,
    "ENABLE_PROVENANCE_PASS": True,
}

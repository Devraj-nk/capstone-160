from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "crisis_monitor")

QUEUE_MAX_SIZE = int(os.getenv("QUEUE_MAX_SIZE", "500"))

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip()
]

# auto = fine-tuned Hugging Face models if torch/transformers are installed,
# otherwise the offline heuristic stand-ins; hf / offline force one or the other.
MODEL_BACKEND = os.getenv("MODEL_BACKEND", "auto")

# Background worker that drains the ingestion queue through the full pipeline.
PIPELINE_WORKER_ENABLED = os.getenv("PIPELINE_WORKER_ENABLED", "true").lower() in ("1", "true", "yes")
PIPELINE_POLL_INTERVAL = float(os.getenv("PIPELINE_POLL_INTERVAL", "0.5"))

# Auto-escalation: a pending situation of this band is routed (marked unverified)
# when no reviewer decides within this many minutes. 0 disables a band; bands
# not listed (Medium, Low) always wait for a reviewer, as do likely-fake ones.
AUTO_ROUTE_MINUTES = {
    "Critical": float(os.getenv("AUTO_ROUTE_CRITICAL_MINUTES", "2")),
    "High": float(os.getenv("AUTO_ROUTE_HIGH_MINUTES", "10")),
}
ESCALATION_CHECK_SECONDS = float(os.getenv("ESCALATION_CHECK_SECONDS", "10"))

# Analytics.
# Time zone for "hour of day" and daily reports (minutes east of UTC; IST = 330).
ANALYTICS_TZ_OFFSET_MINUTES = int(os.getenv("ANALYTICS_TZ_OFFSET_MINUTES", "330"))
# A routed ticket not acknowledged within this long counts as overdue on the
# dashboard (display only — nothing is escalated automatically).
ACK_LIMIT_MINUTES = {"Critical": 15.0, "High": 60.0, "Medium": 240.0, "Low": 1440.0}

# Storage privacy / retention.
AUTHOR_HASH_SALT = os.getenv("AUTHOR_HASH_SALT", "change-me")  # set a secret value in .env
DROPPED_RETENTION_DAYS = int(os.getenv("DROPPED_RETENTION_DAYS", "7"))

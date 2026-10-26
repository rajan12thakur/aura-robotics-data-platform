"""Shared path and environment configuration for the Django application."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("AURA_DATA_DIR", ROOT / "data")).resolve()
MEDIA_DIR = Path(os.getenv("AURA_MEDIA_DIR", DATA_DIR / "media")).resolve()
OUTPUT_DIR = Path(os.getenv("AURA_OUTPUT_DIR", ROOT / "output")).resolve()
MAX_UPLOAD_MB = int(os.getenv("AURA_MAX_UPLOAD_MB", "250"))
APP_NAME = os.getenv("AURA_APP_NAME", "AURA")
DEFAULT_REVIEWER = os.getenv("AURA_DEFAULT_REVIEWER", "Local Reviewer")
FRONTEND_ORIGIN = os.getenv("AURA_FRONTEND_ORIGIN", "http://localhost:5173")
FRAME_SAMPLE_LIMIT = max(1, int(os.getenv("AURA_FRAME_SAMPLE_LIMIT", "100")))
RAG_MAX_PDF_MB = max(1, int(os.getenv("AURA_RAG_MAX_PDF_MB", "25")))
VECTOR_STORE_DIR = Path(os.getenv("AURA_VECTOR_STORE_DIR", DATA_DIR / "vector_store")).resolve()
VISION_ENABLED = os.getenv("AURA_VISION_ENABLED", "false").lower() == "true"
VISION_MODEL = os.getenv("AURA_VISION_MODEL", "")
VISION_WEIGHTS_PATH = os.getenv("AURA_VISION_WEIGHTS_PATH", "")

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "reports").mkdir(parents=True, exist_ok=True)
(OUTPUT_DIR / "exports").mkdir(parents=True, exist_ok=True)

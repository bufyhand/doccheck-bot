from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
TEMP_DIR = PROJECT_ROOT / "temp"
UPLOAD_DIR = TEMP_DIR / "uploads"
REPORT_DIR = TEMP_DIR / "reports"
CATALOG_PATH = DATA_DIR / "catalog_index.json"


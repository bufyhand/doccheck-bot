from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
TEMP_DIR = PROJECT_ROOT / "temp"
UPLOAD_DIR = TEMP_DIR / "uploads"
REPORT_DIR = TEMP_DIR / "reports"

_env_catalog_path = os.getenv("CATALOG_PATH")
CATALOG_CANDIDATES = [
    Path(_env_catalog_path) if _env_catalog_path else None,
    DATA_DIR / "catalog_index.json",
    ASSETS_DIR / "catalog_index.json",
]
CATALOG_CANDIDATES = [path for path in CATALOG_CANDIDATES if path is not None]
CATALOG_PATH = next(
    (path for path in CATALOG_CANDIDATES if path.exists()),
    CATALOG_CANDIDATES[0],
)

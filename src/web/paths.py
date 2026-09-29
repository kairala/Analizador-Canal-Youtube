# src/web/paths.py
from pathlib import Path

import platformdirs


def app_data_dir() -> Path:
    path = Path(platformdirs.user_data_dir("yt-data-extractor"))
    path.mkdir(parents=True, exist_ok=True)
    return path

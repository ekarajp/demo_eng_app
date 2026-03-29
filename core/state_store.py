from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATE_FILE = Path(__file__).resolve().parent.parent / ".streamlit" / "workspace_state.json"


def load_state(allowed_keys: set[str]) -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key in allowed_keys}


def save_state(state: dict[str, Any]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # Persistence is best-effort. The app should still work without it.
        return

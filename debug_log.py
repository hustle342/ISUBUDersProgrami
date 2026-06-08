"""Debug mode NDJSON logger (session 876524)."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

_LOG_PATH = Path(__file__).resolve().parent / "debug-876524.log"
_SESSION = "876524"


def debug_log(
    location: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    hypothesis_id: str = "",
    run_id: str = "pre-fix",
) -> None:
    # #region agent log
    try:
        payload = {
            "sessionId": _SESSION,
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(time.time() * 1000),
        }
        with _LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion

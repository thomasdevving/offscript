"""In-process latency metrics (p50/p95) and structured logging helpers.

Every measurement is recorded from a real code path; nothing here is synthetic.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

import numpy as np

_lock = threading.Lock()
_samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=5000))


def record(name: str, ms: float) -> None:
    with _lock:
        _samples[name].append(float(ms))


@contextmanager
def timer(name: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        record(name, (time.perf_counter() - t0) * 1000)


def summary() -> dict[str, dict[str, float]]:
    out = {}
    with _lock:
        items = {k: list(v) for k, v in _samples.items()}
    for k, v in sorted(items.items()):
        if not v:
            continue
        arr = np.array(v)
        out[k] = {"count": len(v), "p50_ms": round(float(np.percentile(arr, 50)), 3),
                  "p95_ms": round(float(np.percentile(arr, 95)), 3), "max_ms": round(float(arr.max()), 3),
                  "mean_ms": round(float(arr.mean()), 3)}
    return out


def reset() -> None:
    with _lock:
        _samples.clear()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": round(record.created, 3), "level": record.levelname, "logger": record.name,
                   "msg": record.getMessage()}
        for key in ("correlation_id", "analysis_id", "match_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers = [handler]
    root.setLevel(level)
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("azure").setLevel("WARNING")
    logging.getLogger("agent_framework").setLevel("WARNING")

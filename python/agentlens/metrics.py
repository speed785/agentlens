from __future__ import annotations

from typing import Any, Dict

from .observability import get_metrics_collector


def get_metrics() -> Dict[str, Any]:
    return get_metrics_collector().snapshot()


def reset_metrics() -> None:
    get_metrics_collector().reset()


def export_prometheus() -> str:
    return get_metrics_collector().export()

from __future__ import annotations

import importlib
import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional


@dataclass
class ObservabilityConfig:
    log_level: str = "INFO"
    enable_metrics: bool = True
    enable_otel: bool = False
    debug_mode: bool = False


class AgentLensLogger:
    def __init__(self, config: Optional[ObservabilityConfig] = None, logger_name: str = "agentlens") -> None:
        self.config = config or ObservabilityConfig()
        self._logger = logging.getLogger(logger_name)
        self._logger.setLevel(getattr(logging, self.config.log_level.upper(), logging.INFO))
        self._logger.propagate = False

        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter("%(message)s"))
            self._logger.addHandler(handler)

    def _emit(self, level: int, event: str, **payload: Any) -> None:
        message: Dict[str, Any] = {
            "event": event,
            "timestamp_ms": int(time.time() * 1000),
            **payload,
        }
        self._logger.log(level, json.dumps(message, default=str))

    def call_started(self, **payload: Any) -> None:
        self._emit(logging.INFO, "call_started", **payload)

    def call_completed(self, **payload: Any) -> None:
        self._emit(logging.INFO, "call_completed", **payload)

    def call_failed(self, **payload: Any) -> None:
        self._emit(logging.ERROR, "call_failed", **payload)

    def chain_started(self, **payload: Any) -> None:
        self._emit(logging.INFO, "chain_started", **payload)

    def chain_completed(self, **payload: Any) -> None:
        self._emit(logging.INFO, "chain_completed", **payload)

    def debug_trace(self, **payload: Any) -> None:
        if self.config.debug_mode:
            self._emit(logging.DEBUG, "debug_trace", **payload)


class MetricsCollector:
    _LATENCY_BUCKETS_MS = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf"))

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self.call_count = 0
            self.error_count = 0
            self.total_latency_ms = 0.0
            self.token_totals = {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }
            self._latency_bucket_counts = {bucket: 0 for bucket in self._LATENCY_BUCKETS_MS}

    def record(self, *, success: bool, latency_ms: float, token_usage: Optional[Dict[str, int]] = None) -> None:
        with self._lock:
            self.call_count += 1
            if not success:
                self.error_count += 1
            self.total_latency_ms += float(latency_ms)

            usage = token_usage or {}
            self.token_totals["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
            self.token_totals["completion_tokens"] += int(usage.get("completion_tokens", 0) or 0)
            self.token_totals["total_tokens"] += int(usage.get("total_tokens", 0) or 0)

            for bucket in self._LATENCY_BUCKETS_MS:
                if latency_ms <= bucket:
                    self._latency_bucket_counts[bucket] += 1
                    break

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "call_count": self.call_count,
                "error_count": self.error_count,
                "total_latency_ms": round(self.total_latency_ms, 3),
                "token_totals": dict(self.token_totals),
                "latency_buckets_ms": {
                    ("+Inf" if b == float("inf") else str(int(b))): c
                    for b, c in self._latency_bucket_counts.items()
                },
            }

    def export(self) -> str:
        snapshot = self.snapshot()
        bucket_items = snapshot["latency_buckets_ms"].items()

        lines = [
            "# HELP agentlens_call_count_total Total number of profiled calls",
            "# TYPE agentlens_call_count_total counter",
            f"agentlens_call_count_total {snapshot['call_count']}",
            "# HELP agentlens_error_count_total Total number of failed profiled calls",
            "# TYPE agentlens_error_count_total counter",
            f"agentlens_error_count_total {snapshot['error_count']}",
            "# HELP agentlens_latency_ms_sum Sum of call latency in milliseconds",
            "# TYPE agentlens_latency_ms_sum counter",
            f"agentlens_latency_ms_sum {snapshot['total_latency_ms']}",
            "# HELP agentlens_tokens_total Total LLM token usage",
            "# TYPE agentlens_tokens_total counter",
            f"agentlens_tokens_total{{kind=\"prompt\"}} {snapshot['token_totals']['prompt_tokens']}",
            f"agentlens_tokens_total{{kind=\"completion\"}} {snapshot['token_totals']['completion_tokens']}",
            f"agentlens_tokens_total{{kind=\"total\"}} {snapshot['token_totals']['total_tokens']}",
            "# HELP agentlens_latency_ms_bucket Call latency histogram buckets",
            "# TYPE agentlens_latency_ms_bucket histogram",
        ]

        cumulative = 0
        for boundary, value in bucket_items:
            cumulative += int(value)
            lines.append(f"agentlens_latency_ms_bucket{{le=\"{boundary}\"}} {cumulative}")

        lines.append(f"agentlens_latency_ms_count {snapshot['call_count']}")
        return "\n".join(lines) + "\n"


class OTelSpanContext:
    def __init__(self, config: Optional[ObservabilityConfig] = None) -> None:
        self.config = config or ObservabilityConfig()
        self._tracer = None

        if self.config.enable_otel:
            try:
                trace = importlib.import_module("opentelemetry.trace")
                self._tracer = trace.get_tracer("agentlens")
            except Exception:
                self._tracer = None

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        if self._tracer is None:
            yield
            return

        with self._tracer.start_as_current_span(name):
            yield


_default_config = ObservabilityConfig()
_GLOBAL_METRICS = MetricsCollector()


def set_default_observability(config: ObservabilityConfig) -> None:
    global _default_config
    _default_config = config


def get_default_observability() -> ObservabilityConfig:
    return _default_config


def get_metrics_collector() -> MetricsCollector:
    return _GLOBAL_METRICS

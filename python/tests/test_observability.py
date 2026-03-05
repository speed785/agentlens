from __future__ import annotations

import json

from agentlens.metrics import export_prometheus, get_metrics, reset_metrics  # pyright: ignore[reportImplicitRelativeImport]
from agentlens.observability import (  # pyright: ignore[reportImplicitRelativeImport]
    AgentLensLogger,
    MetricsCollector,
    OTelSpanContext,
    ObservabilityConfig,
)
from agentlens.profiler import Profiler  # pyright: ignore[reportImplicitRelativeImport]


def test_metrics_collector_snapshot_and_export() -> None:
    metrics = MetricsCollector()
    metrics.record(
        success=True,
        latency_ms=12.5,
        token_usage={"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
    )
    metrics.record(success=False, latency_ms=4.0, token_usage={"total_tokens": 0})

    snapshot = metrics.snapshot()
    assert snapshot["call_count"] == 2
    assert snapshot["error_count"] == 1
    assert snapshot["token_totals"]["total_tokens"] == 10

    prometheus = metrics.export()
    assert "agentlens_call_count_total 2" in prometheus
    assert "agentlens_error_count_total 1" in prometheus
    assert "agentlens_latency_ms_bucket" in prometheus


def test_metrics_module_helpers() -> None:
    reset_metrics()
    current = get_metrics()
    assert current["call_count"] == 0

    output = export_prometheus()
    assert "agentlens_call_count_total" in output


def test_otel_context_is_graceful_without_dependency() -> None:
    ctx = OTelSpanContext(ObservabilityConfig(enable_otel=True))
    with ctx.span("demo-span"):
        value = 123
    assert value == 123


def test_profiler_emits_structured_events_and_debug_trace(capsys) -> None:
    profiler = Profiler(
        "obs",
        observability=ObservabilityConfig(log_level="DEBUG", debug_mode=True),
    )

    @profiler.llm(model="gpt-4o", name="test_call")
    def call() -> object:
        class Usage:
            prompt_tokens = 1
            completion_tokens = 2
            total_tokens = 3

        class Response:
            usage = Usage()
            model = "gpt-4o"

        return Response()

    call()
    captured = capsys.readouterr().err.splitlines()
    payloads = [json.loads(line) for line in captured if line.startswith("{")]

    assert any(p.get("event") == "call_started" for p in payloads)
    assert any(p.get("event") == "call_completed" for p in payloads)
    assert any(p.get("event") == "debug_trace" for p in payloads)


def test_logger_writes_json(capsys) -> None:
    logger = AgentLensLogger(ObservabilityConfig(log_level="INFO"), logger_name="agentlens.test")
    logger.call_started(name="x", call_id="1")
    payload = json.loads(capsys.readouterr().err.strip())
    assert payload["event"] == "call_started"
    assert payload["name"] == "x"

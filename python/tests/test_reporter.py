from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast

from agentlens.profiler import Profiler, TokenUsage  # pyright: ignore[reportImplicitRelativeImport]
from agentlens.reporter import Reporter, _Colour, _supports_color  # pyright: ignore[reportImplicitRelativeImport]


def _build_profiled_data() -> Profiler:
    profiler = Profiler("report")
    ok = profiler.start_call("llm-step", call_type="llm", model="gpt-4o")
    profiler.end_call(ok, success=True, token_usage=TokenUsage(prompt_tokens=3, completion_tokens=2, total_tokens=5))

    bad = profiler.start_call("tool-step", call_type="tool")
    profiler.end_call(bad, success=False, error=RuntimeError("fail"))
    return profiler


def test_print_summary_table_timeline_outputs_text() -> None:
    profiler = _build_profiled_data()
    reporter = Reporter(profiler, color=False)

    summary_out = io.StringIO()
    table_out = io.StringIO()
    timeline_out = io.StringIO()

    reporter.print_summary(file=summary_out)
    reporter.print_table(file=table_out)
    reporter.print_timeline(file=timeline_out)

    summary = summary_out.getvalue()
    table = table_out.getvalue()
    timeline = timeline_out.getvalue()

    assert "AgentLens" in summary
    assert "Total calls" in summary
    assert "Call Trace" in table
    assert "tool-step" in table
    assert "Timeline" in timeline
    assert "llm-step" in timeline


def test_export_json_and_to_dict(tmp_path, capsys) -> None:
    profiler = _build_profiled_data()
    reporter = Reporter(profiler, color=False)

    output_file = tmp_path / "trace.json"
    reporter.export_json(str(output_file))

    printed = capsys.readouterr().out
    assert "Exported 2 call(s)" in printed

    data = json.loads(output_file.read_text(encoding="utf-8"))
    assert data["profiler"] == "report"
    assert data["summary"]["total_calls"] == 2
    assert len(data["calls"]) == 2

    as_dict = reporter.to_dict()
    assert as_dict["profiler"] == "report"
    assert as_dict["summary"]["failed_calls"] == 1


def test_print_table_can_hide_errors() -> None:
    profiler = _build_profiled_data()
    reporter = Reporter(profiler, color=False)

    table_out = io.StringIO()
    reporter.print_table(show_errors=False, file=table_out)
    text = table_out.getvalue()

    assert "tool-step" not in text
    assert "1 call(s) recorded" in text


def test_colour_support_and_wrapping_behaviour() -> None:
    assert _supports_color(cast(Any, SimpleNamespace(isatty=lambda: True))) is True
    assert _supports_color(cast(Any, SimpleNamespace())) is False

    enabled = _Colour(enabled=True)
    disabled = _Colour(enabled=False)
    assert "\033[32m" in enabled.green("ok")
    assert disabled.green("ok") == "ok"


def test_table_truncation_and_timeline_edge_cases() -> None:
    profiler = Profiler("edges")
    reporter = Reporter(profiler, color=False)

    empty_timeline = io.StringIO()
    reporter.print_timeline(file=empty_timeline)
    assert "No calls recorded" in empty_timeline.getvalue()

    unfinished = profiler.start_call("x" * 80, call_type="tool")
    profiler.end_call(unfinished, success=True)

    table_out = io.StringIO()
    reporter.print_table(file=table_out)
    assert "…" in table_out.getvalue()

    no_start = SimpleNamespace(
        started_at=None,
        ended_at=datetime.now(timezone.utc),
        latency_ms=1.0,
        success=True,
        call_type=SimpleNamespace(value="tool"),
        name="nostart",
        token_usage=TokenUsage(),
        error_type=None,
        model=None,
    )
    timeline_no_start = io.StringIO()
    reporter.profiler = cast(
        Profiler,
        cast(object, SimpleNamespace(name="mock", calls=[no_start], summary=lambda: {}, get_calls=lambda call_type=None: [])),
    )
    reporter.print_timeline(file=timeline_no_start)
    assert timeline_no_start.getvalue() == ""

    missing_end = SimpleNamespace(
        started_at=unfinished.started_at,
        ended_at=None,
        latency_ms=None,
        success=True,
        call_type=SimpleNamespace(value="tool"),
        name="missing-end",
        token_usage=TokenUsage(),
        error_type=None,
        model=None,
    )
    timeline_missing_end = io.StringIO()
    reporter.profiler = cast(
        Profiler,
        cast(object, SimpleNamespace(name="mock2", calls=[missing_end], summary=lambda: {}, get_calls=lambda call_type=None: [])),
    )
    reporter.print_timeline(file=timeline_missing_end)
    assert "Timeline" in timeline_missing_end.getvalue()

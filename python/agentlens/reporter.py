"""
Reporter: generates human-readable CLI tables and JSON exports from a Profiler.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import IO, List, Optional, TextIO

from .profiler import CallType, ProfiledCall, Profiler


# ANSI colour helpers (auto-disable when not a TTY)
def _supports_color(stream: IO) -> bool:
    return hasattr(stream, "isatty") and stream.isatty()


class _Colour:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, t: str) -> str: return self._wrap("1", t)
    def green(self, t: str) -> str: return self._wrap("32", t)
    def red(self, t: str) -> str: return self._wrap("31", t)
    def yellow(self, t: str) -> str: return self._wrap("33", t)
    def cyan(self, t: str) -> str: return self._wrap("36", t)
    def dim(self, t: str) -> str: return self._wrap("2", t)


class Reporter:
    """
    Reads calls from a :class:`Profiler` and renders reports.

    Usage::

        reporter = Reporter(profiler)
        reporter.print_table()
        reporter.print_summary()
        reporter.export_json("trace.json")
    """

    def __init__(self, profiler: Profiler, color: Optional[bool] = None):
        self.profiler = profiler
        use_color = color if color is not None else _supports_color(sys.stdout)
        self._c = _Colour(enabled=use_color)

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #

    def print_summary(self, file: TextIO = sys.stdout) -> None:
        s = self.profiler.summary()
        c = self._c

        print(c.bold(f"\n  AgentLens — Profiler: {s.get('profiler', 'default')}"), file=file)
        print(c.dim("  " + "─" * 46), file=file)

        def row(label: str, value: str, color_fn=None) -> None:
            val = color_fn(value) if color_fn else value
            print(f"  {c.dim(label + ':'): <30} {val}", file=file)

        row("Total calls", str(s["total_calls"]))
        row("  LLM calls", str(s["llm_calls"]), c.cyan)
        row("  Tool calls", str(s["tool_calls"]))
        row("  Failed calls", str(s["failed_calls"]),
            c.red if s["failed_calls"] > 0 else None)
        row("Success rate", f"{s['success_rate']}%",
            c.green if s["success_rate"] == 100.0 else c.yellow)
        row("Total latency", f"{s['total_latency_ms']} ms")
        row("Avg latency", f"{s['avg_latency_ms']} ms")
        row("Min / Max latency",
            f"{s['min_latency_ms']} ms / {s['max_latency_ms']} ms")

        tok = s.get("token_usage", {})
        if tok.get("total_tokens", 0) > 0:
            print(c.dim("  " + "─" * 46), file=file)
            row("Prompt tokens", str(tok["prompt_tokens"]), c.dim)
            row("Completion tokens", str(tok["completion_tokens"]), c.dim)
            row("Total tokens", str(tok["total_tokens"]), c.cyan)

        print("", file=file)

    # ------------------------------------------------------------------ #
    # Call table
    # ------------------------------------------------------------------ #

    def print_table(
        self,
        call_type: Optional[CallType] = None,
        show_errors: bool = True,
        file: TextIO = sys.stdout,
    ) -> None:
        calls = self.profiler.get_calls(call_type=call_type)
        if not show_errors:
            calls = [c for c in calls if c.success]

        c = self._c

        headers = ["#", "Name", "Type", "Model", "Latency (ms)", "Tokens", "Status"]
        col_w = [4, 28, 7, 16, 13, 8, 10]

        def fmt(val: str, width: int) -> str:
            val = str(val)
            if len(val) > width:
                val = val[: width - 1] + "…"
            return val.ljust(width)

        sep = c.dim("  " + "┼".join("─" * w for w in col_w))
        header_row = "  " + "│".join(
            c.bold(fmt(h, col_w[i])) for i, h in enumerate(headers)
        )

        print(c.bold(f"\n  Call Trace — {self.profiler.name}"), file=file)
        print(c.dim("  " + "┬".join("─" * w for w in col_w)), file=file)
        print(header_row, file=file)
        print(sep, file=file)

        for idx, call in enumerate(calls, 1):
            latency = f"{call.latency_ms:.1f}" if call.latency_ms is not None else "—"
            tokens = str(call.token_usage.total_tokens) if call.token_usage.total_tokens else "—"
            status = c.green("✓ ok") if call.success else c.red(f"✗ {call.error_type or 'err'}")
            model = call.model or "—"
            type_str = call.call_type.value if hasattr(call.call_type, "value") else str(call.call_type)

            row = "  " + "│".join([
                fmt(str(idx), col_w[0]),
                fmt(call.name, col_w[1]),
                c.cyan(fmt(type_str, col_w[2])),
                c.dim(fmt(model, col_w[3])),
                fmt(latency, col_w[4]),
                fmt(tokens, col_w[5]),
                status.ljust(col_w[6]),
            ])
            print(row, file=file)

        print(c.dim("  " + "┴".join("─" * w for w in col_w)), file=file)
        print(f"  {len(calls)} call(s) recorded\n", file=file)

    # ------------------------------------------------------------------ #
    # Flame-like timeline (ASCII)
    # ------------------------------------------------------------------ #

    def print_timeline(self, file: TextIO = sys.stdout) -> None:
        calls = self.profiler.calls
        if not calls:
            print("  No calls recorded.", file=file)
            return

        c = self._c
        start_times = [ca.started_at for ca in calls if ca.started_at]
        if not start_times:
            return

        t_min = min(start_times)
        t_max_latency = max(
            (ca.ended_at for ca in calls if ca.ended_at), default=t_min
        )
        total_span = (t_max_latency - t_min).total_seconds() * 1000 or 1
        bar_width = 40

        print(c.bold(f"\n  Timeline — {self.profiler.name}"), file=file)
        print(c.dim(f"  {'Name':<28} {'Bar':<42} {'ms':>7}"), file=file)
        print(c.dim("  " + "─" * 80), file=file)

        for call in calls:
            if call.started_at is None or call.ended_at is None:
                continue
            offset = (call.started_at - t_min).total_seconds() * 1000
            width = max(1, int((call.latency_ms or 0) / total_span * bar_width))
            pad = int(offset / total_span * bar_width)

            bar_char = "█" if call.success else "░"
            bar = " " * pad + bar_char * width
            latency_str = f"{call.latency_ms:.1f}" if call.latency_ms else "—"
            name = call.name[:26]
            colour_fn = c.cyan if call.call_type == CallType.LLM else c.green
            print(
                f"  {name:<28} {colour_fn(bar):<42} {c.dim(latency_str):>7}",
                file=file,
            )

        print("", file=file)

    # ------------------------------------------------------------------ #
    # JSON export
    # ------------------------------------------------------------------ #

    def export_json(self, path: str) -> None:
        """Export all call data and summary to a JSON file."""
        data = {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "profiler": self.profiler.name,
            "summary": self.profiler.summary(),
            "calls": [c.to_dict() for c in self.profiler.calls],
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)
        print(f"  Exported {len(data['calls'])} call(s) to {path}")

    def to_dict(self) -> dict:
        return {
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "profiler": self.profiler.name,
            "summary": self.profiler.summary(),
            "calls": [c.to_dict() for c in self.profiler.calls],
        }

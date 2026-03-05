"""
CLI entry point: `python -m agentlens` or `agentlens` (if installed).
Reads a JSON trace file and pretty-prints the report.
"""

from __future__ import annotations

import argparse
import json
import sys

from .profiler import Profiler, ProfiledCall, CallType, TokenUsage
from .reporter import Reporter


def _load_trace(path: str) -> Profiler:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    profiler_name = data.get("profiler", "imported")
    profiler = Profiler(name=profiler_name)

    for raw in data.get("calls", []):
        call = ProfiledCall(
            id=raw.get("id", ""),
            name=raw.get("name", ""),
            call_type=CallType(raw.get("call_type", "tool")),
            model=raw.get("model"),
            success=raw.get("success", True),
            error=raw.get("error"),
            error_type=raw.get("error_type"),
            metadata=raw.get("metadata", {}),
            parent_id=raw.get("parent_id"),
            tags=raw.get("tags", []),
        )
        # Reconstruct token usage
        tu = raw.get("token_usage", {})
        call.token_usage = TokenUsage(
            prompt_tokens=tu.get("prompt_tokens", 0),
            completion_tokens=tu.get("completion_tokens", 0),
            total_tokens=tu.get("total_tokens", 0),
        )
        # Reconstruct latency
        call.latency_ms = raw.get("latency_ms")
        profiler._calls.append(call)

    return profiler


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agentlens",
        description="AgentLens — view AI agent pipeline traces",
    )
    sub = parser.add_subparsers(dest="command")

    view = sub.add_parser("view", help="View a JSON trace file")
    view.add_argument("file", help="Path to the JSON trace file")
    view.add_argument("--no-table", action="store_true", help="Skip call table")
    view.add_argument("--no-summary", action="store_true", help="Skip summary")
    view.add_argument("--timeline", action="store_true", help="Show ASCII timeline")

    args = parser.parse_args()

    if args.command == "view":
        try:
            profiler = _load_trace(args.file)
        except FileNotFoundError:
            print(f"Error: file not found: {args.file}", file=sys.stderr)
            sys.exit(1)

        reporter = Reporter(profiler)
        if not args.no_table:
            reporter.print_table()
        if not args.no_summary:
            reporter.print_summary()
        if args.timeline:
            reporter.print_timeline()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

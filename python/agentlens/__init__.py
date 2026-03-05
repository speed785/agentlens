"""
AgentLens - Lightweight observability for AI agent pipelines.
DevTools for agents: measure latency, token usage, and tool call health.
"""

from .profiler import Profiler, ProfiledCall, CallType, profile_tool, profile_llm
from .reporter import Reporter
from .metrics import get_metrics, reset_metrics, export_prometheus
from .observability import ObservabilityConfig, AgentLensLogger, MetricsCollector, OTelSpanContext

__version__ = "0.1.0"
__author__ = "AgentLens Contributors"
__license__ = "MIT"

__all__ = [
    "Profiler",
    "ProfiledCall",
    "CallType",
    "profile_tool",
    "profile_llm",
    "Reporter",
    "ObservabilityConfig",
    "AgentLensLogger",
    "MetricsCollector",
    "OTelSpanContext",
    "get_metrics",
    "reset_metrics",
    "export_prometheus",
]

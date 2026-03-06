"""
Core profiler: decorators and wrappers for instrumenting LLM calls and tool calls.
"""

from __future__ import annotations

import functools
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, cast

from .observability import (
    AgentLensLogger,
    ObservabilityConfig,
    OTelSpanContext,
    get_default_observability,
    get_metrics_collector,
)

F = TypeVar("F", bound=Callable[..., Any])


class CallType(str, Enum):
    LLM = "llm"
    TOOL = "tool"
    CHAIN = "chain"


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    @classmethod
    def from_openai_usage(cls, usage: Any) -> "TokenUsage":
        if usage is None:
            return cls()
        return cls(
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )

    @classmethod
    def from_anthropic_usage(cls, usage: Any) -> "TokenUsage":
        if usage is None:
            return cls()
        return cls(
            prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            total_tokens=(getattr(usage, "input_tokens", 0) or 0)
            + (getattr(usage, "output_tokens", 0) or 0),
        )

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class ProfiledCall:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    call_type: CallType = CallType.TOOL
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    latency_ms: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    error_type: Optional[str] = None
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    model: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    def finish(
        self,
        success: bool = True,
        error: Optional[Exception] = None,
        token_usage: Optional[TokenUsage] = None,
        model: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.ended_at = datetime.now(timezone.utc)
        self.latency_ms = (
            (self.ended_at - self.started_at).total_seconds() * 1000
        )
        self.success = success
        if error is not None:
            self.error = str(error)
            self.error_type = type(error).__name__
        if token_usage is not None:
            self.token_usage = token_usage
        if model is not None:
            self.model = model
        if metadata:
            self.metadata.update(metadata)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "call_type": self.call_type.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "latency_ms": round(self.latency_ms, 3) if self.latency_ms is not None else None,
            "success": self.success,
            "error": self.error,
            "error_type": self.error_type,
            "token_usage": self.token_usage.to_dict(),
            "model": self.model,
            "metadata": self.metadata,
            "parent_id": self.parent_id,
            "tags": self.tags,
        }


class Profiler:
    """
    Central profiler that collects and stores all instrumented calls.

    Usage::

        profiler = Profiler(name="my-agent")

        @profiler.tool("search_web")
        def search_web(query: str) -> str:
            ...

        @profiler.llm("gpt-4o")
        def call_llm(messages):
            ...
    """

    _local = threading.local()

    def __init__(
        self,
        name: str = "default",
        tags: Optional[List[str]] = None,
        observability: Optional[ObservabilityConfig] = None,
    ):
        self.name = name
        self.tags = tags or []
        self._calls: List[ProfiledCall] = []
        self._lock = threading.Lock()
        self._active_chain: Optional[str] = None
        self._observability = observability or get_default_observability()
        self._logger = AgentLensLogger(self._observability, logger_name=f"agentlens.{self.name}")
        self._otel = OTelSpanContext(self._observability)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _record(self, call: ProfiledCall) -> None:
        with self._lock:
            self._calls.append(call)

        if self._observability.enable_metrics and call.latency_ms is not None:
            get_metrics_collector().record(
                success=call.success,
                latency_ms=call.latency_ms,
                token_usage=call.token_usage.to_dict(),
            )

        payload: Dict[str, Any] = {
            "call_id": call.id,
            "name": call.name,
            "call_type": call.call_type.value,
            "model": call.model,
            "parent_id": call.parent_id,
            "success": call.success,
            "latency_ms": call.latency_ms,
            "error_type": call.error_type,
        }

        if call.call_type == CallType.CHAIN:
            self._logger.chain_completed(**payload)
        elif call.success:
            self._logger.call_completed(**payload)
        else:
            self._logger.call_failed(**payload)

        if self._observability.debug_mode:
            self._logger.debug_trace(
                event_scope="record",
                profiler=self.name,
                call=call.to_dict(),
                token_breakdown=call.token_usage.to_dict(),
            )

    def _start_call(
        self,
        name: str,
        call_type: CallType,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_id: Optional[str] = None,
    ) -> ProfiledCall:
        call = ProfiledCall(
            name=name,
            call_type=call_type,
            model=model,
            tags=(self.tags + (tags or [])),
            parent_id=parent_id or self._active_chain,
        )

        payload: Dict[str, Any] = {
            "call_id": call.id,
            "name": call.name,
            "call_type": call.call_type.value,
            "model": call.model,
            "parent_id": call.parent_id,
        }

        if call_type == CallType.CHAIN:
            self._logger.chain_started(**payload)
        else:
            self._logger.call_started(**payload)

        return call

    # ------------------------------------------------------------------ #
    # Public API — decorators
    # ------------------------------------------------------------------ #

    def tool(
        self,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Callable[[F], F]:
        """Decorator that profiles a tool/function call."""

        def decorator(fn: F) -> F:
            tool_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                call = self._start_call(tool_name, CallType.TOOL, tags=tags)
                try:
                    result = fn(*args, **kwargs)
                    call.finish(success=True)
                    return result
                except Exception as exc:
                    call.finish(success=False, error=exc)
                    raise
                finally:
                    self._record(call)

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                call = self._start_call(tool_name, CallType.TOOL, tags=tags)
                try:
                    result = await fn(*args, **kwargs)
                    call.finish(success=True)
                    return result
                except Exception as exc:
                    call.finish(success=False, error=exc)
                    raise
                finally:
                    self._record(call)

            import asyncio

            if asyncio.iscoroutinefunction(fn):
                return cast(F, async_wrapper)  # pyright: ignore[reportReturnType]
            return cast(F, wrapper)  # pyright: ignore[reportReturnType]

        return decorator

    def llm(
        self,
        model: Optional[str] = None,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
        token_extractor: Optional[Callable[[Any], TokenUsage]] = None,
    ) -> Callable[[F], F]:
        """Decorator that profiles an LLM call and extracts token usage."""

        def decorator(fn: F) -> F:
            call_name = name or fn.__name__

            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                call = self._start_call(call_name, CallType.LLM, model=model, tags=tags)
                try:
                    result = fn(*args, **kwargs)
                    usage = None
                    if token_extractor:
                        usage = token_extractor(result)
                    elif hasattr(result, "usage"):
                        # Auto-detect OpenAI or Anthropic usage shapes
                        raw = result.usage
                        if hasattr(raw, "prompt_tokens"):
                            usage = TokenUsage.from_openai_usage(raw)
                        elif hasattr(raw, "input_tokens"):
                            usage = TokenUsage.from_anthropic_usage(raw)
                    inferred_model = model or getattr(result, "model", None)
                    call.finish(success=True, token_usage=usage, model=inferred_model)
                    return result
                except Exception as exc:
                    call.finish(success=False, error=exc)
                    raise
                finally:
                    self._record(call)

            @functools.wraps(fn)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                call = self._start_call(call_name, CallType.LLM, model=model, tags=tags)
                try:
                    result = await fn(*args, **kwargs)
                    usage = None
                    if token_extractor:
                        usage = token_extractor(result)
                    elif hasattr(result, "usage"):
                        raw = result.usage
                        if hasattr(raw, "prompt_tokens"):
                            usage = TokenUsage.from_openai_usage(raw)
                        elif hasattr(raw, "input_tokens"):
                            usage = TokenUsage.from_anthropic_usage(raw)
                    inferred_model = model or getattr(result, "model", None)
                    call.finish(success=True, token_usage=usage, model=inferred_model)
                    return result
                except Exception as exc:
                    call.finish(success=False, error=exc)
                    raise
                finally:
                    self._record(call)

            import asyncio

            if asyncio.iscoroutinefunction(fn):
                return cast(F, async_wrapper)  # pyright: ignore[reportReturnType]
            return cast(F, wrapper)  # pyright: ignore[reportReturnType]

        return decorator

    def chain(self, name: str, tags: Optional[List[str]] = None) -> "ChainContext":
        """Context manager that groups calls under a named chain."""
        return ChainContext(self, name, tags=tags)

    # ------------------------------------------------------------------ #
    # Manual instrumentation
    # ------------------------------------------------------------------ #

    def start_call(
        self,
        name: str,
        call_type: Union[CallType, str] = CallType.TOOL,
        model: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> ProfiledCall:
        """Start a call manually and return the ProfiledCall handle."""
        # Accept both CallType enum values and plain strings like "llm", "tool"
        if isinstance(call_type, str):
            call_type = CallType(call_type)
        call = self._start_call(name, call_type, model=model, tags=tags)
        return call

    def end_call(
        self,
        call: ProfiledCall,
        success: bool = True,
        error: Optional[Exception] = None,
        token_usage: Optional[TokenUsage] = None,
        model: Optional[str] = None,
    ) -> None:
        """Finish a manually-started call and record it."""
        call.finish(success=success, error=error, token_usage=token_usage, model=model)
        self._record(call)

    # ------------------------------------------------------------------ #
    # Data access
    # ------------------------------------------------------------------ #

    @property
    def calls(self) -> List[ProfiledCall]:
        with self._lock:
            return list(self._calls)

    def clear(self) -> None:
        with self._lock:
            self._calls.clear()

    def get_calls(
        self,
        call_type: Optional[CallType] = None,
        success_only: bool = False,
        failed_only: bool = False,
    ) -> List[ProfiledCall]:
        results = self.calls
        if call_type:
            results = [c for c in results if c.call_type == call_type]
        if success_only:
            results = [c for c in results if c.success]
        if failed_only:
            results = [c for c in results if not c.success]
        return results

    def summary(self) -> Dict[str, Any]:
        """Return a compact summary dict of all recorded calls."""
        calls = self.calls
        if not calls:
            return {"total_calls": 0}

        total_latency = sum(c.latency_ms or 0 for c in calls)
        llm_calls = [c for c in calls if c.call_type == CallType.LLM]
        tool_calls = [c for c in calls if c.call_type == CallType.TOOL]
        failed = [c for c in calls if not c.success]

        total_tokens = sum(c.token_usage.total_tokens for c in llm_calls)
        prompt_tokens = sum(c.token_usage.prompt_tokens for c in llm_calls)
        completion_tokens = sum(c.token_usage.completion_tokens for c in llm_calls)

        latencies = [c.latency_ms for c in calls if c.latency_ms is not None]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0
        min_latency = min(latencies) if latencies else 0

        return {
            "profiler": self.name,
            "total_calls": len(calls),
            "llm_calls": len(llm_calls),
            "tool_calls": len(tool_calls),
            "failed_calls": len(failed),
            "success_rate": round((1 - len(failed) / len(calls)) * 100, 1) if calls else 100.0,
            "total_latency_ms": round(total_latency, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "min_latency_ms": round(min_latency, 2),
            "max_latency_ms": round(max_latency, 2),
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }


class ChainContext:
    """Context manager for grouping calls under a named chain."""

    def __init__(self, profiler: Profiler, name: str, tags: Optional[List[str]] = None):
        self._profiler = profiler
        self._name = name
        self._tags = tags
        self._call: Optional[ProfiledCall] = None
        self._previous_chain: Optional[str] = None

    def __enter__(self) -> "ChainContext":
        self._call = self._profiler._start_call(self._name, CallType.CHAIN, tags=self._tags)
        self._previous_chain = self._profiler._active_chain
        self._profiler._active_chain = self._call.id
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self._profiler._active_chain = self._previous_chain
        if self._call:
            success = exc_type is None
            error = exc_val if exc_val else None
            self._call.finish(success=success, error=error)
            self._profiler._record(self._call)

    async def __aenter__(self) -> "ChainContext":
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.__exit__(exc_type, exc_val, exc_tb)


# ------------------------------------------------------------------ #
# Standalone decorators backed by a module-level default profiler
# ------------------------------------------------------------------ #

_default_profiler = Profiler(name="global")


def profile_tool(
    name: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Callable[[F], F]:
    """Module-level @profile_tool decorator using the global profiler."""
    return _default_profiler.tool(name=name, tags=tags)


def profile_llm(
    model: Optional[str] = None,
    name: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> Callable[[F], F]:
    """Module-level @profile_llm decorator using the global profiler."""
    return _default_profiler.llm(model=model, name=name, tags=tags)


def get_default_profiler() -> Profiler:
    return _default_profiler

"""
Drop-in wrapper for the Anthropic Python client.

Usage::

    import anthropic
    from agentlens import Profiler
    from agentlens.integrations.anthropic import ProfiledAnthropic

    profiler = Profiler("my-agent")
    client = ProfiledAnthropic(anthropic.Anthropic(api_key="..."), profiler=profiler)

    # Use exactly like the standard anthropic client
    message = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": "Hello!"}],
    )
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from ..profiler import CallType, ProfiledCall, Profiler, TokenUsage


class _ProfiledMessages:
    def __init__(self, inner: Any, profiler: Profiler) -> None:
        self._inner = inner
        self._profiler = profiler

    def create(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        stream = kwargs.get("stream", False)
        name = f"anthropic.messages/{model}"

        if stream:
            return self._create_stream(name, *args, **kwargs)

        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            response = self._inner.create(*args, **kwargs)
            usage = TokenUsage.from_anthropic_usage(getattr(response, "usage", None))
            inferred_model = getattr(response, "model", model)
            call.finish(success=True, token_usage=usage, model=inferred_model)
            return response
        except Exception as exc:
            call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(call)

    def _create_stream(self, name: str, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            stream = self._inner.create(*args, **kwargs)
        except Exception as exc:
            call.finish(success=False, error=exc)
            self._profiler._record(call)
            raise
        return _AnthropicStreamWrapper(stream, call, self._profiler)

    async def acreate(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        name = f"anthropic.messages/{model}"
        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            response = await self._inner.acreate(*args, **kwargs)
            usage = TokenUsage.from_anthropic_usage(getattr(response, "usage", None))
            call.finish(success=True, token_usage=usage, model=getattr(response, "model", model))
            return response
        except Exception as exc:
            call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(call)

    def stream(self, *args: Any, **kwargs: Any) -> Any:
        """Support the `with client.messages.stream(...)` context manager pattern."""
        model = kwargs.get("model", "unknown")
        name = f"anthropic.messages.stream/{model}"
        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            ctx = self._inner.stream(*args, **kwargs)
        except Exception as exc:
            call.finish(success=False, error=exc)
            self._profiler._record(call)
            raise
        return _AnthropicStreamContext(ctx, call, self._profiler)


class _AnthropicStreamWrapper:
    def __init__(self, stream: Any, call: ProfiledCall, profiler: Profiler) -> None:
        self._stream = stream
        self._call = call
        self._profiler = profiler

    def __iter__(self) -> Iterator[Any]:
        try:
            for event in self._stream:
                yield event
            self._call.finish(success=True)
        except Exception as exc:
            self._call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(self._call)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._stream, item)


class _AnthropicStreamContext:
    """Wraps the context manager returned by `client.messages.stream(...)`."""

    def __init__(self, ctx: Any, call: ProfiledCall, profiler: Profiler) -> None:
        self._ctx = ctx
        self._call = call
        self._profiler = profiler

    def __enter__(self) -> Any:
        inner = self._ctx.__enter__()
        return _AnthropicStreamWrapper(inner, self._call, self._profiler)

    def __exit__(self, *args: Any) -> Any:
        return self._ctx.__exit__(*args)

    async def __aenter__(self) -> Any:
        inner = await self._ctx.__aenter__()
        return _AnthropicStreamWrapper(inner, self._call, self._profiler)

    async def __aexit__(self, *args: Any) -> Any:
        return await self._ctx.__aexit__(*args)


class ProfiledAnthropic:
    """
    Wraps an ``anthropic.Anthropic`` instance and automatically profiles
    every API call.

    All non-wrapped attributes are forwarded transparently to the underlying
    client so existing code requires no other changes.
    """

    def __init__(self, client: Any, profiler: Optional[Profiler] = None) -> None:
        self._client = client
        self._profiler = profiler or Profiler("anthropic")
        self.messages = _ProfiledMessages(client.messages, self._profiler)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._client, item)

    @property
    def profiler(self) -> Profiler:
        return self._profiler

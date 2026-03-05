"""
Drop-in wrapper for the OpenAI Python client.

Usage::

    import openai
    from agentlens import Profiler
    from agentlens.integrations.openai import ProfiledOpenAI

    profiler = Profiler("my-agent")
    client = ProfiledOpenAI(openai.OpenAI(api_key="..."), profiler=profiler)

    # Use exactly like the standard openai client
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Hello!"}],
    )
"""

from __future__ import annotations

from typing import Any, Iterator, Optional

from ..profiler import CallType, ProfiledCall, Profiler, TokenUsage


class _ProfiledChatCompletions:
    def __init__(self, inner: Any, profiler: Profiler) -> None:
        self._inner = inner
        self._profiler = profiler

    def create(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        stream = kwargs.get("stream", False)
        name = f"openai.chat/{model}"

        if stream:
            return self._create_stream(name, *args, **kwargs)

        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            response = self._inner.create(*args, **kwargs)
            usage = TokenUsage.from_openai_usage(getattr(response, "usage", None))
            inferred_model = getattr(response, "model", model)
            call.finish(success=True, token_usage=usage, model=inferred_model)
            return response
        except Exception as exc:
            call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(call)

    def _create_stream(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Wrap a streaming response — records the call after the stream is consumed."""
        model = kwargs.get("model", "unknown")
        call = self._profiler._start_call(name, CallType.LLM, model=model)

        try:
            stream = self._inner.create(*args, **kwargs)
        except Exception as exc:
            call.finish(success=False, error=exc)
            self._profiler._record(call)
            raise

        return _StreamWrapper(stream, call, self._profiler)

    async def acreate(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        name = f"openai.chat/{model}"
        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            response = await self._inner.acreate(*args, **kwargs)
            usage = TokenUsage.from_openai_usage(getattr(response, "usage", None))
            call.finish(success=True, token_usage=usage, model=getattr(response, "model", model))
            return response
        except Exception as exc:
            call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(call)


class _StreamWrapper:
    """Thin iterator wrapper that closes the profiled call when the stream ends."""

    def __init__(self, stream: Any, call: ProfiledCall, profiler: Profiler) -> None:
        self._stream = stream
        self._call = call
        self._profiler = profiler

    def __iter__(self) -> Iterator[Any]:
        try:
            for chunk in self._stream:
                yield chunk
            self._call.finish(success=True)
        except Exception as exc:
            self._call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(self._call)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._stream, item)


class _ProfiledCompletions:
    """Wraps legacy openai.completions (text completion endpoint)."""

    def __init__(self, inner: Any, profiler: Profiler) -> None:
        self._inner = inner
        self._profiler = profiler

    def create(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "unknown")
        name = f"openai.completion/{model}"
        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            response = self._inner.create(*args, **kwargs)
            usage = TokenUsage.from_openai_usage(getattr(response, "usage", None))
            call.finish(success=True, token_usage=usage)
            return response
        except Exception as exc:
            call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(call)


class _ProfiledEmbeddings:
    def __init__(self, inner: Any, profiler: Profiler) -> None:
        self._inner = inner
        self._profiler = profiler

    def create(self, *args: Any, **kwargs: Any) -> Any:
        model = kwargs.get("model", "text-embedding-3-small")
        name = f"openai.embeddings/{model}"
        call = self._profiler._start_call(name, CallType.LLM, model=model)
        try:
            response = self._inner.create(*args, **kwargs)
            usage = TokenUsage.from_openai_usage(getattr(response, "usage", None))
            call.finish(success=True, token_usage=usage)
            return response
        except Exception as exc:
            call.finish(success=False, error=exc)
            raise
        finally:
            self._profiler._record(call)


class ProfiledOpenAI:
    """
    Wraps an ``openai.OpenAI`` (or ``openai.AzureOpenAI``) instance and
    automatically profiles every API call.

    All attributes not explicitly wrapped are forwarded transparently to the
    underlying client, so you can drop this in without any other code changes.
    """

    def __init__(self, client: Any, profiler: Optional[Profiler] = None) -> None:
        self._client = client
        self._profiler = profiler or Profiler("openai")
        self.chat = _ProfiledChat(client.chat, self._profiler)
        self.completions = _ProfiledCompletions(client.completions, self._profiler)  # type: ignore[attr-defined]
        self.embeddings = _ProfiledEmbeddings(client.embeddings, self._profiler)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._client, item)

    @property
    def profiler(self) -> Profiler:
        return self._profiler


class _ProfiledChat:
    def __init__(self, inner: Any, profiler: Profiler) -> None:
        self._inner = inner
        self.completions = _ProfiledChatCompletions(inner.completions, profiler)

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

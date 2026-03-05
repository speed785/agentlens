from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest  # pyright: ignore[reportMissingImports]

from agentlens import Profiler  # pyright: ignore[reportImplicitRelativeImport]
from agentlens.integrations import (  # pyright: ignore[reportImplicitRelativeImport]
    ProfiledAnthropic,
    ProfiledOpenAI,
)


def test_integrations_exports() -> None:
    assert ProfiledOpenAI is not None
    assert ProfiledAnthropic is not None


def test_profiled_openai_records_chat_and_embeddings_calls() -> None:
    profiler = Profiler("openai")

    chat_create = Mock(
        return_value=SimpleNamespace(
            model="gpt-4o-mini",
            usage=SimpleNamespace(prompt_tokens=4, completion_tokens=6, total_tokens=10),
        )
    )
    embed_create = Mock(return_value=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=2, completion_tokens=0, total_tokens=2)))
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=chat_create), sentinel="ok"),
        completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace(usage=None))),
        embeddings=SimpleNamespace(create=embed_create),
        ping="pong",
    )

    wrapped = ProfiledOpenAI(client, profiler=profiler)
    wrapped.chat.completions.create(model="gpt-4o", messages=[])
    wrapped.embeddings.create(model="text-embedding-3-small", input="x")

    assert wrapped.chat.sentinel == "ok"
    assert wrapped.ping == "pong"

    calls = profiler.calls
    assert len(calls) == 2
    assert calls[0].name == "openai.chat/gpt-4o"
    assert calls[0].token_usage.total_tokens == 10
    assert calls[0].model == "gpt-4o-mini"
    assert calls[1].name == "openai.embeddings/text-embedding-3-small"


def test_profiled_openai_stream_records_after_iteration() -> None:
    profiler = Profiler("openai-stream")

    class Stream:
        def __iter__(self):
            yield {"delta": "a"}
            yield {"delta": "b"}

    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(return_value=Stream()))),
        completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace(usage=None))),
        embeddings=SimpleNamespace(create=Mock(return_value=SimpleNamespace(usage=None))),
    )
    wrapped = ProfiledOpenAI(client, profiler=profiler)

    stream = wrapped.chat.completions.create(model="gpt-4o", stream=True, messages=[])
    assert list(stream) == [{"delta": "a"}, {"delta": "b"}]

    assert len(profiler.calls) == 1
    assert profiler.calls[0].success is True


def test_profiled_anthropic_records_calls_and_stream_context() -> None:
    profiler = Profiler("anthropic")

    message_create = Mock(
        return_value=SimpleNamespace(
            model="claude-3-5-sonnet",
            usage=SimpleNamespace(input_tokens=8, output_tokens=4),
        )
    )

    class DummyCtx:
        def __enter__(self):
            return iter([{"event": 1}])

        def __exit__(self, *_args):
            return False

    messages = SimpleNamespace(create=message_create, stream=Mock(return_value=DummyCtx()))
    client = SimpleNamespace(messages=messages, ping="pong")

    wrapped = ProfiledAnthropic(client, profiler=profiler)
    wrapped.messages.create(model="claude-3-5-sonnet", max_tokens=10, messages=[])

    with wrapped.messages.stream(model="claude-3-5-sonnet", max_tokens=10, messages=[]) as stream:
        assert list(stream) == [{"event": 1}]

    assert wrapped.ping == "pong"
    assert len(profiler.calls) == 2
    assert profiler.calls[0].token_usage.total_tokens == 12
    assert profiler.calls[1].name.startswith("anthropic.messages.stream/")


@pytest.mark.asyncio
async def test_async_create_methods_are_profiled() -> None:
    profiler = Profiler("async-integrations")

    openai_chat = SimpleNamespace(
        create=Mock(return_value=SimpleNamespace(usage=None)),
        acreate=AsyncMock(return_value=SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))),
    )
    openai_client = SimpleNamespace(
        chat=SimpleNamespace(completions=openai_chat),
        completions=SimpleNamespace(create=Mock(return_value=SimpleNamespace(usage=None))),
        embeddings=SimpleNamespace(create=Mock(return_value=SimpleNamespace(usage=None))),
    )
    wrapped_openai = ProfiledOpenAI(openai_client, profiler=profiler)
    await wrapped_openai.chat.completions.acreate(model="gpt-4o", messages=[])

    anthropic_messages = SimpleNamespace(
        create=Mock(return_value=SimpleNamespace(usage=None)),
        acreate=AsyncMock(return_value=SimpleNamespace(usage=SimpleNamespace(input_tokens=2, output_tokens=3))),
    )
    wrapped_anthropic = ProfiledAnthropic(SimpleNamespace(messages=anthropic_messages), profiler=profiler)
    await wrapped_anthropic.messages.acreate(model="claude", max_tokens=5, messages=[])

    totals = [c.token_usage.total_tokens for c in profiler.calls]
    assert 2 in totals
    assert 5 in totals

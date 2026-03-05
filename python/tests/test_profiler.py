from __future__ import annotations

from types import SimpleNamespace

import pytest  # pyright: ignore[reportMissingImports]

from agentlens.profiler import (  # pyright: ignore[reportImplicitRelativeImport]
    CallType,
    Profiler,
    TokenUsage,
    get_default_profiler,
    profile_llm,
    profile_tool,
)


def test_tool_decorator_success_and_failure() -> None:
    profiler = Profiler("unit", tags=["suite"])

    @profiler.tool("double", tags=["math"])
    def double(x: int) -> int:
        return x * 2

    @profiler.tool("boom")
    def boom() -> None:
        raise ValueError("bad")

    assert double(21) == 42
    with pytest.raises(ValueError):
        boom()

    calls = profiler.calls
    assert len(calls) == 2
    assert calls[0].name == "double"
    assert calls[0].call_type == CallType.TOOL
    assert calls[0].success is True
    assert "suite" in calls[0].tags
    assert "math" in calls[0].tags
    assert calls[1].success is False
    assert calls[1].error_type == "ValueError"


def test_llm_decorator_token_extraction_openai_and_anthropic() -> None:
    profiler = Profiler("tokens")

    @profiler.llm(model="gpt-4o", name="openai_call")
    def openai_call() -> SimpleNamespace:
        return SimpleNamespace(
            model="gpt-4o-mini",
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )

    @profiler.llm(model="claude", name="anthropic_call")
    def anthropic_call() -> SimpleNamespace:
        return SimpleNamespace(
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
        )

    openai_call()
    anthropic_call()

    first, second = profiler.calls
    assert first.token_usage.total_tokens == 15
    assert first.model == "gpt-4o"
    assert second.token_usage.prompt_tokens == 7
    assert second.token_usage.completion_tokens == 3
    assert second.token_usage.total_tokens == 10


def test_token_usage_none_and_profiled_call_metadata_update() -> None:
    assert TokenUsage.from_openai_usage(None).to_dict() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    assert TokenUsage.from_anthropic_usage(None).to_dict() == {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }

    call = Profiler("meta").start_call("c")
    call.finish(metadata={"a": 1})
    assert call.metadata == {"a": 1}


def test_llm_decorator_custom_token_extractor() -> None:
    profiler = Profiler("custom")

    @profiler.llm(model="custom-model", token_extractor=lambda r: TokenUsage(total_tokens=r["total"]))
    def call() -> dict[str, int]:
        return {"total": 99}

    call()
    assert profiler.calls[0].token_usage.total_tokens == 99


@pytest.mark.asyncio
async def test_async_tool_and_llm_wrappers() -> None:
    profiler = Profiler("async")

    @profiler.tool("atool")
    async def atool(v: int) -> int:
        return v + 1

    @profiler.llm(model="gpt-4o", name="allm")
    async def allm() -> SimpleNamespace:
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3))

    assert await atool(4) == 5
    await allm()

    calls = profiler.calls
    assert [c.name for c in calls] == ["atool", "allm"]
    assert calls[1].token_usage.total_tokens == 3


@pytest.mark.asyncio
async def test_async_wrapper_error_paths_and_token_inference_branches() -> None:
    profiler = Profiler("async-branches")

    @profiler.tool("atool-boom")
    async def atool_boom() -> None:
        raise RuntimeError("tool fail")

    @profiler.llm(name="sync-llm-boom")
    def sync_llm_boom() -> None:
        raise ValueError("sync fail")

    @profiler.llm(name="allm-custom", token_extractor=lambda res: TokenUsage(total_tokens=res["n"]))
    async def allm_custom() -> dict[str, int]:
        return {"n": 7}

    @profiler.llm(name="allm-anthropic")
    async def allm_anthropic() -> SimpleNamespace:
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=4, output_tokens=5))

    @profiler.llm(name="allm-boom")
    async def allm_boom() -> None:
        raise RuntimeError("llm fail")

    with pytest.raises(RuntimeError, match="tool fail"):
        await atool_boom()
    with pytest.raises(ValueError, match="sync fail"):
        sync_llm_boom()

    await allm_custom()
    await allm_anthropic()

    with pytest.raises(RuntimeError, match="llm fail"):
        await allm_boom()

    custom = next(c for c in profiler.calls if c.name == "allm-custom")
    anthropic = next(c for c in profiler.calls if c.name == "allm-anthropic")
    assert custom.token_usage.total_tokens == 7
    assert anthropic.token_usage.total_tokens == 9


def test_summary_empty_profiler() -> None:
    assert Profiler("empty").summary() == {"total_calls": 0}


def test_manual_instrumentation_and_filters() -> None:
    profiler = Profiler("manual")
    call = profiler.start_call("manual-llm", call_type="llm", model="m")
    profiler.end_call(call, success=True, token_usage=TokenUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5))

    fail = profiler.start_call("manual-tool", call_type=CallType.TOOL)
    profiler.end_call(fail, success=False, error=RuntimeError("x"))

    assert len(profiler.get_calls(call_type=CallType.LLM)) == 1
    assert len(profiler.get_calls(success_only=True)) == 1
    assert len(profiler.get_calls(failed_only=True)) == 1

    summary = profiler.summary()
    assert summary["total_calls"] == 2
    assert summary["failed_calls"] == 1
    assert summary["token_usage"]["total_tokens"] == 5

    profiler.clear()
    assert profiler.calls == []


def test_chain_parent_ids_and_chain_failure() -> None:
    profiler = Profiler("chain")

    @profiler.tool("inside")
    def inside() -> None:
        return None

    with profiler.chain("pipeline"):
        inside()

    chain_call = next(c for c in profiler.calls if c.call_type == CallType.CHAIN)
    tool_call = next(c for c in profiler.calls if c.call_type == CallType.TOOL)
    assert tool_call.parent_id == chain_call.id

    with pytest.raises(RuntimeError):
        with profiler.chain("broken"):
            raise RuntimeError("boom")

    broken = [c for c in profiler.calls if c.name == "broken"][0]
    assert broken.success is False
    assert broken.error_type == "RuntimeError"


def test_module_level_decorators_record_calls() -> None:
    global_before = len(Profiler._local.__dict__) if hasattr(Profiler._local, "__dict__") else 0

    @profile_tool("global-tool")
    def gtool() -> str:
        return "ok"

    @profile_llm(model="global-model", name="global-llm")
    def gllm() -> SimpleNamespace:
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2))

    assert gtool() == "ok"
    gllm()
    assert global_before >= 0


@pytest.mark.asyncio
async def test_async_chain_methods_and_default_profiler_accessor() -> None:
    profiler = Profiler("achain")

    async with profiler.chain("async-chain"):
        pass

    chain_call = next(c for c in profiler.calls if c.name == "async-chain")
    assert chain_call.success is True
    assert get_default_profiler() is not None

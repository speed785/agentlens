import random
import importlib
import sys
import time

sys.path.insert(0, "../python")

def main() -> None:
    profiler_mod = importlib.import_module("agentlens")
    metrics_mod = importlib.import_module("agentlens.metrics")
    obs_mod = importlib.import_module("agentlens.observability")

    Profiler = profiler_mod.Profiler
    ObservabilityConfig = obs_mod.ObservabilityConfig
    reset_metrics = metrics_mod.reset_metrics
    export_prometheus = metrics_mod.export_prometheus

    reset_metrics()
    profiler = Profiler(
        name="observability-demo",
        observability=ObservabilityConfig(log_level="DEBUG", debug_mode=True),
    )

    @profiler.tool("web_lookup")
    def web_lookup(query: str) -> dict[str, object]:
        time.sleep(random.uniform(0.01, 0.05))
        return {"query": query, "results": 3}

    @profiler.llm(model="gpt-4o-mini", name="answer")
    def answer(_prompt: str):
        time.sleep(random.uniform(0.02, 0.08))

        class Usage:
            prompt_tokens = 42
            completion_tokens = 18
            total_tokens = 60

        class Response:
            model = "gpt-4o-mini"
            usage = Usage()

        return Response()

    with profiler.chain("pipeline"):
        data = web_lookup("latest ai agent tooling")
        answer(str(data))

    print("\nPrometheus metrics:\n")
    print(export_prometheus())


if __name__ == "__main__":
    main()

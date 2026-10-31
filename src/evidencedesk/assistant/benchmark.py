"""Optional C3 benchmark code. No model call or benchmark runs on import."""

import math
from collections.abc import Sequence
from statistics import mean, median
from time import perf_counter

from evidencedesk.assistant.generation import GENERATION_MODEL, OllamaGeneration
from evidencedesk.contracts.models import GenerationInput


def benchmark_qwen(
    generate: OllamaGeneration,
    workloads: Sequence[GenerationInput],
    *,
    repeats: int = 1,
) -> dict:
    """Run only when explicitly invoked; return measured results without saving prompts.

    Total-response token rate includes prompt/model-load time. It is not a pure
    decode-throughput measurement. Failures retain their actual error codes.
    """
    if type(repeats) is not int or repeats < 1 or not workloads:
        raise ValueError("Provide workloads and a positive repeat count.")
    samples = []
    for repeat in range(repeats):
        for workload_id, request in enumerate(workloads, start=1):
            started = perf_counter()
            response = generate(request)
            elapsed_ms = (perf_counter() - started) * 1000
            sample = {
                "repeat": repeat + 1,
                "workload_id": workload_id,
                "ok": response.ok and response.data is not None,
                "wall_ms": elapsed_ms,
                "error_code": response.error.code if response.error else None,
            }
            if response.ok and response.data is not None:
                result = response.data
                sample.update({
                    "model_digest": result.model_digest,
                    "server_duration_ms": result.duration_ms,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                    "completion_tokens_per_total_second": (
                        result.completion_tokens * 1000 / result.duration_ms
                        if result.duration_ms > 0 else None
                    ),
                })
            samples.append(sample)
    durations = sorted(sample["wall_ms"] for sample in samples if sample["ok"])
    return {
        "mode": "live",
        "model": GENERATION_MODEL,
        "samples": samples,
        "successful_calls": len(durations),
        "failed_calls": len(samples) - len(durations),
        "mean_wall_ms": mean(durations) if durations else None,
        "p50_wall_ms": median(durations) if durations else None,
        "p95_wall_ms": durations[math.ceil(len(durations) * 0.95) - 1] if durations else None,
        "load_state": "Uncontrolled; requests may include model loading or reuse a warm model.",
        "scope": "Generation latency/tokens only; no answer-quality or Ragas score is inferred.",
    }

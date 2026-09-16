from __future__ import annotations

import importlib
import json
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from statistics import mean
from typing import Protocol, TypeVar, cast

from pydantic import JsonValue

from core.settings import settings
from courserag.indexing.dense import LocalSentenceTransformerEmbeddingAdapter
from evaluation.io import atomic_write_json
from evaluation.p08_corpus import load_p08_child_corpus

T = TypeVar("T")


class MemoryInfo(Protocol):
    rss: int


class ProcessHandle(Protocol):
    def cpu_percent(self, interval: float | None = None) -> float: ...

    def memory_info(self) -> MemoryInfo: ...


class VirtualMemory(Protocol):
    total: int


class PsutilModule(Protocol):
    def Process(self) -> ProcessHandle: ...

    def cpu_count(self, logical: bool = True) -> int | None: ...

    def virtual_memory(self) -> VirtualMemory: ...


class CudaModule(Protocol):
    def reset_peak_memory_stats(self) -> None: ...

    def max_memory_allocated(self) -> int: ...

    def max_memory_reserved(self) -> int: ...

    def get_device_name(self, device: int) -> str: ...


class TorchVersion(Protocol):
    cuda: str | None


class TorchModule(Protocol):
    __version__: str
    cuda: CudaModule
    version: TorchVersion


@dataclass
class ResourceSample:
    process_cpu_percent: float
    process_rss_bytes: int
    gpu_utilization_percent: float | None
    gpu_memory_used_mib: float | None
    gpu_power_watts: float | None


@dataclass
class ResourceMonitor:
    samples: list[ResourceSample] = field(default_factory=list)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        psutil = _psutil_module()
        process = psutil.Process()
        process.cpu_percent(interval=None)
        self._thread = threading.Thread(target=self._run, args=(process,), daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, float | int | None]:
        psutil = _psutil_module()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logical_cpus = max(1, psutil.cpu_count(logical=True) or 1)
        cpu = [item.process_cpu_percent for item in self.samples]
        rss = [item.process_rss_bytes for item in self.samples]
        gpu_util = [
            item.gpu_utilization_percent
            for item in self.samples
            if item.gpu_utilization_percent is not None
        ]
        gpu_memory = [
            item.gpu_memory_used_mib
            for item in self.samples
            if item.gpu_memory_used_mib is not None
        ]
        gpu_power = [
            item.gpu_power_watts for item in self.samples if item.gpu_power_watts is not None
        ]
        return {
            "sample_count": len(self.samples),
            "process_cpu_percent_mean_one_core_100": round(mean(cpu), 2) if cpu else None,
            "process_cpu_percent_peak_one_core_100": round(max(cpu), 2) if cpu else None,
            "process_cpu_percent_mean_total_machine": (
                round(mean(cpu) / logical_cpus, 2) if cpu else None
            ),
            "process_cpu_percent_peak_total_machine": (
                round(max(cpu) / logical_cpus, 2) if cpu else None
            ),
            "process_rss_peak_bytes": max(rss) if rss else None,
            "gpu_utilization_percent_mean": round(mean(gpu_util), 2) if gpu_util else None,
            "gpu_utilization_percent_peak": round(max(gpu_util), 2) if gpu_util else None,
            "gpu_memory_used_mib_peak_system": round(max(gpu_memory), 2) if gpu_memory else None,
            "gpu_power_watts_mean": round(mean(gpu_power), 2) if gpu_power else None,
            "gpu_power_watts_peak": round(max(gpu_power), 2) if gpu_power else None,
        }

    def _run(self, process: ProcessHandle) -> None:
        while not self._stop.is_set():
            gpu_utilization, gpu_memory, gpu_power = _gpu_sample()
            self.samples.append(
                ResourceSample(
                    process_cpu_percent=process.cpu_percent(interval=None),
                    process_rss_bytes=process.memory_info().rss,
                    gpu_utilization_percent=gpu_utilization,
                    gpu_memory_used_mib=gpu_memory,
                    gpu_power_watts=gpu_power,
                )
            )
            self._stop.wait(0.2)


def _gpu_sample() -> tuple[float | None, float | None, float | None]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,power.draw",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    if completed.returncode != 0:
        return None, None, None
    values = [item.strip() for item in completed.stdout.splitlines()[0].split(",")]
    if len(values) != 3:
        return None, None, None
    return (
        _optional_float(values[0]),
        _optional_float(values[1]),
        _optional_float(values[2]),
    )


def _optional_float(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _phase(call: Callable[[], T]) -> tuple[T, float, dict[str, float | int | None]]:
    torch = _torch_module()
    monitor = ResourceMonitor()
    torch.cuda.reset_peak_memory_stats()
    monitor.start()
    started = time.perf_counter()
    try:
        result = call()
    finally:
        elapsed = time.perf_counter() - started
        resources = monitor.stop()
    resources["torch_cuda_peak_allocated_bytes"] = torch.cuda.max_memory_allocated()
    resources["torch_cuda_peak_reserved_bytes"] = torch.cuda.max_memory_reserved()
    return result, elapsed, resources


def _adapter() -> LocalSentenceTransformerEmbeddingAdapter:
    required = (
        settings.COURSERAG_EMBEDDING_MODEL_PATH,
        settings.COURSERAG_EMBEDDING_MODEL,
        settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256,
        settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256,
    )
    if any(value is None for value in required):
        raise ValueError("Local Embedding benchmark configuration is incomplete")
    return LocalSentenceTransformerEmbeddingAdapter(
        model_path=str(required[0]),
        model_name=str(required[1]),
        model_bundle_sha256=str(required[2]),
        weights_sha256=str(required[3]),
        device=settings.COURSERAG_EMBEDDING_DEVICE,
        dtype=settings.COURSERAG_EMBEDDING_DTYPE,
        max_length=settings.COURSERAG_EMBEDDING_MAX_LENGTH,
        batch_size=settings.COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE,
        query_prompt_name=settings.COURSERAG_EMBEDDING_QUERY_PROMPT_NAME,
    )


def run_benchmark(repository_root: Path, output_path: Path) -> Path:
    if settings.COURSERAG_EMBEDDING_PROVIDER != "local_sentence_transformers":
        raise ValueError("Benchmark requires the local SentenceTransformers Provider")
    torch = _torch_module()
    psutil = _psutil_module()
    corpora = load_p08_child_corpus(repository_root)
    all_texts = sorted(
        (item.text for corpus in corpora.values() for item in corpus),
        key=lambda item: (len(item), item),
    )
    representative = [all_texts[round(index * (len(all_texts) - 1) / 31)] for index in range(32)]
    adapter_object, load_seconds, load_resources = _phase(_adapter)
    adapter = adapter_object
    if not isinstance(adapter, LocalSentenceTransformerEmbeddingAdapter):
        raise TypeError("Local Embedding benchmark loaded an unexpected Adapter")
    adapter.embed_documents(representative[:1])
    batches: dict[str, object] = {}
    for batch_size in (1, 8, 16):
        durations: list[float] = []
        resources: list[dict[str, float | int | None]] = []
        for _ in range(3):
            _, elapsed, sample = _phase(
                partial(adapter.embed_documents, representative[:batch_size])
            )
            durations.append(elapsed)
            resources.append(sample)
        batches[str(batch_size)] = {
            "repetitions": 3,
            "mean_seconds": round(mean(durations), 4),
            "items_per_second": round(batch_size / mean(durations), 3),
            "resource_samples": resources,
        }
    _, query_seconds, query_resources = _phase(
        lambda: adapter.embed_query("What knowledge explains the requested course concept?")
    )
    baseline_gpu = _gpu_sample()
    payload = {
        "schema_version": "courserag.p08-local-embedding-benchmark.v1",
        "model_identity": adapter.identity,
        "model_bundle_sha256": adapter.model_bundle_sha256,
        "weights_sha256": adapter.weights_sha256,
        "corpus_item_count": len(all_texts),
        "representative_item_count": len(representative),
        "content_persisted": False,
        "runtime": {
            "torch": torch.__version__,
            "torch_cuda_runtime": torch.version.cuda,
            "gpu_name": torch.cuda.get_device_name(0),
            "logical_cpu_count": psutil.cpu_count(logical=True),
            "physical_cpu_count": psutil.cpu_count(logical=False),
            "system_memory_bytes": psutil.virtual_memory().total,
            "device": adapter.device,
            "dtype": adapter.dtype,
            "max_length": adapter.max_length,
            "internal_batch_size": adapter.batch_size,
        },
        "baseline_system_gpu": {
            "utilization_percent": baseline_gpu[0],
            "memory_used_mib": baseline_gpu[1],
            "power_watts": baseline_gpu[2],
        },
        "cold_load": {"seconds": round(load_seconds, 4), "resources": load_resources},
        "document_batches": batches,
        "single_query": {
            "seconds": round(query_seconds, 4),
            "resources": query_resources,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_path, cast(JsonValue, json.loads(json.dumps(payload))))
    return output_path


def _torch_module() -> TorchModule:
    try:
        module = importlib.import_module("torch")
    except ImportError as exc:
        raise RuntimeError("Local Embedding benchmark requires the CUDA optional extra") from exc
    return cast(TorchModule, module)


def _psutil_module() -> PsutilModule:
    try:
        module = importlib.import_module("psutil")
    except ImportError as exc:
        raise RuntimeError("Local Embedding benchmark requires the CUDA optional extra") from exc
    return cast(PsutilModule, module)


if __name__ == "__main__":
    print(
        run_benchmark(
            Path.cwd(),
            Path("storage_eval/p08_local_embedding/benchmark.json"),
        )
    )

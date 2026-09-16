"""Provider contract, bounded concurrency, retry and identity-safe Window cache."""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Lock
from typing import Protocol

from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    ProviderUsage,
    SectionWindow,
    WindowExtractionResult,
    canonical_json_bytes,
    sha256_bytes,
)


class KnowledgePointProviderError(RuntimeError):
    """Stable base error that never embeds credentials or response bodies."""


class KnowledgePointProviderUnavailable(KnowledgePointProviderError):
    pass


class KnowledgePointProviderTransientError(KnowledgePointProviderError):
    pass


class KnowledgePointProviderResponseError(KnowledgePointProviderError):
    pass


@dataclass(frozen=True)
class ProviderExtraction:
    candidates: tuple[KnowledgePointCandidate, ...]
    usage: ProviderUsage = ProviderUsage()


class KnowledgePointProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def structured_output_method(self) -> str: ...

    def extract(self, window: SectionWindow, prompt: str) -> ProviderExtraction: ...


class KnowledgePointExtractionCache(Protocol):
    def get(self, cache_key: str) -> WindowExtractionResult | None: ...

    def begin(self, window: SectionWindow, cache_key: str) -> None: ...

    def put(self, cache_key: str, result: WindowExtractionResult) -> None: ...

    def fail(self, window: SectionWindow, cache_key: str, error_code: str) -> None: ...


class InMemoryExtractionCache:
    def __init__(self) -> None:
        self._values: dict[str, WindowExtractionResult] = {}
        self._lock = Lock()

    def get(self, cache_key: str) -> WindowExtractionResult | None:
        with self._lock:
            return self._values.get(cache_key)

    def begin(self, window: SectionWindow, cache_key: str) -> None:
        del window, cache_key

    def put(self, cache_key: str, result: WindowExtractionResult) -> None:
        with self._lock:
            existing = self._values.get(cache_key)
            if existing is not None and existing.result_sha256 != result.result_sha256:
                raise KnowledgePointProviderResponseError(
                    "Knowledge Point cache identity already has different output"
                )
            self._values[cache_key] = result

    def fail(self, window: SectionWindow, cache_key: str, error_code: str) -> None:
        del window, cache_key, error_code


def extraction_cache_key(
    window: SectionWindow,
    *,
    prompt_sha256: str,
    provider: str,
    model: str,
    structured_output_method: str,
    extractor_profile_sha256: str,
) -> str:
    return sha256_bytes(
        canonical_json_bytes(
            {
                "window_content_sha256": window.content_sha256,
                "evidence_ids": [item.evidence_id for item in window.evidence],
                "prompt_sha256": prompt_sha256,
                "provider": provider,
                "model": model,
                "structured_output_method": structured_output_method,
                "extractor_profile_sha256": extractor_profile_sha256,
            }
        )
    )


class KnowledgePointExtractionRunner:
    def __init__(
        self,
        provider: KnowledgePointProvider,
        cache: KnowledgePointExtractionCache,
        *,
        prompt: str,
        prompt_sha256: str,
        extractor_profile_sha256: str,
        concurrency: int = 4,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        retry_max_seconds: float = 30.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if concurrency < 1:
            raise ValueError("Knowledge Point concurrency must be positive")
        if max_retries < 0:
            raise ValueError("Knowledge Point max retries cannot be negative")
        self.provider = provider
        self.cache = cache
        self.prompt = prompt
        self.prompt_sha256 = prompt_sha256
        self.extractor_profile_sha256 = extractor_profile_sha256
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds
        self.sleeper = sleeper
        self.last_provider_call_count = 0
        self.last_cache_hit_count = 0

    def run(
        self, windows: tuple[SectionWindow, ...], *, force: bool = False
    ) -> tuple[WindowExtractionResult, ...]:
        if len({window.window_id for window in windows}) != len(windows):
            raise ValueError("Section Windows must be unique")
        results: dict[str, WindowExtractionResult] = {}
        missing: list[tuple[SectionWindow, str]] = []
        for window in windows:
            key = self._cache_key(window)
            cached = None if force else self.cache.get(key)
            if cached is None:
                missing.append((window, key))
            else:
                self._validate_result(window, cached)
                results[window.window_id] = cached
        self.last_provider_call_count = len(missing)
        self.last_cache_hit_count = len(windows) - len(missing)

        if missing:
            with ThreadPoolExecutor(max_workers=self.concurrency) as executor:
                futures = {}
                for window, key in missing:
                    self.cache.begin(window, key)
                    futures[executor.submit(self._extract_one, window)] = (window, key)
                for future in as_completed(futures):
                    window, key = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        self.cache.fail(window, key, type(exc).__name__)
                        raise
                    self.cache.put(key, result)
                    results[window.window_id] = result
        return tuple(results[window.window_id] for window in windows)

    def _extract_one(self, window: SectionWindow) -> WindowExtractionResult:
        started = time.monotonic()
        attempt = 0
        while True:
            try:
                response = self.provider.extract(window, self.prompt)
                result = WindowExtractionResult(
                    window_id=window.window_id,
                    window_content_sha256=window.content_sha256,
                    provider=self.provider.provider_name,
                    model=self.provider.model_name,
                    prompt_sha256=self.prompt_sha256,
                    extractor_profile_sha256=self.extractor_profile_sha256,
                    candidates=response.candidates,
                    usage=response.usage,
                    duration_ms=max(0, int((time.monotonic() - started) * 1000)),
                )
                self._validate_result(window, result)
                return result
            except KnowledgePointProviderTransientError:
                if attempt >= self.max_retries:
                    raise
                delay = min(
                    self.retry_max_seconds,
                    self.retry_base_seconds * (2**attempt),
                )
                attempt += 1
                self.sleeper(delay)

    def _cache_key(self, window: SectionWindow) -> str:
        return extraction_cache_key(
            window,
            prompt_sha256=self.prompt_sha256,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            structured_output_method=self.provider.structured_output_method,
            extractor_profile_sha256=self.extractor_profile_sha256,
        )

    def _validate_result(self, window: SectionWindow, result: WindowExtractionResult) -> None:
        if result.window_id != window.window_id:
            raise KnowledgePointProviderResponseError("Provider returned the wrong Window ID")
        if result.window_content_sha256 != window.content_sha256:
            raise KnowledgePointProviderResponseError(
                "Provider Result Window Hash differs from the requested Window"
            )
        if (
            result.provider != self.provider.provider_name
            or result.model != self.provider.model_name
        ):
            raise KnowledgePointProviderResponseError(
                "Provider Result identity differs from config"
            )
        if result.prompt_sha256 != self.prompt_sha256:
            raise KnowledgePointProviderResponseError("Provider Result Prompt Hash differs")
        if result.extractor_profile_sha256 != self.extractor_profile_sha256:
            raise KnowledgePointProviderResponseError("Provider Result Profile Hash differs")
        allowed = {item.evidence_id for item in window.evidence}
        for candidate in result.candidates:
            if not {item.evidence_id for item in candidate.evidence_refs}.issubset(allowed):
                raise KnowledgePointProviderResponseError(
                    "Provider Candidate references Evidence outside the Window"
                )

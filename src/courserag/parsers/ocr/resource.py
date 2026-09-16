"""Fail-closed subprocess resource guard for OCR engines."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class OCRProviderError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        duration_ms: int = 0,
        peak_memory_bytes: int = 0,
    ) -> None:
        super().__init__(message)
        self.duration_ms = duration_ms
        self.peak_memory_bytes = peak_memory_bytes


class OCRProviderUnavailable(OCRProviderError):
    pass


class OCRIdentityError(OCRProviderError):
    pass


class OCRResourceLimitError(OCRProviderError):
    def __init__(
        self,
        message: str,
        *,
        duration_ms: int = 0,
        peak_memory_bytes: int = 0,
    ) -> None:
        super().__init__(
            message,
            duration_ms=duration_ms,
            peak_memory_bytes=peak_memory_bytes,
        )


@dataclass(frozen=True)
class OCRCommandOutput:
    stdout: bytes
    duration_ms: int
    peak_memory_bytes: int


class ProcessTreeSampler(Protocol):
    def rss_bytes(self, pid: int) -> int: ...

    def terminate(self, pid: int) -> None: ...


class PsutilProcessTreeSampler:
    def __init__(self) -> None:
        try:
            import psutil
        except ImportError as exc:
            raise OCRProviderUnavailable(
                "psutil is required to enforce OCR process-tree memory limits"
            ) from exc
        self._psutil = psutil

    def rss_bytes(self, pid: int) -> int:
        try:
            process = self._psutil.Process(pid)
            processes = [process, *process.children(recursive=True)]
            return sum(item.memory_info().rss for item in processes if item.is_running())
        except self._psutil.Error:
            return 0

    def terminate(self, pid: int) -> None:
        try:
            process = self._psutil.Process(pid)
            children = process.children(recursive=True)
            for child in children:
                child.kill()
            process.kill()
            self._psutil.wait_procs([*children, process], timeout=5)
        except self._psutil.Error:
            return


class OCRCommandRunner(Protocol):
    def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_memory_bytes: int,
    ) -> OCRCommandOutput: ...


class SubprocessResourceGuard:
    def __init__(self, sampler: ProcessTreeSampler | None = None) -> None:
        self.sampler = sampler or PsutilProcessTreeSampler()

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_memory_bytes: int,
    ) -> OCRCommandOutput:
        started = time.monotonic()
        process = subprocess.Popen(
            list(command),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        peak = 0
        while process.poll() is None:
            elapsed = time.monotonic() - started
            rss = self.sampler.rss_bytes(process.pid)
            peak = max(peak, rss)
            if rss > max_memory_bytes:
                self.sampler.terminate(process.pid)
                process.wait(timeout=5)
                raise OCRResourceLimitError(
                    "OCR page exceeded the configured memory limit",
                    duration_ms=round(elapsed * 1000),
                    peak_memory_bytes=peak,
                )
            if elapsed > timeout_seconds:
                self.sampler.terminate(process.pid)
                process.wait(timeout=5)
                raise OCRResourceLimitError(
                    "OCR page exceeded the configured timeout",
                    duration_ms=round(elapsed * 1000),
                    peak_memory_bytes=peak,
                )
            time.sleep(0.05)
        stdout, _stderr = process.communicate()
        duration_ms = round((time.monotonic() - started) * 1000)
        if process.returncode != 0:
            raise OCRProviderError(
                "OCR provider process failed; inspect protected service logs",
                duration_ms=duration_ms,
                peak_memory_bytes=peak,
            )
        return OCRCommandOutput(
            stdout=stdout,
            duration_ms=duration_ms,
            peak_memory_bytes=peak,
        )

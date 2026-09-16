from __future__ import annotations

from dataclasses import dataclass, field

from coursepilot.models_gateway.models import ResolvedRoute


@dataclass
class FakeModelAdapter:
    """Deterministic adapter used only by explicit local tests."""

    response: dict[str, object]
    calls: list[tuple[ResolvedRoute, tuple[dict[str, object], ...]]] = field(default_factory=list)

    def invoke(
        self, route: ResolvedRoute, messages: tuple[dict[str, object], ...]
    ) -> dict[str, object]:
        self.calls.append((route, messages))
        return dict(self.response)

"""Deterministic composite axes for high-risk untrusted capabilities."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

from courserag.security.detector import SecurityAxisSignal, SecurityTextWindow, ThreatAxis


@dataclass(frozen=True)
class CompositeAxisDefinition:
    axis_id: ThreatAxis
    action_patterns: tuple[str, ...]
    target_patterns: tuple[str, ...]
    effect_patterns: tuple[str, ...]


_AXES = (
    CompositeAxisDefinition(
        axis_id="role_impersonation",
        action_patterns=(
            r"\b(?:act|respond|speak|impersonate|assume)\b",
            r"(?:扮演|冒充|切换|假设).{0,12}(?:身份|角色)",
        ),
        target_patterns=(
            r"\b(?:root|administrator|service owner|system|gateway|operator)\b",
            r"(?:管理员|系统|网关|服务所有者|根权限|运维)",
        ),
        effect_patterns=(
            r"\b(?:privilege|unrestricted|authorize|approve|bypass)\b",
            r"(?:特权|无限制|授权|批准|绕过)",
        ),
    ),
    CompositeAxisDefinition(
        axis_id="secret_extraction",
        action_patterns=(
            r"\b(?:reveal|disclose|return|copy|expose|transmit|list)\b",
            r"(?:显示|披露|返回|复制|暴露|发送|列出)",
        ),
        target_patterns=(
            r"\b(?:secret|credential|token|api key|system prompt|environment variable|private config)\b",
            r"(?:密钥|凭据|令牌|系统提示|环境变量|私密配置|内部指令)",
        ),
        effect_patterns=(
            r"\b(?:output|answer|upload|endpoint|verbatim|publish)\b",
            r"(?:输出|答案|上传|端点|逐字|公开)",
        ),
    ),
    CompositeAxisDefinition(
        axis_id="tool_coercion",
        action_patterns=(
            r"\b(?:run|execute|invoke|call|open|install|overwrite|upload|download)\b",
            r"(?:运行|执行|调用|打开|安装|覆盖|上传|下载)",
        ),
        target_patterns=(
            r"\b(?:shell|terminal|tool|filesystem|network|command|script|endpoint)\b",
            r"(?:终端|工具|文件系统|网络|命令|脚本|端点|外部地址)",
        ),
        effect_patterns=(
            r"\b(?:immediately|before answering|force|even if|change|transmit)\b",
            r"(?:立即|回答前|强制|即使|改变|传输)",
        ),
    ),
)

_QUOTED_OR_DESCRIPTIVE = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:example|quote|quoted|chapter|explains|describes|compare|must not|do not obey|disabled)\b",
        r"(?:示例|引用|本章|解释|描述|比较|不得执行|不要服从|已禁用)",
    )
)
_OBFUSCATED = re.compile(r"(?:\w[\s.\-_]){3,}\w|[\u200b\u200c\u200d\ufeff\u2060]")


class StructuredCapabilityAxes:
    detector_id = "courserag/structured-capability-axes@v1"

    def validate_environment(self) -> None:
        return None

    def detect(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[SecurityAxisSignal, ...]:
        output: list[SecurityAxisSignal] = []
        for window in windows:
            text = _normalize(window.text)
            context_guard = any(pattern.search(text) for pattern in _QUOTED_OR_DESCRIPTIVE)
            for definition in _AXES:
                evidence = _evidence(definition, text)
                ready = len(evidence) == 3 and not context_guard
                if evidence:
                    output.append(
                        SecurityAxisSignal(
                            signal_id=_signal_id(window.window_id, definition.axis_id, evidence),
                            window_id=window.window_id,
                            axis_id=definition.axis_id,
                            score=len(evidence) / 3,
                            detector_id=self.detector_id,
                            evidence_ids=evidence,
                            decision_ready=ready,
                        )
                    )
            if _OBFUSCATED.search(window.text):
                output.append(
                    SecurityAxisSignal(
                        signal_id=_signal_id(
                            window.window_id, "obfuscation_modifier", ("surface_obfuscation",)
                        ),
                        window_id=window.window_id,
                        axis_id="obfuscation_modifier",
                        score=1,
                        detector_id=self.detector_id,
                        evidence_ids=("surface_obfuscation",),
                        decision_ready=False,
                    )
                )
        return tuple(output)


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _evidence(definition: CompositeAxisDefinition, text: str) -> tuple[str, ...]:
    groups = (
        ("action", definition.action_patterns),
        ("target", definition.target_patterns),
        ("effect", definition.effect_patterns),
    )
    return tuple(
        name
        for name, patterns in groups
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)
    )


def _signal_id(window_id: str, axis_id: object, evidence: object) -> str:
    payload = f"{window_id}\x1f{axis_id}\x1f{evidence}".encode()
    return f"secsig_{hashlib.sha256(payload).hexdigest()[:24]}"

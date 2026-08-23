"""Deterministic, scope-aware action-target-effect security axes."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from courserag.security.detector import SecurityAxisSignal, SecurityTextWindow, ThreatAxis

InstructionScope = Literal[
    "quoted",
    "negated",
    "educational",
    "defensive_description",
    "approved_procedure",
    "operative",
]

_ZERO_WIDTH = frozenset("\u200b\u200c\u200d\ufeff\u2060")
_SEPARATOR = re.compile(r"[\s.\-_]")


@dataclass(frozen=True)
class NormalizedSecurityText:
    """A normalized view whose characters map back to original offsets."""

    text: str
    original_offsets: tuple[int, ...]

    def original_span(self, start: int, end: int) -> tuple[int, int]:
        if not 0 <= start < end <= len(self.original_offsets):
            raise ValueError("normalized security span is outside the source text")
        return self.original_offsets[start], self.original_offsets[end - 1] + 1


@dataclass(frozen=True)
class CompositeAxisDefinition:
    axis_id: ThreatAxis
    actions: tuple[str, ...]
    effect_patterns: tuple[str, ...]
    target_patterns: tuple[str, ...] = ()


_AXES = (
    CompositeAxisDefinition(
        axis_id="policy_override",
        actions=(
            "bypass",
            "ignore",
            "override",
            "disable",
            "discard",
            "skip",
            "remove",
            "绕过",
            "忽略",
            "覆盖",
            "禁用",
            "丢弃",
            "跳过",
            "移除",
        ),
        target_patterns=(
            r"\b(?:policy|guard(?:rail)?|gate|approval|acl|authorization|check|scope|boundary|route|capability|redaction|control)\b",
            r"(?:策略|护栏|门禁|审批|权限|授权|校验|检查|范围|边界|路由|能力|脱敏|控制)",
        ),
        effect_patterns=(
            r"\b(?:continue|proceed|operate).{0,40}\b(?:without|missing).{0,30}\b(?:required|necessary|approved)?\s*(?:control|check|approval|authorization)\b",
            r"\b(?:highest authority|unrestricted|nonbinding|no longer bound)\b",
            r"(?:缺少|无需|没有).{0,12}(?:必需|必要|批准|授权)?.{0,8}(?:控制|校验|审批|授权).{0,12}(?:继续|执行|运行)",
            r"(?:最高权限|不受限制|不再约束)",
        ),
    ),
    CompositeAxisDefinition(
        axis_id="role_impersonation",
        actions=(
            "act as",
            "respond as",
            "speak as",
            "impersonate",
            "assume",
            "扮演",
            "冒充",
            "切换身份",
            "假设身份",
        ),
        target_patterns=(
            r"\b(?:administrator|owner|approver|reviewer|publisher|provider|operator|coordinator|gateway|service|developer|root|system)\b",
            r"(?:管理员|所有者|审批者|审核者|发布者|提供商|操作员|协调者|网关|服务|开发者|系统|运维|根权限)",
        ),
        effect_patterns=(
            r"\b(?:grant|obtain|gain|use).{0,40}\b(?:authority|privilege|permission|access)\b",
            r"\b(?:authority|privilege|permission|access).{0,40}\b(?:never|not).{0,12}\bapproved\b",
            r"\b(?:unrestricted privilege|authorize|approve)\b",
            r"(?:获得|授予|取得|使用).{0,20}(?:权限|特权|访问权)",
            r"(?:从未|没有|未经).{0,12}(?:批准|授权).{0,12}(?:权限|特权|访问权)",
        ),
    ),
    CompositeAxisDefinition(
        axis_id="secret_extraction",
        actions=(
            "reveal",
            "disclose",
            "return",
            "copy",
            "expose",
            "transmit",
            "list",
            "显示",
            "披露",
            "返回",
            "复制",
            "暴露",
            "发送",
            "列出",
            "泄露",
        ),
        target_patterns=(
            r"\b(?:secret|credential|token|password|api key|encryption key|system prompt|environment|connection string|cookie|claim|authorization header|signing key)\b",
            r"(?:秘密|密钥|凭据|令牌|密码|系统提示|环境变量|连接字符串|会话|声明|授权头|签名密钥|私密配置)",
        ),
        effect_patterns=(
            r"\b(?:expose|disclose|publish|return|output|transmit).{0,40}\b(?:protected|private|secret|configuration|credential|value|data)\b",
            r"\b(?:output|answer|upload|endpoint|verbatim|publish)\b",
            r"(?:暴露|披露|公开|返回|输出|传输).{0,20}(?:受保护|私密|秘密|配置|凭据|数据|值)",
        ),
    ),
    CompositeAxisDefinition(
        axis_id="tool_coercion",
        actions=(
            "run",
            "execute",
            "invoke",
            "call",
            "open",
            "install",
            "overwrite",
            "upload",
            "download",
            "运行",
            "执行",
            "调用",
            "打开",
            "安装",
            "覆盖",
            "上传",
            "下载",
        ),
        target_patterns=(
            r"\b(?:shell|terminal|tool|file|filesystem|network|http|command|script|endpoint|database|index|process|callback|writeback|mutation|upload|launch|replacement|cancellation|lookup|switch)\b",
            r"(?:终端|工具|文件|文件系统|网络|命令|脚本|端点|数据库|索引|进程|回调|写回|修改|上传|启动|替换|取消|查询|切换)",
        ),
        effect_patterns=(
            r"\b(?:perform|cause|produce|trigger|create).{0,40}\b(?:unapproved|unauthorized|forbidden).{0,20}\b(?:side effect|action|change|write|request)\b",
            r"\b(?:immediately|before answering|force|even if|change|transmit)\b",
            r"(?:产生|执行|触发|造成).{0,20}(?:未经批准|未授权|禁止).{0,12}(?:副作用|操作|变更|写入|请求)",
        ),
    ),
)

_EXPLICIT_TARGET = (
    re.compile(r"\btarget\s+(?:named\s+)?[\"'“‘]?[^\"'”’，,.;]{2,100}", re.IGNORECASE),
    re.compile(r"目标\s*[\"'“‘]?[^\"'”’，,.;]{1,100}", re.IGNORECASE),
)
_OBFUSCATED = re.compile(r"(?:\w[\s.\-_]){2,}\w|[\u200b\u200c\u200d\ufeff\u2060]")

_QUOTED = (
    re.compile(r"\b(?:quote|quotes|quoted|excerpt)\b", re.IGNORECASE),
    re.compile(r"(?:引文|摘录)", re.IGNORECASE),
)
_EDUCATIONAL = (
    re.compile(r"\b(?:chapter|example|explains?|describes?|teaching material)\b", re.IGNORECASE),
    re.compile(r"(?:本章|示例|课程材料说明|用于教学|解释|描述)", re.IGNORECASE),
)
_DEFENSIVE = (
    re.compile(r"\b(?:defensive|mitigation|protect|prevention|detection rule)\b", re.IGNORECASE),
    re.compile(r"(?:防御|防护|缓解|预防|检测规则)", re.IGNORECASE),
)
_APPROVED = (
    re.compile(r"\b(?:approved procedure|approved workflow|runbook)\b", re.IGNORECASE),
    re.compile(r"(?:已批准流程|批准的操作规程|运行手册)", re.IGNORECASE),
)


class StructuredCapabilityAxes:
    def __init__(self, *, version: Literal["v1", "v2"] = "v1") -> None:
        self.detector_id = f"courserag/structured-capability-axes@{version}"

    def validate_environment(self) -> None:
        return None

    def detect(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[SecurityAxisSignal, ...]:
        output: list[SecurityAxisSignal] = []
        for window in windows:
            normalized = normalize_security_text(window.text)
            deobfuscated = deobfuscate_security_text(normalized)
            scope = classify_instruction_scope(deobfuscated.text)
            for definition in _AXES:
                evidence = _evidence(definition, deobfuscated.text)
                ready = len(evidence) == 3 and scope == "operative"
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
                evidence = ("surface_obfuscation",)
                output.append(
                    SecurityAxisSignal(
                        signal_id=_signal_id(window.window_id, "obfuscation_modifier", evidence),
                        window_id=window.window_id,
                        axis_id="obfuscation_modifier",
                        score=1,
                        detector_id=self.detector_id,
                        evidence_ids=evidence,
                        decision_ready=False,
                    )
                )
        return tuple(output)


def normalize_security_text(text: str) -> NormalizedSecurityText:
    characters: list[str] = []
    offsets: list[int] = []
    pending_space: int | None = None
    for offset, character in enumerate(text):
        if character in _ZERO_WIDTH:
            continue
        for normalized in unicodedata.normalize("NFKC", character).casefold():
            if normalized.isspace():
                if characters:
                    pending_space = offset
                continue
            if pending_space is not None:
                characters.append(" ")
                offsets.append(pending_space)
                pending_space = None
            characters.append(normalized)
            offsets.append(offset)
    return NormalizedSecurityText("".join(characters), tuple(offsets))


def deobfuscate_security_text(view: NormalizedSecurityText) -> NormalizedSecurityText:
    matches: list[tuple[int, int, str]] = []
    actions = {value.casefold() for definition in _AXES for value in definition.actions}
    for action in sorted(actions, key=len, reverse=True):
        pattern = _separated_action_pattern(action)
        matches.extend(
            (match.start(), match.end(), action) for match in pattern.finditer(view.text)
        )
    selected: list[tuple[int, int, str]] = []
    cursor = 0
    for start, end, action in sorted(matches, key=lambda item: (item[0], -item[1])):
        if start < cursor:
            continue
        selected.append((start, end, action))
        cursor = end
    if not selected:
        return view
    output: list[str] = []
    offsets: list[int] = []
    cursor = 0
    for start, end, action in selected:
        output.extend(view.text[cursor:start])
        offsets.extend(view.original_offsets[cursor:start])
        source_offsets = [
            view.original_offsets[index]
            for index in range(start, end)
            if not _SEPARATOR.fullmatch(view.text[index])
        ]
        if len(source_offsets) != len(action):
            source_offsets = [view.original_offsets[start]] * len(action)
        output.extend(action)
        offsets.extend(source_offsets)
        cursor = end
    output.extend(view.text[cursor:])
    offsets.extend(view.original_offsets[cursor:])
    return NormalizedSecurityText("".join(output), tuple(offsets))


def classify_instruction_scope(text: str) -> InstructionScope:
    value = deobfuscate_security_text(normalize_security_text(text)).text
    if any(pattern.search(value) for pattern in _QUOTED):
        return "quoted"
    if _has_negated_dangerous_action(value):
        return "negated"
    if any(pattern.search(value) for pattern in _EDUCATIONAL):
        return "educational"
    if any(pattern.search(value) for pattern in _DEFENSIVE):
        return "defensive_description"
    if any(pattern.search(value) for pattern in _APPROVED):
        return "approved_procedure"
    return "operative"


def _has_negated_dangerous_action(text: str) -> bool:
    actions = sorted(
        {value.casefold() for definition in _AXES for value in definition.actions},
        key=len,
        reverse=True,
    )
    english = "|".join(re.escape(value) for value in actions if value.isascii())
    chinese = "|".join(re.escape(value) for value in actions if not value.isascii())
    return bool(
        re.search(rf"\b(?:do not|must not|never|cannot)\s+(?:{english})\b", text)
        or re.search(rf"(?:不得|不要|禁止|不能)\s*(?:{chinese})", text)
    )


def _separated_action_pattern(action: str) -> re.Pattern[str]:
    separator = r"[\s.\-_]*"
    body = separator.join(re.escape(character) for character in action)
    if action.isascii() and action[0].isalnum() and action[-1].isalnum():
        body = rf"(?<!\w){body}(?!\w)"
    return re.compile(body, re.IGNORECASE)


def _evidence(definition: CompositeAxisDefinition, text: str) -> tuple[str, ...]:
    action = any(_separated_action_pattern(value).search(text) for value in definition.actions)
    target = any(pattern.search(text) for pattern in _EXPLICIT_TARGET) or any(
        re.search(pattern, text, re.IGNORECASE) for pattern in definition.target_patterns
    )
    effect = any(re.search(pattern, text, re.IGNORECASE) for pattern in definition.effect_patterns)
    return tuple(
        name
        for name, matched in (("action", action), ("target", target), ("effect", effect))
        if matched
    )


def _signal_id(window_id: str, axis_id: object, evidence: object) -> str:
    payload = f"{window_id}\x1f{axis_id}\x1f{evidence}".encode()
    return f"secsig_{hashlib.sha256(payload).hexdigest()[:24]}"

"""OpenAI-compatible CourseRAG Knowledge Point Provider Adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from openai import APIConnectionError, APITimeoutError, RateLimitError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from core.settings import Settings, settings
from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    ProviderUsage,
    SectionWindow,
)
from courserag.knowledge_points.provider import (
    KnowledgePointProviderResponseError,
    KnowledgePointProviderTransientError,
    KnowledgePointProviderUnavailable,
    ProviderExtraction,
)


class _CandidateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: tuple[KnowledgePointCandidate, ...] = Field(max_length=40)


_VALIDATION_REASON_CODES = {
    "Knowledge Point Candidate Evidence references must be unique": "duplicate_evidence_ref",
    "Knowledge Point Candidate requires primary Evidence": "missing_primary_evidence",
    "Knowledge Point Candidate aliases must be unique": "duplicate_alias",
    "Canonical Knowledge Point name cannot repeat as an Alias": "canonical_repeated_as_alias",
}


class OpenAICompatibleKnowledgePointProvider:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: SecretStr,
        timeout_seconds: float,
        temperature: float = 0.1,
        structured_output_method: Literal["json_mode", "function_calling"] = "json_mode",
    ) -> None:
        self._model_name = model
        self._structured_output_method = structured_output_method
        self._client = ChatOpenAI(
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=0,
            temperature=temperature,
        )
        # No reasoning/thinking arguments are sent. The selected endpoint only has
        # to satisfy the explicit Structured Output contract.
        self._structured = self._client.with_structured_output(
            _CandidateBatch,
            method=structured_output_method,
            include_raw=True,
        )

    @property
    def provider_name(self) -> str:
        return "openai-compatible"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def structured_output_method(self) -> str:
        return self._structured_output_method

    def extract(self, window: SectionWindow, prompt: str) -> ProviderExtraction:
        source_payload = {
            "course_id": window.course_id,
            "section_id": window.section_id,
            "section_title": window.section_title,
            "evidence": [
                {
                    "evidence_id": item.evidence_id,
                    "text": item.text,
                    "source_mode": item.source_mode,
                    "warning_codes": list(item.warning_codes),
                }
                for item in window.evidence
            ],
        }
        try:
            response: object = self._structured.invoke(
                [
                    SystemMessage(content=prompt),
                    HumanMessage(
                        content=json.dumps(
                            source_payload,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    ),
                ]
            )
        except (RateLimitError, APITimeoutError, APIConnectionError) as exc:
            raise KnowledgePointProviderTransientError(
                "Knowledge Point Provider is temporarily unavailable"
            ) from exc
        except Exception as exc:
            raise KnowledgePointProviderResponseError(
                "Knowledge Point Provider request failed"
            ) from exc
        if not isinstance(response, Mapping):
            raise KnowledgePointProviderResponseError(
                "Knowledge Point Provider returned an invalid response envelope"
            )
        parsed = response.get("parsed")
        parsing_error = response.get("parsing_error")
        if parsing_error is not None or not isinstance(parsed, _CandidateBatch):
            raise KnowledgePointProviderResponseError(
                "Knowledge Point Provider Structured Output validation failed: "
                f"{_structured_output_error_code(response)}"
            )
        raw = response.get("raw")
        usage = _usage_from_raw(raw)
        return ProviderExtraction(candidates=parsed.candidates, usage=usage)


def knowledge_point_provider_from_settings(
    configured: Settings = settings,
) -> OpenAICompatibleKnowledgePointProvider:
    if configured.COURSERAG_KP_PROVIDER == "disabled":
        raise KnowledgePointProviderUnavailable("Knowledge Point Provider is disabled")
    model = configured.COURSERAG_KP_MODEL or configured.COMPATIBLE_MODEL
    base_url = configured.COURSERAG_KP_BASE_URL or configured.COMPATIBLE_BASE_URL
    api_key = configured.COURSERAG_KP_API_KEY or configured.COMPATIBLE_API_KEY
    if not model or not base_url or api_key is None:
        raise KnowledgePointProviderUnavailable(
            "Knowledge Point Provider requires model, base URL and API key configuration"
        )
    return OpenAICompatibleKnowledgePointProvider(
        model=model,
        base_url=str(base_url),
        api_key=api_key,
        timeout_seconds=configured.COURSERAG_KP_TIMEOUT_SECONDS,
        structured_output_method=configured.COURSERAG_KP_STRUCTURED_OUTPUT_METHOD,
    )


def _usage_from_raw(raw: object) -> ProviderUsage:
    if not isinstance(raw, AIMessage) or not isinstance(raw.usage_metadata, dict):
        return ProviderUsage()
    metadata = raw.usage_metadata
    input_tokens = metadata.get("input_tokens")
    output_tokens = metadata.get("output_tokens")
    total_tokens = metadata.get("total_tokens")
    return ProviderUsage(
        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        total_tokens=total_tokens if isinstance(total_tokens, int) else None,
    )


def _structured_output_error_code(response: Mapping[object, object]) -> str:
    raw = response.get("raw")
    if not isinstance(raw, AIMessage) or not isinstance(raw.content, str):
        return "invalid_response_envelope"
    if not raw.content.strip():
        return "empty_json_content"
    try:
        payload = json.loads(raw.content)
    except json.JSONDecodeError:
        return "invalid_json_content"
    try:
        _CandidateBatch.model_validate(payload)
    except ValidationError as exc:
        summaries = []
        for error in exc.errors(include_input=False, include_url=False)[:5]:
            location = ".".join(str(item) for item in error["loc"])
            error_type = str(error["type"])
            if error_type == "value_error":
                context = error.get("ctx")
                reason = str(context.get("error")) if isinstance(context, dict) else ""
                error_type = _VALIDATION_REASON_CODES.get(reason, "value_error")
            summaries.append(f"{location}:{error_type}")
        return "schema_mismatch[" + ",".join(summaries) + "]"
    return "parser_contract_mismatch"

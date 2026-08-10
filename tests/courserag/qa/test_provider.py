import json

import httpx
import pytest
from pydantic import SecretStr

from courserag.contracts.qa import AnswerType
from courserag.infrastructure.qa_provider import (
    OpenAICompatibleCapability,
    OpenAICompatibleQAProvider,
)
from courserag.qa.models import ProviderOutputError
from courserag.query.answer_shape import AnswerShapeDecision, decide_answer_shape
from tests.courserag.qa.test_cited_qa import _context


def test_deepseek_capability_sends_explicit_thinking_toggle_without_leaking_key() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "answered",
                                    "answer_type": "explanatory",
                                    "answer": "answer",
                                    "list_items": [],
                                    "claims": [{"text": "claim", "evidence_ids": ["ev-a"]}],
                                }
                            )
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13},
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret-value"),
        model="configured-model",
        capability=OpenAICompatibleCapability(
            profile_name="deepseek_v4", supports_thinking_toggle=True
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate("question", _context())
    assert result.usage.total_tokens == 13
    assert captured["payload"]["thinking"] == {"type": "disabled"}  # type: ignore[index]
    assert "secret-value" not in json.dumps(captured["payload"])


def test_unknown_provider_does_not_receive_thinking_parameter() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "thinking" not in json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"status":"abstained_insufficient_evidence","answer_type":null,"answer":null,"list_items":[],"claims":[]}'
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(profile_name="unknown"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.generate("question", _context()).output.status.startswith("abstained")


def test_plain_baseline_requests_answer_without_claim_or_abstention_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer":"plain answer"}'}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(
            profile_name="deepseek_v4", supports_thinking_toggle=True
        ),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate_plain("question", _context())
    assert result.output.answer == "plain answer"
    assert result.usage.total_tokens == 10
    system_prompt = captured["payload"]["messages"][0]["content"]  # type: ignore[index]
    assert "Do not add citations, claims, refusal status" in system_prompt


def test_generation_reliability_list_uses_summary_short_aliases_and_shape_budget() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "answered",
                                    "answer_type": "list",
                                    "answer": "两项关键事实。",
                                    "claims": [],
                                    "list_items": [
                                        {"text": "事实一", "evidence_ids": ["E001"]},
                                        {"text": "事实二", "evidence_ids": ["E001"]},
                                    ],
                                },
                                ensure_ascii=False,
                            )
                        },
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 30, "total_tokens": 50},
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(profile_name="deepseek_v4"),
        generation_reliability_enabled=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    shape = decide_answer_shape("文中列出了哪些事实？")
    result = provider.generate("文中列出了哪些事实？", _context(), answer_shape=shape)

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["max_tokens"] == 3200
    user_prompt = payload["messages"][1]["content"]
    user_payload = json.loads(user_prompt)
    evidence_payload = user_payload["untrusted_evidence"][0]
    assert evidence_payload["evidence_aliases"] == ["E001"]
    assert "evidence_ids" not in evidence_payload
    assert result.output.answer == "两项关键事实。"
    assert result.output.list_items[0].evidence_ids == ("ev-a",)
    assert result.prompt_version == "p09_generation_reliability_list_v1"
    assert result.completion_metadata["finish_reason"] == "stop"


def test_generation_reliability_contract_is_disabled_by_default() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured["payload"] = payload
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "answered",
                                    "answer_type": "list",
                                    "answer": None,
                                    "claims": [],
                                    "list_items": [{"text": "事实一", "evidence_ids": ["ev-a"]}],
                                },
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(profile_name="deepseek_v4"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(
        "教材给出了哪些事实？",
        _context(),
        answer_shape=decide_answer_shape("教材给出了哪些事实？"),
    )
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["max_tokens"] == 1600
    assert result.prompt_version == "p09_answer_grounding_v3"
    assert result.output.answer is None


def test_p10_list_only_reliability_restores_q2_factoid_contract() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "answered",
                                    "answer_type": "factoid",
                                    "answer": "Concise answer.",
                                    "list_items": [],
                                    "claims": [
                                        {"text": "Concise answer.", "evidence_ids": ["ev-a"]}
                                    ],
                                }
                            )
                        }
                    }
                ]
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(profile_name="deepseek_v4"),
        generation_reliability_enabled=True,
        generation_reliability_factoid_enabled=False,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    shape = AnswerShapeDecision(
        forced_type=AnswerType.FACTOID,
        rule_id="answer_shape.explicit_task_factoid.v1",
        reason="P10 regression fixture",
    )
    result = provider.generate("Which task?", _context(), answer_shape=shape)

    payload = captured["payload"]
    assert isinstance(payload, dict)
    user_payload = json.loads(payload["messages"][1]["content"])
    evidence_payload = user_payload["untrusted_evidence"][0]
    assert evidence_payload["evidence_ids"] == ["ev-a"]
    assert "evidence_aliases" not in evidence_payload
    assert result.prompt_version == "p09_answer_grounding_v3"


def test_generation_reliability_supports_a_34_item_list_without_full_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 3200
        items = [
            {"text": f"职业 {index}：{index}%", "evidence_ids": ["E001"]} for index in range(1, 35)
        ]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "status": "answered",
                                    "answer_type": "list",
                                    "answer": "教材列出了34种职业的自动化淘汰概率。",
                                    "claims": [],
                                    "list_items": items,
                                },
                                ensure_ascii=False,
                            )
                        },
                    }
                ]
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(profile_name="deepseek_v4"),
        generation_reliability_enabled=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = provider.generate(
        "教材给出了哪些职业概率？",
        _context(),
        answer_shape=decide_answer_shape("教材给出了哪些职业概率？"),
    )
    assert len(result.output.list_items) == 34
    assert all(item.evidence_ids == ("ev-a",) for item in result.output.list_items)


def test_invalid_json_reports_finish_reason_without_raw_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"finish_reason": "length", "message": {"content": '{"status":'}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 3200},
            },
        )

    provider = OpenAICompatibleQAProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured-model",
        capability=OpenAICompatibleCapability(profile_name="deepseek_v4"),
        generation_reliability_enabled=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(ProviderOutputError) as caught:
        provider.generate(
            "列出了哪些事实？",
            _context(),
            answer_shape=decide_answer_shape("列出了哪些事实？"),
        )
    assert caught.value.code == "INVALID_JSON"
    assert caught.value.metadata["finish_reason"] == "length"
    assert caught.value.metadata["output_token_limit"] == 3200
    assert "content" not in caught.value.metadata

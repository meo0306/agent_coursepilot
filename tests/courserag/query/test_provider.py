import json

import httpx
from pydantic import SecretStr

from courserag.infrastructure.query_provider import OpenAICompatibleRewriteProvider


def test_rewrite_provider_preserves_capability_boundary() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["thinking"] == {"type": "disabled"}
        assert "secret" not in json.dumps(payload)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"rewrites":["rewrite"]}'}}],
                "usage": {"total_tokens": 12},
            },
        )

    provider = OpenAICompatibleRewriteProvider(
        base_url="https://example.test/v1",
        api_key=SecretStr("secret"),
        model="configured",
        supports_thinking_toggle=True,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert provider.rewrite("query", max_rewrites=3) == ("rewrite",)
    assert provider.total_tokens == 12

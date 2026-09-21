"""The Vertex AI provider, exercised against a mock transport (no network, no credentials)."""

import httpx
import pytest

from app.adapters import ai
from app.core.config import Settings


def settings(**overrides) -> Settings:
    values = {
        "ai_provider": "vertex",
        "ai_text_model": "gemini-2.5-flash",
        "gcp_project_id": "knowhub-test",
        "gcp_region": "us-central1",
        **overrides,
    }
    return Settings(_env_file=None, **values)


@pytest.fixture
def vertex(monkeypatch):
    """Capture the request and reply with whatever the test asks for."""
    seen: dict = {}

    def install(handler):
        def factory(base_url: str = "", timeout: float = 30.0) -> httpx.AsyncClient:
            def capture(request: httpx.Request) -> httpx.Response:
                seen["url"] = str(request.url)
                seen["headers"] = dict(request.headers)
                seen["json"] = __import__("json").loads(request.content)
                return handler(request)

            return httpx.AsyncClient(transport=httpx.MockTransport(capture), timeout=timeout)

        monkeypatch.setattr(ai, "_client", factory)

    monkeypatch.setattr(ai, "_access_token", lambda: _token())
    return install, seen


async def _token() -> str:
    return "test-token"


def reply(body: dict, status: int = 200):
    return lambda request: httpx.Response(status, json=body)


TEXT_REPLY = {"candidates": [{"content": {"parts": [{"text": "A clearer title"}]}, "finishReason": "STOP"}]}


async def test_calls_the_right_endpoint_with_the_prompt(vertex):
    install, seen = vertex
    install(reply(TEXT_REPLY))

    out = await ai.generate_text(settings(), system="You edit titles.", prompt="fix teh title")

    assert out == "A clearer title"
    assert seen["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/knowhub-test"
        "/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert seen["headers"]["authorization"] == "Bearer test-token"
    # user credentials need the call attributed to a project
    assert seen["headers"]["x-goog-user-project"] == "knowhub-test"
    assert seen["json"]["systemInstruction"]["parts"][0]["text"] == "You edit titles."
    assert seen["json"]["contents"][0]["parts"][0]["text"] == "fix teh title"
    # copy editing, not creative writing
    assert seen["json"]["generationConfig"]["temperature"] == 0.1


async def test_global_location_uses_the_global_host(vertex):
    install, seen = vertex
    install(reply(TEXT_REPLY))
    await ai.generate_text(settings(vertex_location="global"), system="s", prompt="p")
    assert seen["url"].startswith("https://aiplatform.googleapis.com/")


async def test_multi_part_answers_are_joined(vertex):
    install, _ = vertex
    install(reply({"candidates": [{"content": {"parts": [{"text": "one "}, {"text": "two"}]}}]}))
    assert await ai.generate_text(settings(), system="s", prompt="p") == "one two"


async def test_disabled_api_says_how_to_enable_it(vertex):
    install, _ = vertex
    install(reply({"error": {"status": "SERVICE_DISABLED"}}, status=403))
    with pytest.raises(ai.AIUnavailable, match="gcloud services enable aiplatform.googleapis.com"):
        await ai.generate_text(settings(), system="s", prompt="p")


async def test_disabled_api_is_recognised_in_a_long_error_body(vertex):
    """Vertex puts the reason in error.details[], after a long human message — so the
    check must look at the whole body, not the first few hundred characters."""
    install, _ = vertex
    install(
        reply(
            {
                "error": {
                    "code": 403,
                    "message": "Agent Platform API has not been used in project x before "
                    "or it is disabled. " + "Enable it by visiting the console. " * 6,
                    "status": "PERMISSION_DENIED",
                    "details": [{"reason": "SERVICE_DISABLED", "domain": "googleapis.com"}],
                }
            },
            status=403,
        )
    )
    with pytest.raises(ai.AIUnavailable, match="gcloud services enable"):
        await ai.generate_text(settings(), system="s", prompt="p")


async def test_permission_denied_points_at_the_role(vertex):
    install, _ = vertex
    install(reply({"error": {"status": "PERMISSION_DENIED"}}, status=403))
    with pytest.raises(ai.AIUnavailable, match="roles/aiplatform.user"):
        await ai.generate_text(settings(), system="s", prompt="p")


async def test_unknown_model_points_at_the_setting(vertex):
    install, _ = vertex
    install(reply({"error": {"status": "NOT_FOUND"}}, status=404))
    with pytest.raises(ai.AIUnavailable, match="AI_TEXT_MODEL"):
        await ai.generate_text(settings(), system="s", prompt="p")


async def test_a_blocked_prompt_is_reported_not_returned_empty(vertex):
    install, _ = vertex
    install(reply({"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ai.AIUnavailable, match="SAFETY"):
        await ai.generate_text(settings(), system="s", prompt="p")


async def test_truncated_answers_are_reported(vertex):
    install, _ = vertex
    install(reply({"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}]}))
    with pytest.raises(ai.AIUnavailable, match="output limit"):
        await ai.generate_text(settings(), system="s", prompt="p")


async def test_health_check_uses_count_tokens_and_reports_detail(vertex):
    install, seen = vertex
    install(reply({"totalTokens": 3}))
    result = await ai.check_ai(settings())
    assert result == {
        "ok": True,
        "provider": "vertex",
        "model": "gemini-2.5-flash",
        "location": "us-central1",
        "project": "knowhub-test",
    }
    assert seen["url"].endswith(":countTokens")  # free: never bills a generation


async def test_health_check_explains_a_failure_instead_of_raising(vertex):
    install, _ = vertex
    install(reply({"error": {"status": "SERVICE_DISABLED"}}, status=403))
    result = await ai.check_ai(settings())
    assert result["ok"] is False
    assert "aiplatform.googleapis.com" in result["error"]


async def test_missing_project_is_caught_before_any_call():
    with pytest.raises(ai.AIUnavailable, match="GCP_PROJECT_ID"):
        await ai.generate_text(settings(gcp_project_id=""), system="s", prompt="p")

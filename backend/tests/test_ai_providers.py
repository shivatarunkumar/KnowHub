"""Every AI provider, against a mock transport: no network, no keys, no credentials.

These pin down what each provider is actually sent (URL, auth header, model, prompt) and
that failures come back as something a person can act on.
"""

import json

import httpx
import pytest

from app.adapters import ai
from app.core.config import Settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """The developer's own .env is exported into the test process, and environment
    variables win over defaults — so clear the AI ones and test the defaults themselves."""
    for name in (
        "PROVIDER",
        "AI_PROVIDER",
        "MODEL",
        "AI_TEXT_MODEL",
        "LLM_API_BASE",
        "OLLAMA_BASE_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "VERTEX_LOCATION",
        "GCP_PROJECT_ID",
        "GCP_REGION",
    ):
        monkeypatch.delenv(name, raising=False)


def settings(**overrides) -> Settings:
    values = {"gcp_project_id": "knowhub-test", "gcp_region": "us-central1", **overrides}
    return Settings(_env_file=None, **values)


@pytest.fixture
def transport(monkeypatch):
    """Capture the outgoing request and reply with whatever the test wants."""
    seen: dict = {}

    def install(handler):
        def factory(base_url: str = "", timeout: float = 30.0) -> httpx.AsyncClient:
            def capture(request: httpx.Request) -> httpx.Response:
                seen["method"] = request.method
                seen["url"] = str(request.url)
                seen["headers"] = dict(request.headers)
                seen["json"] = json.loads(request.content) if request.content else None
                return handler(request)

            return httpx.AsyncClient(transport=httpx.MockTransport(capture), timeout=timeout)

        monkeypatch.setattr(ai, "_client", factory)

    async def token() -> str:
        return "test-token"

    monkeypatch.setattr(ai, "_access_token", token)
    return install, seen


def reply(body: dict, status: int = 200):
    return lambda request: httpx.Response(status, json=body)


OPENAI_REPLY = {"choices": [{"message": {"content": "A clearer title"}, "finish_reason": "stop"}]}
ANTHROPIC_REPLY = {"content": [{"type": "text", "text": "A clearer title"}], "stop_reason": "end_turn"}
GEMINI_REPLY = {"candidates": [{"content": {"parts": [{"text": "A clearer title"}]}, "finishReason": "STOP"}]}


# ------------------------------------------------------------------ defaults
def test_each_provider_has_a_default_model_and_endpoint():
    assert settings(provider="openai").ai_model == "gpt-4.1-mini"
    assert settings(provider="anthropic").ai_model == "claude-sonnet-5"
    assert settings(provider="gemini").ai_model == "gemini-2.5-flash"
    assert settings(provider="ollama").ai_model == "llama3.2"
    assert settings(provider="openai").ai_base_url == "https://api.openai.com"


def test_model_and_base_from_env_win():
    configured = settings(provider="openai", model="gpt-4o", llm_api_base="http://localhost:11434/")
    assert configured.ai_model == "gpt-4o"
    assert configured.ai_base_url == "http://localhost:11434"  # trailing slash trimmed


def test_the_old_env_names_still_work(monkeypatch):
    """.env files written before this shape used AI_PROVIDER / AI_TEXT_MODEL / OLLAMA_BASE_URL."""
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("AI_TEXT_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    configured = Settings()
    assert (configured.provider, configured.ai_model) == ("openai", "gpt-4o-mini")
    assert configured.ai_base_url == "http://localhost:11434"


def test_a_cloud_provider_with_a_local_model_is_refused():
    with pytest.raises(ValueError, match="which is a local model"):
        settings(provider="openai", model="llama3.2")
    # unless a gateway is named, where the model belongs to that gateway
    assert settings(provider="openai", model="llama3.2", llm_api_base="http://localhost:11434").ai_model


# ------------------------------------------------------------------ openai
async def test_openai_request_shape(transport):
    install, seen = transport
    install(reply(OPENAI_REPLY))

    out = await ai.generate_text(
        settings(provider="openai", openai_api_key="sk-test"),
        system="You edit titles.",
        prompt="fix teh title",
    )

    assert out == "A clearer title"
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["authorization"] == "Bearer sk-test"
    assert seen["json"]["model"] == "gpt-4.1-mini"
    assert seen["json"]["messages"][0] == {"role": "system", "content": "You edit titles."}
    assert seen["json"]["messages"][1] == {"role": "user", "content": "fix teh title"}
    assert seen["json"]["temperature"] == 0.1  # copy editing, not creative writing


async def test_openai_against_a_local_gateway_needs_no_key(transport):
    install, seen = transport
    install(reply(OPENAI_REPLY))
    await ai.generate_text(
        settings(provider="openai", llm_api_base="http://localhost:11434", model="llama3.2"),
        system="s",
        prompt="p",
    )
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert "authorization" not in seen["headers"]


async def test_a_base_url_that_already_ends_in_v1_is_not_doubled(transport):
    install, seen = transport
    install(reply(OPENAI_REPLY))
    await ai.generate_text(
        settings(provider="openai", llm_api_base="https://proxy.corp/v1", openai_api_key="k"),
        system="s",
        prompt="p",
    )
    assert seen["url"] == "https://proxy.corp/v1/chat/completions"


async def test_missing_openai_key_names_the_setting(transport):
    install, _ = transport
    install(reply({"error": {"message": "no key"}}, status=401))
    with pytest.raises(ai.AIUnavailable, match="set OPENAI_API_KEY in .env"):
        await ai.generate_text(settings(provider="openai"), system="s", prompt="p")


async def test_a_rejected_openai_key_says_so(transport):
    install, _ = transport
    install(reply({"error": {"message": "bad key"}}, status=401))
    with pytest.raises(ai.AIUnavailable, match="rejected the API key"):
        await ai.generate_text(settings(provider="openai", openai_api_key="sk-wrong"), system="s", prompt="p")


async def test_openai_truncation_is_reported(transport):
    install, _ = transport
    install(reply({"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}))
    with pytest.raises(ai.AIUnavailable, match="output limit"):
        await ai.generate_text(settings(provider="openai", openai_api_key="k"), system="s", prompt="p")


# ------------------------------------------------------------------ anthropic
async def test_anthropic_request_shape(transport):
    install, seen = transport
    install(reply(ANTHROPIC_REPLY))

    out = await ai.generate_text(
        settings(provider="anthropic", anthropic_api_key="sk-ant"), system="You edit titles.", prompt="fix it"
    )

    assert out == "A clearer title"
    assert seen["url"] == "https://api.anthropic.com/v1/messages"
    assert seen["headers"]["x-api-key"] == "sk-ant"
    assert seen["headers"]["anthropic-version"] == ai.ANTHROPIC_VERSION
    assert seen["json"]["model"] == "claude-sonnet-5"
    assert seen["json"]["system"] == "You edit titles."  # a field, not a message
    assert seen["json"]["max_tokens"] == ai.MAX_OUTPUT_TOKENS


async def test_anthropic_joins_text_blocks_and_ignores_others(transport):
    install, _ = transport
    install(
        reply(
            {
                "content": [
                    {"type": "thinking", "thinking": "hmm"},
                    {"type": "text", "text": "one "},
                    {"type": "text", "text": "two"},
                ]
            }
        )
    )
    out = await ai.generate_text(
        settings(provider="anthropic", anthropic_api_key="k"), system="s", prompt="p"
    )
    assert out == "one two"


# ------------------------------------------------------------------ gemini
async def test_gemini_request_shape(transport):
    install, seen = transport
    install(reply(GEMINI_REPLY))

    out = await ai.generate_text(
        settings(provider="gemini", gemini_api_key="AIza-test"), system="You edit titles.", prompt="fix it"
    )

    assert out == "A clearer title"
    assert seen["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    )
    # the key travels as a header, so it never lands in a URL log
    assert seen["headers"]["x-goog-api-key"] == "AIza-test"
    assert "AIza-test" not in seen["url"]
    assert seen["json"]["systemInstruction"]["parts"][0]["text"] == "You edit titles."


async def test_a_blocked_prompt_is_reported_not_returned_empty(transport):
    install, _ = transport
    install(reply({"promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(ai.AIUnavailable, match="SAFETY"):
        await ai.generate_text(settings(provider="gemini", gemini_api_key="k"), system="s", prompt="p")


# ------------------------------------------------------------------ vertex
async def test_vertex_uses_adc_and_the_regional_host(transport):
    install, seen = transport
    install(reply(GEMINI_REPLY))

    out = await ai.generate_text(settings(provider="vertex"), system="s", prompt="p")

    assert out == "A clearer title"
    assert seen["url"] == (
        "https://us-central1-aiplatform.googleapis.com/v1/projects/knowhub-test"
        "/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent"
    )
    assert seen["headers"]["authorization"] == "Bearer test-token"
    assert seen["headers"]["x-goog-user-project"] == "knowhub-test"


async def test_vertex_global_location_uses_the_global_host(transport):
    install, seen = transport
    install(reply(GEMINI_REPLY))
    await ai.generate_text(settings(provider="vertex", vertex_location="global"), system="s", prompt="p")
    assert seen["url"].startswith("https://aiplatform.googleapis.com/")


async def test_disabled_vertex_api_is_recognised_in_a_long_error_body(transport):
    """The reason sits in error.details[], after a long human message — so the check must
    look at the whole body, not the first few hundred characters."""
    install, _ = transport
    install(
        reply(
            {
                "error": {
                    "code": 403,
                    "message": "Agent Platform API has not been used in project x before or it is "
                    "disabled. " + "Enable it by visiting the console. " * 6,
                    "status": "PERMISSION_DENIED",
                    "details": [{"reason": "SERVICE_DISABLED"}],
                }
            },
            status=403,
        )
    )
    with pytest.raises(ai.AIUnavailable, match="gcloud services enable"):
        await ai.generate_text(settings(provider="vertex"), system="s", prompt="p")


async def test_vertex_without_a_project_is_caught_before_any_call():
    with pytest.raises(ai.AIUnavailable, match="GCP_PROJECT_ID"):
        await ai.generate_text(settings(provider="vertex", gcp_project_id=""), system="s", prompt="p")


# ------------------------------------------------------------------ ollama
async def test_ollama_request_shape(transport):
    install, seen = transport
    install(reply({"response": "A clearer title"}))
    out = await ai.generate_text(settings(provider="ollama"), system="s", prompt="p")
    assert out == "A clearer title"
    assert seen["url"] == "http://localhost:11434/api/generate"
    assert seen["json"]["model"] == "llama3.2"
    assert seen["json"]["stream"] is False


# ------------------------------------------------------------------ health
async def test_health_check_per_provider(transport):
    install, seen = transport

    install(reply({"data": []}))
    assert (await ai.check_ai(settings(provider="openai", openai_api_key="k")))["ok"] is True
    assert seen["url"].endswith("/v1/models") and seen["method"] == "GET"

    install(reply({"totalTokens": 3}))
    assert (await ai.check_ai(settings(provider="vertex")))["ok"] is True
    assert seen["url"].endswith(":countTokens")  # free: never bills a generation

    install(reply({"models": [{"name": "llama3.2:latest"}, {"name": "nomic-embed-text:latest"}]}))
    assert (await ai.check_ai(settings(provider="ollama")))["ok"] is True


async def test_health_check_explains_a_failure_instead_of_raising(transport):
    install, _ = transport
    install(reply({"error": {"message": "nope"}}, status=401))
    result = await ai.check_ai(settings(provider="openai"))
    assert result["ok"] is False
    assert "OPENAI_API_KEY" in result["error"]


async def test_switching_off_needs_no_provider():
    assert (await ai.check_ai(settings(provider="none")))["ok"] is True
    with pytest.raises(ai.AIUnavailable, match="PROVIDER=none"):
        await ai.generate_text(settings(provider="none"), system="s", prompt="p")

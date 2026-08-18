"""
Real Ollama + Qwen2.5-Coder Integration and Runtime Unit Tests.

Validates Ollama server connectivity, installed model detection,
active model switching between Quality (7B Q4) and Fast (3B Q4) models,
no-fake-fallback error propagation, SSE token streaming, and health checks.
"""

from __future__ import annotations

import pytest

from services.llm.app.adapters.ollama_adapter import OllamaAdapter
from services.llm.app.prompts.templates import PromptTemplateRegistry
from services.llm.app.services.llm_service import LLMService
from shared.config.settings import get_settings
from shared.exceptions.handlers import ServiceUnavailableException, ValidationException


@pytest.fixture
def settings():
    return get_settings()


@pytest.fixture
def adapter():
    return OllamaAdapter()


@pytest.fixture
def llm_service(adapter):
    return LLMService(adapter=adapter)


@pytest.mark.asyncio
async def test_ollama_server_reachable(adapter: OllamaAdapter):
    """Verify local Ollama server endpoint at http://localhost:11434 is reachable."""
    health = await adapter.check_health()
    assert health["ollama_connected"] is True
    assert health["status"] == "online"
    assert isinstance(health["loaded_models"], list)


@pytest.mark.asyncio
async def test_models_configuration(settings):
    """Verify default Quality (7B Q4) and Fast (3B Q4) model configurations."""
    assert "7b" in settings.default_quality_model.lower() or "qwen2.5-coder" in settings.default_quality_model.lower()
    assert "3b" in settings.default_fast_model.lower() or "qwen2.5-coder" in settings.default_fast_model.lower()


def test_model_switching(llm_service: LLMService):
    """Verify select_model updates active model correctly and validates empty IDs."""
    # Switch to quality model
    res_quality = llm_service.select_model("qwen2.5-coder:7b-instruct-q4_0")
    assert res_quality.active_model == "qwen2.5-coder:7b-instruct-q4_0"
    assert llm_service.active_model == "qwen2.5-coder:7b-instruct-q4_0"

    # Switch to fast model
    res_fast = llm_service.select_model("qwen2.5-coder:3b-instruct-q4_0")
    assert res_fast.active_model == "qwen2.5-coder:3b-instruct-q4_0"
    assert llm_service.active_model == "qwen2.5-coder:3b-instruct-q4_0"

    # Verify empty model error
    with pytest.raises(ValidationException):
        llm_service.select_model("   ")


def test_prompt_template_compilation():
    """Verify prompt compilation across all 7 prompt modes."""
    modes = ["ASK", "PLAN", "CODE", "DEBUG", "TEST", "REVIEW", "EXPLAIN"]
    for mode in modes:
        sys_p, user_p = PromptTemplateRegistry.compile_prompt(
            mode=mode,
            instruction="Refactor authentication middleware",
            context="Current code: def auth(): pass",
        )
        assert sys_p is not None and len(sys_p) > 0
        assert "Refactor authentication middleware" in user_p


@pytest.mark.asyncio
async def test_no_fake_fallback_on_unreachable_ollama():
    """Verify that when Ollama server is unreachable, generation raises ServiceUnavailableException with NO hardcoded fallback."""
    bad_adapter = OllamaAdapter(ollama_url="http://localhost:59999")
    bad_service = LLMService(adapter=bad_adapter)

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await bad_service.generate(prompt="Write a function", mode="CODE")

    assert "unreachable" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_llm_health_status(llm_service: LLMService):
    """Verify LLM service health status reporting."""
    health_resp = await llm_service.get_health()
    assert health_resp.ollama_connected is True
    assert health_resp.active_model == llm_service.active_model
    assert isinstance(health_resp.loaded_models, list)


@pytest.mark.asyncio
async def test_real_ollama_generation_if_installed(adapter: OllamaAdapter, llm_service: LLMService):
    """If a Qwen model is installed on Ollama, execute real generation and streaming test."""
    models_data = await adapter.list_models()
    installed_names = [m.get("name", "") for m in models_data]

    if not installed_names:
        pytest.skip("No models installed in Ollama yet; skipping real generation test until model download completes")

    test_model = installed_names[0]
    llm_service.select_model(test_model)

    # Test Real Generation
    gen_resp = await llm_service.generate(
        prompt="Write a Python function named add_numbers(a, b) that returns their sum.",
        mode="CODE",
    )
    assert gen_resp.model == test_model
    assert gen_resp.response is not None and len(gen_resp.response.strip()) > 0
    # Verify no fallback string
    assert "Fallback generated code snippet" not in gen_resp.response

    # Test Real SSE Streaming
    tokens = []
    async for token in llm_service.generate_stream(
        prompt="Say hello in one word",
        mode="ASK",
    ):
        tokens.append(token)

    assert len(tokens) > 0
    full_stream_text = "".join(tokens)
    assert len(full_stream_text.strip()) > 0

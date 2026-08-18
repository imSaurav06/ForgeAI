"""
LLM Service managing local model execution, active model switching,
prompt compilation, token streaming, and structured response parsing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

from services.llm.app.adapters.ollama_adapter import OllamaAdapter
from services.llm.app.prompts.templates import PromptTemplateRegistry
from services.llm.app.schemas.execution_plan_schema import (
    EXECUTION_PLAN_JSON_SCHEMA,
)
from services.llm.app.schemas.llm_schemas import (
    ChatMessage,
    ChatResponse,
    GenerateResponse,
    LLMModelInfo,
    ModelHealthResponse,
    ModelSelectResponse,
)
from shared.config.settings import get_settings
from shared.exceptions.handlers import ValidationException
from shared.logging.logger import logger


class LLMService:
    """LLM Service managing model loading, switching, prompt compilation, and generation."""

    def __init__(self, adapter: OllamaAdapter | None = None) -> None:
        self.settings = get_settings()
        self.adapter = adapter or OllamaAdapter()
        self.active_model: str = self.settings.default_fast_model

    def select_model(self, model_id: str) -> ModelSelectResponse:
        """Switch active LLM model used for subsequent generation tasks."""
        clean_model = model_id.strip()

        if not clean_model:
            raise ValidationException(message="Model ID cannot be empty")

        self.active_model = clean_model

        logger.info(
            f"Active LLM model switched to '{self.active_model}'"
        )

        return ModelSelectResponse(
            active_model=self.active_model,
            status="ready",
        )

    async def list_models(self) -> list[LLMModelInfo]:
        """Fetch installed models from Ollama."""
        models_data = await self.adapter.list_models()
        model_items: list[LLMModelInfo] = []

        for model in models_data:
            name = model.get("name", "unknown")
            size = model.get("size")

            model_items.append(
                LLMModelInfo(
                    id=name,
                    name=name.replace("-", " ").title(),
                    size_bytes=size,
                    is_active=(name == self.active_model),
                )
            )

        return model_items

    async def get_health(self) -> ModelHealthResponse:
        """Check Ollama connectivity and model availability status."""
        health = await self.adapter.check_health()

        loaded = health.get("loaded_models", [])
        connected = health.get("ollama_connected", False)

        if not connected:
            status_str = "unhealthy"
        elif (
            self.active_model in loaded
            or any(self.active_model in model for model in loaded)
        ):
            status_str = "healthy"
        else:
            status_str = "degraded"

        return ModelHealthResponse(
            status=status_str,
            ollama_connected=connected,
            active_model=self.active_model,
            loaded_models=loaded,
        )

    @staticmethod
    def _parse_json_response(raw_response: str) -> dict[str, Any] | None:
        """Parse a JSON object from a raw LLM response."""
        if not isinstance(raw_response, str):
            return None

        content = raw_response.strip()

        if not content:
            return None

        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

        if "```json" in content:
            try:
                json_str = (
                    content.split("```json", 1)[1]
                    .split("```", 1)[0]
                    .strip()
                )

                parsed = json.loads(json_str)
                return parsed if isinstance(parsed, dict) else None
            except (IndexError, json.JSONDecodeError):
                return None

        return None

    @staticmethod
    def _is_valid_execution_plan(data: dict[str, Any] | None) -> bool:
        """Validate the minimum execution-plan contract returned by PLAN mode."""
        if not isinstance(data, dict):
            return False

        required_fields = {
            "plan_id",
            "summary",
            "steps",
            "affected_files",
            "test_plan",
        }

        if not required_fields.issubset(data.keys()):
            return False

        if "plan_steps" in data:
            return False

        steps = data.get("steps")

        if not isinstance(steps, list) or not steps:
            return False

        if not isinstance(data.get("affected_files"), list):
            return False

        if not isinstance(data.get("test_plan"), list):
            return False

        for step in steps:
            if not isinstance(step, dict):
                return False

            required_step_fields = {
                "id",
                "task",
                "tool",
                "depends_on",
                "files",
            }

            if not required_step_fields.issubset(step.keys()):
                return False

            if not isinstance(step["depends_on"], list):
                return False

            if not isinstance(step["files"], list):
                return False

        return True

    async def generate(
        self,
        prompt: str,
        mode: str = "CODE",
        context: str | None = None,
        model_override: str | None = None,
        temperature: float = 0.2,
    ) -> GenerateResponse:
        """Compile prompt and execute real Ollama LLM text generation."""
        target_model = model_override or self.active_model
        mode_upper = mode.upper()

        logger.info(
            f"LLM Generation dispatch: "
            f"requested_override='{model_override}', "
            f"active_model='{self.active_model}', "
            f"target_model='{target_model}', "
            f"mode='{mode_upper}'"
        )

        system_prompt, compiled_prompt = (
            PromptTemplateRegistry.compile_prompt(
                mode=mode_upper,
                instruction=prompt,
                context=context or "",
            )
        )

        structured_schema = (
            EXECUTION_PLAN_JSON_SCHEMA
            if mode_upper == "PLAN"
            else None
        )

        generation_temperature = (
            min(temperature, 0.1)
            if mode_upper == "PLAN"
            else temperature
        )

        options: dict[str, Any] = {
            "temperature": generation_temperature,
        }

        if mode_upper == "PLAN":
            options["top_p"] = 0.9

            logger.info(
                "LLM structured output enabled for PLAN mode "
                f"with temperature={generation_temperature}"
            )

        response = await self.adapter.generate(
            model=target_model,
            prompt=compiled_prompt,
            system_prompt=system_prompt,
            options=options,
            structured_schema=structured_schema,
        )

        raw_response = response.get("response", "")
        parsed_json = self._parse_json_response(raw_response)

        if mode_upper == "PLAN":
            if self._is_valid_execution_plan(parsed_json):
                logger.info(
                    "PLAN generation returned a valid execution-plan contract"
                )
            else:
                if isinstance(parsed_json, dict) and "plan_steps" in parsed_json:
                    logger.warning(
                        "PLAN generation returned legacy 'plan_steps' "
                        "instead of executable 'steps'"
                    )
                else:
                    logger.warning(
                        "PLAN generation returned JSON that does not "
                        "satisfy the execution-plan contract"
                    )

                parsed_json = None

        return GenerateResponse(
            model=target_model,
            response=raw_response,
            structured_data=parsed_json,
        )

    async def generate_stream(
        self,
        prompt: str,
        mode: str = "CODE",
        context: str | None = None,
        model_override: str | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream token chunks for generation prompt directly from Ollama."""
        target_model = model_override or self.active_model

        logger.info(
            f"LLM Stream dispatch: "
            f"requested_override='{model_override}', "
            f"active_model='{self.active_model}', "
            f"target_model='{target_model}'"
        )

        system_prompt, compiled_prompt = (
            PromptTemplateRegistry.compile_prompt(
                mode=mode,
                instruction=prompt,
                context=context or "",
            )
        )

        async for token in self.adapter.generate_stream(
            model=target_model,
            prompt=compiled_prompt,
            system_prompt=system_prompt,
        ):
            yield token

    async def chat(
        self,
        messages: list[ChatMessage],
        model_override: str | None = None,
    ) -> ChatResponse:
        """Handle multi-turn chat generation via Ollama."""
        target_model = model_override or self.active_model
        last_message = messages[-1].content if messages else ""

        generation_response = await self.generate(
            prompt=last_message,
            mode="ASK",
            model_override=target_model,
        )

        return ChatResponse(
            model=target_model,
            message=ChatMessage(
                role="assistant",
                content=generation_response.response,
            ),
        )
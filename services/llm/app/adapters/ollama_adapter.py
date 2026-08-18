"""
Real Ollama Async Adapter.

Communicates with local Ollama server at http://localhost:11434 (or configured URL)
for LLM generation, chat completions, token streaming, and model lifecycle management.
No hardcoded or fake fallbacks allowed.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from shared.config.settings import get_settings
from shared.exceptions.handlers import ServiceUnavailableException
from shared.logging.logger import logger


class OllamaAdapter:
    """Async adapter for communicating with real local Ollama runtime API."""

    def __init__(
        self,
        ollama_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        settings = get_settings()
        self.ollama_url = (ollama_url or settings.ollama_url).rstrip("/")
        self.timeout = timeout

    async def check_health(self) -> dict[str, Any]:
        """Check Ollama connectivity and return installed model tags."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.ollama_url}/api/tags")

                if resp.status_code == 200:
                    data = resp.json()
                    models = [
                        m.get("name")
                        for m in data.get("models", [])
                        if m.get("name")
                    ]

                    return {
                        "status": "online",
                        "ollama_connected": True,
                        "loaded_models": models,
                    }

        except Exception as err:
            logger.debug(
                f"Ollama connection check failed at "
                f"{self.ollama_url}: {err}"
            )

        return {
            "status": "offline",
            "ollama_connected": False,
            "loaded_models": [],
        }

    async def list_models(self) -> list[dict[str, Any]]:
        """Fetch list of installed model objects from Ollama."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{self.ollama_url}/api/tags"
                )

                if resp.status_code == 200:
                    return resp.json().get("models", [])

                raise ServiceUnavailableException(
                    message=(
                        f"Ollama server returned HTTP "
                        f"{resp.status_code}"
                    ),
                    details={"response": resp.text},
                )

        except httpx.RequestError as err:
            logger.error(
                f"Cannot connect to Ollama at "
                f"{self.ollama_url}: {err}"
            )

            raise ServiceUnavailableException(
                message=(
                    f"Local Ollama server is unreachable at "
                    f"{self.ollama_url}"
                ),
                details={"error": str(err)},
            ) from err

    async def generate(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        options: dict[str, Any] | None = None,
        structured_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute real LLM text completion via Ollama.

        When structured_output is enabled, Ollama is explicitly
        instructed to return a JSON object.
        """
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": options or {
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        if structured_schema is not None:
            payload["format"] = structured_schema

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                )

                if resp.status_code == 200:
                    return resp.json()

                error_msg = (
                    f"Ollama generation failed with status "
                    f"{resp.status_code}"
                )

                logger.error(
                    f"{error_msg}: {resp.text}"
                )

                raise ServiceUnavailableException(
                    message=error_msg,
                    details={
                        "status_code": resp.status_code,
                        "body": resp.text,
                    },
                )

        except httpx.RequestError as err:
            logger.error(
                f"Ollama connection error during generate: {err}"
            )

            raise ServiceUnavailableException(
                message=(
                    f"Local Ollama server is unreachable at "
                    f"{self.ollama_url}"
                ),
                details={"error": str(err)},
            ) from err

    async def generate_stream(
        self,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream real-time LLM token chunks directly from Ollama."""
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": True,
            "options": options or {
                "temperature": 0.2,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:
                async with client.stream(
                    "POST",
                    f"{self.ollama_url}/api/generate",
                    json=payload,
                ) as resp:

                    if resp.status_code != 200:
                        raise ServiceUnavailableException(
                            message=(
                                "Ollama streaming failed with "
                                f"status {resp.status_code}"
                            ),
                        )

                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue

                        try:
                            data = json.loads(line)
                            token = data.get("response", "")

                            if token:
                                yield token

                        except Exception as parse_err:
                            logger.debug(
                                "Error parsing Ollama stream chunk: "
                                f"{parse_err}"
                            )

        except httpx.RequestError as err:
            logger.error(
                "Ollama streaming connection error: "
                f"{err}"
            )

            raise ServiceUnavailableException(
                message=(
                    f"Local Ollama server is unreachable at "
                    f"{self.ollama_url}"
                ),
                details={"error": str(err)},
            ) from err
"""
services/llm_client.py — Ollama LLM Client
============================================
Communicates with the locally-running Ollama server.
Streams tokens back to the caller via an async generator.

No API key needed. No subscription. Runs on your own hardware.
"""

import json
from typing import AsyncGenerator

import httpx
import structlog

from config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class OllamaClient:
    """
    Async streaming client for Ollama.
    Converts Ollama's NDJSON stream into individual tokens.
    """

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout

    async def stream_chat(
        self,
        query: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response from Ollama token by token.
        
        Args:
            query: The user's question
            system_prompt: Context + instructions for the model
            temperature: Creativity (0 = focused, 1 = creative)
            max_tokens: Maximum tokens to generate
        
        Yields:
            Individual text tokens as they're generated
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()

                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("done"):
                            break
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue

    async def generate(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Non-streaming generation — for internal use (e.g., query rewriting).
        Returns the complete response as a string.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            return response.json().get("response", "")

    async def is_available(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                if response.status_code != 200:
                    return False
                models = [m["name"] for m in response.json().get("models", [])]
                return any(self.model.split(":")[0] in m for m in models)
        except Exception:
            return False

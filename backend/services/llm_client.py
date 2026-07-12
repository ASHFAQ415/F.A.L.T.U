"""
services/llm_client.py — Groq LLM Client
==========================================
Communicates with the Groq API for ultra-fast LLM inference.
Streams tokens back to the caller via an async generator.

Groq API is FREE:
  - 14,400 requests/day on free tier
  - Model: llama-3.1-8b-instant (fastest)
  - No credit card required to sign up

Get your free API key at: https://console.groq.com
"""

from typing import AsyncGenerator

import structlog
from groq import AsyncGroq

from config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class GroqClient:
    """
    Async streaming client for Groq API.
    Drop-in replacement for OllamaClient — same interface, much faster responses.

    Free tier limits (as of 2024):
      - 14,400 requests/day
      - 6,000 tokens/minute
      - 30 requests/minute
    """

    def __init__(self):
        self.client = AsyncGroq(api_key=settings.groq_api_key)
        self.model = settings.groq_model

    async def stream_chat(
        self,
        query: str,
        system_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response from Groq token by token.
        Single-turn: uses system prompt + user query only.
        """
        logger.info(
            "🚀 Streaming from Groq",
            model=self.model,
            tokens=max_tokens,
        )

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def stream_chat_with_history(
        self,
        query: str,
        system_prompt: str,
        history: list,
        temperature: float = 0.7,
        max_tokens: int = 1024,
    ) -> AsyncGenerator[str, None]:
        """
        Stream a chat response with full conversation history for multi-turn memory.

        Args:
            query: The current user question
            system_prompt: Context + instructions for the model
            history: List of {"role": "user"|"assistant", "content": str} dicts
            temperature: Creativity (0 = focused, 1 = creative)
            max_tokens: Maximum tokens to generate

        Yields:
            Individual text tokens as they're generated
        """
        logger.info(
            "🚀 Streaming from Groq (with history)",
            model=self.model,
            history_turns=len(history),
            tokens=max_tokens,
        )

        # Build message list: system + history + current query
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": query})

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    async def generate(self, prompt: str, temperature: float = 0.3) -> str:
        """
        Non-streaming generation — for internal use (e.g., query rewriting).
        Returns the complete response as a string.
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=256,
            stream=False,
        )
        return response.choices[0].message.content or ""

    async def generate_hyde(self, query: str) -> str:
        """
        HyDE (Hypothetical Document Embedding): generate a short hypothetical
        answer/passage that WOULD answer the query. Embed this instead of the
        raw query to dramatically improve retrieval quality for short queries.

        Returns:
            A 2-3 sentence hypothetical answer string for embedding.
        """
        prompt = (
            f"Write a short 2-3 sentence passage that would directly answer this question. "
            f"Be factual and specific. Do NOT say you don't know.\n\n"
            f"Question: {query}\n\nPassage:"
        )
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=150,
                stream=False,
            )
            return response.choices[0].message.content or query
        except Exception as e:
            logger.warning("HyDE generation failed, using original query", error=str(e))
            return query  # Fallback to original query

    async def is_available(self) -> bool:
        """Check if Groq API is reachable and the API key is valid."""
        try:
            await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                stream=False,
            )
            return True
        except Exception as e:
            logger.warning("Groq API unavailable", error=str(e))
            return False


# Backward-compatible alias so existing imports don't break
OllamaClient = GroqClient

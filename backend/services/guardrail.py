"""
services/guardrail.py — Input/Output Safety Guardrails
========================================================
Protects the chatbot from:
  1. Prompt injection attacks (attempts to override system instructions)
  2. Jailbreaking attempts
  3. Excessively long inputs (potential DoS or injection via paste)
  4. Unsafe outputs (toxic content, PII exposure)

All implemented locally — no external moderation API needed.
"""

import re
from typing import Tuple

import structlog

from config import get_settings

settings = get_settings()
logger = structlog.get_logger()


class Guardrail:
    """
    Input and output safety guard for the RAG chatbot.
    
    Replaces: AWS Bedrock Guardrails ($$$) with regex + heuristics (FREE)
    """

    # ── Prompt Injection Patterns ────────────────────────
    INJECTION_PATTERNS = [
        r"(?i)(ignore|forget|disregard|override)[\s\S]{0,30}(instructions|prompt|rules|system)",
        r"(?i)(show|reveal|print|output|display)[\s\S]{0,20}(system prompt|instructions|context)",
        r"(?i)(you are now|pretend to be|roleplay as|imagine you are)",
        r"(?i)(act as).{0,30}(hacker|jailbreak|DAN|unrestricted|no limits|evil|villain|without rules)",
        r"(?i)(bypass|circumvent|disable|turn off)[\s\S]{0,20}(safety|filter|guardrail|restriction)",
        r"(?i)jailbreak",
        r"(?i)DAN\s*(mode|prompt|jailbreak)",
        r"(?i)(do anything now|no restrictions|without limitations)",
        r"(?i)</?(system|user|assistant|human)>",  # Prompt delimiters injection
        r"(?i)\[INST\]|\[\/INST\]",                # Llama instruction format injection
    ]

    # ── Unsafe Output Keywords ───────────────────────────
    UNSAFE_OUTPUT_PATTERNS = [
        r"(?i)step[- ]by[- ]step.*?(bomb|explosive|weapon|poison)",
        r"(?i)(synthesize|manufacture|make)[\s\S]{0,30}(drug|explosive|weapon)",
        r"(?i)(password|credential|api.?key|secret.?key)[\s\S]{0,50}[a-z0-9]{20,}",
    ]

    def __init__(self):
        self._injection_regexes = [re.compile(p) for p in self.INJECTION_PATTERNS]
        self._unsafe_regexes = [re.compile(p) for p in self.UNSAFE_OUTPUT_PATTERNS]

    def check_input(self, query: str) -> Tuple[bool, str]:
        """
        Check if a user query is safe to process.
        
        Returns:
            (is_safe, reason) — True if safe, False with reason if blocked
        """
        # ── Length check ─────────────────────────────────
        if len(query) > 2000:
            logger.warning("Query too long", length=len(query))
            return False, "Query exceeds maximum length of 2000 characters."

        if len(query.strip()) < 2:
            return False, "Query is too short."

        # ── Injection pattern check ───────────────────────
        for pattern in self._injection_regexes:
            if pattern.search(query):
                logger.warning(
                    "🚨 Prompt injection detected",
                    pattern=pattern.pattern[:50],
                    query_preview=query[:100],
                )
                return False, "Query contains patterns that are not allowed."

        # ── Repeated characters check (potential DoS) ─────
        # e.g., "aaaaaaaaaa" * 200
        if len(query) > 100:
            unique_chars = len(set(query.lower().replace(" ", "")))
            if unique_chars < 5:
                return False, "Query appears to contain repetitive or non-meaningful content."

        return True, "OK"

    def check_output(self, response: str) -> Tuple[str, bool]:
        """
        Check and potentially sanitize a generated response.
        
        Returns:
            (response_text, is_safe) — filtered response and safety flag
        """
        if not settings.enable_output_filtering:
            return response, True

        for pattern in self._unsafe_regexes:
            if pattern.search(response):
                logger.warning(
                    "🚨 Unsafe output detected",
                    pattern=pattern.pattern[:50],
                )
                return (
                    "I'm sorry, I can't provide that information. "
                    "If you need help, please contact your system administrator.",
                    False,
                )

        return response, True

    def sanitize_query(self, query: str) -> str:
        """
        Clean up a query before processing.
        - Strip leading/trailing whitespace
        - Collapse multiple spaces
        - Remove null bytes
        """
        query = query.strip()
        query = re.sub(r"\s+", " ", query)
        query = query.replace("\x00", "")
        return query

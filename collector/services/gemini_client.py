from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Iterable
from typing import Any

from google import genai
from google.genai import types

from .gemini_quota_service import GeminiRateLimiter


logger = logging.getLogger(__name__)


class GeminiError(RuntimeError):
    pass


class GeminiConfigurationError(GeminiError):
    pass


class GeminiQuotaExceeded(GeminiError):
    pass


class GeminiResponseError(GeminiError):
    pass


class GeminiClient:
    MAX_PROMPT_CHARS = 40_000
    MAX_PROMPT_BYTES = 180_000
    MAX_OUTPUT_TOKENS = 4_096

    def __init__(
        self,
        api_key: str | None,
        model: str | None,
        rate_limiter: GeminiRateLimiter,
        *,
        max_attempts: int = 2,
    ):
        self.api_key = str(api_key or "").strip()
        self.model = str(model or "").strip()
        self.rate_limiter = rate_limiter
        self.max_attempts = max(1, min(int(max_attempts), 3))
        self.enabled = bool(self.api_key and self.model)
        self._client: genai.Client | None = None

        if self.api_key and not self.model:
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is configured but GEMINI_MODEL is missing. "
                "Configure the exact supported model ID instead of falling back to another model."
            )

    @property
    def client(self) -> genai.Client:
        if not self.enabled:
            raise GeminiConfigurationError("Gemini is not configured.")
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate_json(self, *, purpose: str, prompt: str) -> Any:
        if not self.enabled:
            raise GeminiConfigurationError("Gemini is not configured.")

        bounded_prompt = self._bounded_prompt(prompt)
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            decision = self.rate_limiter.reserve(purpose)
            if not decision.allowed:
                raise GeminiQuotaExceeded(decision.reason)
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=bounded_prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.0,
                        max_output_tokens=self.MAX_OUTPUT_TOKENS,
                    ),
                )
                text = getattr(response, "text", "") or ""
                return self.parse_json_payload(text)
            except GeminiResponseError:
                raise
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Gemini request failed purpose=%s attempt=%s/%s error_type=%s",
                    purpose,
                    attempt + 1,
                    self.max_attempts,
                    type(exc).__name__,
                )
                if attempt + 1 < self.max_attempts:
                    time.sleep(0.25 * (attempt + 1))

        raise GeminiError(f"Gemini request failed after {self.max_attempts} attempts") from last_error

    @classmethod
    def _bounded_prompt(cls, prompt: str) -> str:
        value = str(prompt or "")[: cls.MAX_PROMPT_CHARS]
        encoded = value.encode("utf-8")[: cls.MAX_PROMPT_BYTES]
        return encoded.decode("utf-8", errors="ignore")

    @classmethod
    def parse_json_payload(cls, text: str) -> Any:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        for candidate in cls._json_candidates(cleaned):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise GeminiResponseError("Gemini response did not contain valid JSON.")

    @staticmethod
    def _json_candidates(text: str) -> Iterable[str]:
        yield text
        object_start = text.find("{")
        object_end = text.rfind("}")
        if object_start >= 0 and object_end > object_start:
            yield text[object_start : object_end + 1]
        array_start = text.find("[")
        array_end = text.rfind("]")
        if array_start >= 0 and array_end > array_start:
            yield text[array_start : array_end + 1]

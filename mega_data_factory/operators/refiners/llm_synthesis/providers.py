"""
LLM Provider implementations for OpenAI, Anthropic (Claude), Google Gemini, and MiniMax.

Each provider handles API-specific request formatting, multimodal content encoding,
response parsing, and rate-limit detection. All providers use raw HTTP via httpx
for full control over proxy routing and connection management.
"""

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from .pool import Account

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from any LLM provider."""

    content: str = ""
    thinking: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    finish_reason: str = ""
    error: str = ""
    raw_response: dict = field(default_factory=dict)


class LLMProvider(ABC):
    """Abstract base for LLM API providers."""

    @abstractmethod
    def build_request(
        self,
        *,
        prompt: str,
        system_prompt: str | None,
        image_data: bytes | None,
        image_media_type: str,
        video_data: bytes | None,
        video_media_type: str,
        model: str,
        max_tokens: int,
        temperature: float,
        extra_params: dict[str, Any],
        account: Account,
    ) -> tuple[str, dict[str, str], dict[str, Any]]:
        """Build HTTP request components.

        Returns:
            Tuple of (url, headers, json_body)
        """

    @abstractmethod
    def parse_response(self, response: httpx.Response) -> LLMResponse:
        """Parse HTTP response into standardized format."""

    @abstractmethod
    def is_rate_limited(self, response: httpx.Response) -> bool:
        """Check if the response indicates rate limiting."""

    def get_retry_after(self, response: httpx.Response) -> float:
        """Extract retry-after duration from a rate-limited response."""
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
        return 60.0


class OpenAIProvider(LLMProvider):
    """Provider for OpenAI API and any OpenAI-compatible endpoint.

    Works with: OpenAI (GPT-4o, o3, etc.), DeepSeek, Together AI, Groq,
    Azure OpenAI, vLLM, Ollama, and any other OpenAI-compatible API.

    Set account.base_url to point to alternative endpoints.
    """

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    def build_request(
        self,
        *,
        prompt,
        system_prompt,
        image_data,
        image_media_type,
        video_data,
        video_media_type,
        model,
        max_tokens,
        temperature,
        extra_params,
        account,
    ):
        base_url = (account.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        url = f"{base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {account.api_key}",
            "Content-Type": "application/json",
        }
        if account.org_id:
            headers["OpenAI-Organization"] = account.org_id

        content = self._build_content(prompt, image_data, image_media_type)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": content})

        body: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body.update(extra_params)

        return url, headers, body

    @staticmethod
    def _build_content(
        prompt: str,
        image_data: bytes | None,
        image_media_type: str,
    ) -> str | list[dict]:
        """Build message content, using multipart format only when needed."""
        if not image_data:
            return prompt

        parts: list[dict] = []
        if prompt:
            parts.append({"type": "text", "text": prompt})
        b64 = base64.b64encode(image_data).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{image_media_type};base64,{b64}"},
            }
        )
        return parts

    def parse_response(self, response):
        data = response.json()
        if "error" in data:
            return LLMResponse(
                error=data["error"].get("message", str(data["error"])),
                raw_response=data,
            )

        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        usage = data.get("usage", {})

        # reasoning_content: DeepSeek-R1, OpenAI o-series reasoning
        thinking = message.get("reasoning_content", "")
        completion_details = usage.get("completion_tokens_details", {})

        return LLMResponse(
            content=message.get("content", "") or "",
            thinking=thinking or "",
            model=data.get("model", ""),
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            thinking_tokens=completion_details.get("reasoning_tokens", 0),
            finish_reason=choice.get("finish_reason", ""),
            raw_response=data,
        )

    def is_rate_limited(self, response):
        return response.status_code == 429


class AnthropicProvider(LLMProvider):
    """Provider for Anthropic Claude API with extended thinking support.

    Supports Claude 3.5, Claude 4, and future models. When enable_thinking
    is True, uses Claude's extended thinking mode for chain-of-thought reasoning.
    """

    DEFAULT_BASE_URL = "https://api.anthropic.com"
    API_VERSION = "2023-06-01"

    def __init__(self, enable_thinking: bool = False, thinking_budget: int = 10000):
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

    def build_request(
        self,
        *,
        prompt,
        system_prompt,
        image_data,
        image_media_type,
        video_data,
        video_media_type,
        model,
        max_tokens,
        temperature,
        extra_params,
        account,
    ):
        base_url = (account.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        url = f"{base_url}/v1/messages"

        headers = {
            "x-api-key": account.api_key,
            "anthropic-version": self.API_VERSION,
            "Content-Type": "application/json",
        }

        content = self._build_content(
            prompt,
            image_data,
            image_media_type,
            video_data,
            video_media_type,
        )

        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }

        if system_prompt:
            body["system"] = system_prompt

        if self.enable_thinking:
            body["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
        else:
            body["temperature"] = temperature

        body.update(extra_params)
        return url, headers, body

    @staticmethod
    def _build_content(
        prompt: str,
        image_data: bytes | None,
        image_media_type: str,
        video_data: bytes | None,
        video_media_type: str,
    ) -> str | list[dict]:
        """Build content blocks, using multipart only when media is present."""
        has_media = image_data or video_data
        if not has_media:
            return prompt

        blocks: list[dict] = []
        if image_data:
            b64 = base64.b64encode(image_data).decode("ascii")
            blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": image_media_type, "data": b64},
                }
            )
        if video_data:
            b64 = base64.b64encode(video_data).decode("ascii")
            blocks.append(
                {
                    "type": "video",
                    "source": {"type": "base64", "media_type": video_media_type, "data": b64},
                }
            )
        if prompt:
            blocks.append({"type": "text", "text": prompt})
        return blocks

    def parse_response(self, response):
        data = response.json()
        if data.get("type") == "error":
            error_info = data.get("error", {})
            return LLMResponse(
                error=error_info.get("message", str(error_info)),
                raw_response=data,
            )

        content_text = ""
        thinking_text = ""
        for block in data.get("content", []):
            if block.get("type") == "thinking":
                thinking_text += block.get("thinking", "")
            elif block.get("type") == "text":
                content_text += block.get("text", "")

        usage = data.get("usage", {})
        return LLMResponse(
            content=content_text,
            thinking=thinking_text,
            model=data.get("model", ""),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            thinking_tokens=usage.get("thinking_tokens", 0),
            finish_reason=data.get("stop_reason", ""),
            raw_response=data,
        )

    def is_rate_limited(self, response):
        return response.status_code == 429


class GeminiProvider(LLMProvider):
    """Provider for Google Gemini API with native thinking and video support.

    Supports Gemini 2.5 Flash/Pro with built-in thinking mode.
    Natively handles inline video and image content.
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"

    def __init__(self, enable_thinking: bool = False, thinking_budget: int = 0):
        self.enable_thinking = enable_thinking
        self.thinking_budget = thinking_budget

    def build_request(
        self,
        *,
        prompt,
        system_prompt,
        image_data,
        image_media_type,
        video_data,
        video_media_type,
        model,
        max_tokens,
        temperature,
        extra_params,
        account,
    ):
        base_url = (account.base_url or self.DEFAULT_BASE_URL).rstrip("/")
        url = f"{base_url}/v1beta/models/{model}:generateContent?key={account.api_key}"

        headers = {"Content-Type": "application/json"}

        parts = self._build_parts(
            prompt,
            image_data,
            image_media_type,
            video_data,
            video_media_type,
        )

        body: dict[str, Any] = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": temperature,
            },
        }

        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        if self.enable_thinking:
            thinking_config: dict[str, Any] = {"thinkingBudget": self.thinking_budget}
            body["generationConfig"]["thinkingConfig"] = thinking_config

        body.update(extra_params)
        return url, headers, body

    @staticmethod
    def _build_parts(
        prompt: str,
        image_data: bytes | None,
        image_media_type: str,
        video_data: bytes | None,
        video_media_type: str,
    ) -> list[dict]:
        parts: list[dict] = []
        if image_data:
            b64 = base64.b64encode(image_data).decode("ascii")
            parts.append({"inline_data": {"mime_type": image_media_type, "data": b64}})
        if video_data:
            b64 = base64.b64encode(video_data).decode("ascii")
            parts.append({"inline_data": {"mime_type": video_media_type, "data": b64}})
        if prompt:
            parts.append({"text": prompt})
        return parts

    def parse_response(self, response):
        data = response.json()

        if "error" in data:
            return LLMResponse(
                error=data["error"].get("message", str(data["error"])),
                raw_response=data,
            )

        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(error="No candidates in response", raw_response=data)

        candidate = candidates[0]
        content_text = ""
        thinking_text = ""

        for part in candidate.get("content", {}).get("parts", []):
            if part.get("thought"):
                thinking_text += part.get("text", "")
            elif "text" in part:
                content_text += part.get("text", "")

        usage = data.get("usageMetadata", {})
        return LLMResponse(
            content=content_text,
            thinking=thinking_text,
            model=data.get("modelVersion", ""),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            thinking_tokens=usage.get("thoughtsTokenCount", 0),
            finish_reason=candidate.get("finishReason", ""),
            raw_response=data,
        )

    def is_rate_limited(self, response):
        return response.status_code == 429


class MiniMaxProvider(OpenAIProvider):
    """Provider for MiniMax API (M2.7, M2.7-highspeed, M2.5, M2.5-highspeed).

    Uses MiniMax's OpenAI-compatible endpoint at api.minimax.io/v1.
    Temperature is clamped to (0.0, 1.0] per MiniMax API constraints.
    Thinking tags emitted by reasoning models are stripped from the response.
    """

    DEFAULT_BASE_URL = "https://api.minimax.io/v1"
    # MiniMax requires temperature in (0.0, 1.0] — clamp silently to avoid errors.
    _TEMP_MIN = 1e-6
    _TEMP_MAX = 1.0

    def build_request(self, *, temperature, **kwargs):
        clamped = max(self._TEMP_MIN, min(self._TEMP_MAX, temperature))
        return super().build_request(temperature=clamped, **kwargs)

    def parse_response(self, response):
        import re

        result = super().parse_response(response)
        # Strip <think>...</think> blocks emitted by reasoning-capable models.
        if result.content and "<think>" in result.content:
            think_match = re.search(r"<think>(.*?)</think>", result.content, re.DOTALL)
            if think_match:
                result.thinking = (result.thinking or "") + think_match.group(1)
                result.content = re.sub(
                    r"<think>.*?</think>", "", result.content, flags=re.DOTALL
                ).strip()
        return result


PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "minimax": MiniMaxProvider,
}

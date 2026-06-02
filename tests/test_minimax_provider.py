"""
Unit and integration tests for MiniMaxProvider.

Unit tests use mock HTTP responses; integration tests require MINIMAX_API_KEY.
Run integration tests with: pytest tests/test_minimax_provider.py -m integration -v
"""

import os
import sys
from datetime import timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Backport datetime.UTC for Python 3.10 (the project targets 3.11+).
# This must happen before any mega_data_factory import.
# ---------------------------------------------------------------------------
import datetime as _dt
if not hasattr(_dt, "UTC"):
    _dt.UTC = timezone.utc

from mega_data_factory.operators.refiners.llm_synthesis.providers import (
    PROVIDERS,
    MiniMaxProvider,
    LLMResponse,
)
from mega_data_factory.operators.refiners.llm_synthesis.pool import Account


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_account(api_key="test-key", base_url=None):
    return Account(api_key=api_key, base_url=base_url, org_id=None)


def _make_response(body: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = body
    mock.headers = {}
    return mock


def _openai_body(content: str, model: str = "MiniMax-M3", usage: dict | None = None):
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "model": model,
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 20},
    }


# ---------------------------------------------------------------------------
# Unit tests: registration
# ---------------------------------------------------------------------------

class TestMiniMaxRegistration:
    def test_registered_in_providers(self):
        assert "minimax" in PROVIDERS

    def test_is_minimax_provider(self):
        assert PROVIDERS["minimax"] is MiniMaxProvider


# ---------------------------------------------------------------------------
# Unit tests: default base URL
# ---------------------------------------------------------------------------

class TestMiniMaxDefaultBaseURL:
    def test_default_url(self):
        p = MiniMaxProvider()
        assert p.DEFAULT_BASE_URL == "https://api.minimax.io/v1"

    def test_builds_correct_url(self):
        p = MiniMaxProvider()
        account = _make_account()
        url, _, _ = p.build_request(
            prompt="hello",
            system_prompt=None,
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M2.7",
            max_tokens=100,
            temperature=0.7,
            extra_params={},
            account=account,
        )
        assert url == "https://api.minimax.io/v1/chat/completions"

    def test_respects_custom_base_url(self):
        p = MiniMaxProvider()
        account = _make_account(base_url="https://custom.minimax.io/v1")
        url, _, _ = p.build_request(
            prompt="hello",
            system_prompt=None,
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M2.7",
            max_tokens=100,
            temperature=0.7,
            extra_params={},
            account=account,
        )
        assert url == "https://custom.minimax.io/v1/chat/completions"


# ---------------------------------------------------------------------------
# Unit tests: temperature clamping
# ---------------------------------------------------------------------------

class TestMiniMaxTemperatureClamping:
    def _get_body_temperature(self, temperature: float) -> float:
        p = MiniMaxProvider()
        account = _make_account()
        _, _, body = p.build_request(
            prompt="test",
            system_prompt=None,
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M2.7",
            max_tokens=100,
            temperature=temperature,
            extra_params={},
            account=account,
        )
        return body["temperature"]

    def test_zero_clamped_to_minimum(self):
        t = self._get_body_temperature(0.0)
        assert t > 0.0

    def test_above_one_clamped(self):
        t = self._get_body_temperature(2.0)
        assert t <= 1.0

    def test_valid_temperature_unchanged(self):
        t = self._get_body_temperature(0.7)
        assert abs(t - 0.7) < 1e-9

    def test_one_is_valid(self):
        t = self._get_body_temperature(1.0)
        assert t == 1.0

    def test_negative_clamped(self):
        t = self._get_body_temperature(-0.5)
        assert t > 0.0


# ---------------------------------------------------------------------------
# Unit tests: request building
# ---------------------------------------------------------------------------

class TestMiniMaxRequestBuilding:
    def test_bearer_auth_header(self):
        p = MiniMaxProvider()
        account = _make_account(api_key="mm-secret")
        _, headers, _ = p.build_request(
            prompt="hi",
            system_prompt=None,
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M2.7",
            max_tokens=100,
            temperature=0.7,
            extra_params={},
            account=account,
        )
        assert headers["Authorization"] == "Bearer mm-secret"

    def test_model_in_body(self):
        p = MiniMaxProvider()
        account = _make_account()
        _, _, body = p.build_request(
            prompt="hi",
            system_prompt=None,
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M2.7-highspeed",
            max_tokens=100,
            temperature=0.7,
            extra_params={},
            account=account,
        )
        assert body["model"] == "MiniMax-M2.7-highspeed"

    def test_system_prompt_included(self):
        p = MiniMaxProvider()
        account = _make_account()
        _, _, body = p.build_request(
            prompt="hi",
            system_prompt="You are helpful.",
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M2.7",
            max_tokens=100,
            temperature=0.7,
            extra_params={},
            account=account,
        )
        assert body["messages"][0] == {"role": "system", "content": "You are helpful."}

    def test_m3_model(self):
        p = MiniMaxProvider()
        account = _make_account()
        _, _, body = p.build_request(
            prompt="hi",
            system_prompt=None,
            image_data=None,
            image_media_type="",
            video_data=None,
            video_media_type="",
            model="MiniMax-M3",
            max_tokens=100,
            temperature=0.5,
            extra_params={},
            account=account,
        )
        assert body["model"] == "MiniMax-M3"


# ---------------------------------------------------------------------------
# Unit tests: response parsing
# ---------------------------------------------------------------------------

class TestMiniMaxResponseParsing:
    def test_normal_response(self):
        p = MiniMaxProvider()
        response = _make_response(_openai_body("Hello world"))
        result = p.parse_response(response)
        assert result.content == "Hello world"
        assert result.error == ""

    def test_think_tag_stripped(self):
        p = MiniMaxProvider()
        body = _openai_body("<think>internal reasoning</think>Final answer.")
        response = _make_response(body)
        result = p.parse_response(response)
        assert "<think>" not in result.content
        assert result.content == "Final answer."
        assert "internal reasoning" in result.thinking

    def test_think_tag_multiline(self):
        p = MiniMaxProvider()
        body = _openai_body("<think>\nline1\nline2\n</think>Result.")
        response = _make_response(body)
        result = p.parse_response(response)
        assert result.content == "Result."
        assert "line1" in result.thinking

    def test_no_think_tag(self):
        p = MiniMaxProvider()
        body = _openai_body("Plain answer.")
        response = _make_response(body)
        result = p.parse_response(response)
        assert result.content == "Plain answer."
        assert result.thinking == ""

    def test_error_response(self):
        p = MiniMaxProvider()
        body = {"error": {"message": "Invalid API key", "code": 401}}
        response = _make_response(body)
        result = p.parse_response(response)
        assert "Invalid API key" in result.error

    def test_rate_limited(self):
        p = MiniMaxProvider()
        response = _make_response({}, status_code=429)
        assert p.is_rate_limited(response) is True

    def test_not_rate_limited(self):
        p = MiniMaxProvider()
        response = _make_response(_openai_body("ok"), status_code=200)
        assert p.is_rate_limited(response) is False

    def test_usage_fields(self):
        p = MiniMaxProvider()
        body = _openai_body("hi", usage={"prompt_tokens": 5, "completion_tokens": 15})
        response = _make_response(body)
        result = p.parse_response(response)
        assert result.input_tokens == 5
        assert result.output_tokens == 15


# ---------------------------------------------------------------------------
# Unit tests: online refiner integration
# ---------------------------------------------------------------------------

class TestMiniMaxOnlineRefiner:
    """Smoke tests for MiniMaxProvider inside LLMOnlineSynthesisRefiner."""

    @pytest.fixture(autouse=True)
    def _load_online(self):
        from mega_data_factory.operators.refiners.llm_synthesis.online import LLMOnlineSynthesisRefiner
        self.LLMOnlineSynthesisRefiner = LLMOnlineSynthesisRefiner

    def test_refiner_accepts_minimax_provider(self):
        refiner = self.LLMOnlineSynthesisRefiner(
            provider="minimax",
            model="MiniMax-M2.7",
            accounts=[{"api_key": "test-key"}],
        )
        assert isinstance(refiner.provider, MiniMaxProvider)

    def test_refiner_rejects_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            self.LLMOnlineSynthesisRefiner(
                provider="nonexistent",
                model="some-model",
                accounts=[{"api_key": "test-key"}],
            )

    def test_refiner_calls_minimax_api(self):
        refiner = self.LLMOnlineSynthesisRefiner(
            provider="minimax",
            model="MiniMax-M2.7",
            accounts=[{"api_key": "test-key"}],
            max_concurrent=1,
        )

        with patch.object(refiner, "_call_llm", return_value=LLMResponse(content="Synthesized content", model="MiniMax-M2.7")):
            records = [{"prompt": "Explain quantum computing."}]
            refiner.refine_batch(records)
            assert records[0]["llm_response"] == "Synthesized content"
            assert records[0]["llm_error"] == ""


# ---------------------------------------------------------------------------
# Integration tests (require MINIMAX_API_KEY)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestMiniMaxIntegration:
    """Live API tests. Run with: pytest -m integration"""

    @pytest.fixture(autouse=True)
    def setup(self):
        key = os.environ.get("MINIMAX_API_KEY")
        if not key:
            pytest.skip("MINIMAX_API_KEY not set")
        self.api_key = key
        from mega_data_factory.operators.refiners.llm_synthesis.online import LLMOnlineSynthesisRefiner
        self.LLMOnlineSynthesisRefiner = LLMOnlineSynthesisRefiner

    def test_m27_basic_call(self):
        refiner = self.LLMOnlineSynthesisRefiner(
            provider="minimax",
            model="MiniMax-M2.7",
            accounts=[{"api_key": self.api_key}],
            max_tokens=64,
        )
        records = [{"prompt": "Say 'hello' in one word."}]
        refiner.refine_batch(records)
        assert records[0]["llm_error"] == ""
        assert len(records[0]["llm_response"]) > 0

    def test_m27_highspeed_basic_call(self):
        refiner = self.LLMOnlineSynthesisRefiner(
            provider="minimax",
            model="MiniMax-M2.7-highspeed",
            accounts=[{"api_key": self.api_key}],
            max_tokens=64,
        )
        records = [{"prompt": "What is 2 + 2?"}]
        refiner.refine_batch(records)
        assert records[0]["llm_error"] == ""
        # Answer may land in response or thinking depending on model mode.
        combined = records[0]["llm_response"] + records[0]["llm_thinking"]
        assert "4" in combined

    def test_temperature_zero_clamped(self):
        # temperature=0.0 would be rejected by MiniMax; provider should clamp it.
        refiner = self.LLMOnlineSynthesisRefiner(
            provider="minimax",
            model="MiniMax-M2.7",
            accounts=[{"api_key": self.api_key}],
            max_tokens=32,
            temperature=0.0,
        )
        records = [{"prompt": "Say 'ok'."}]
        refiner.refine_batch(records)
        # If clamping works, no error should be returned.
        assert records[0]["llm_error"] == ""

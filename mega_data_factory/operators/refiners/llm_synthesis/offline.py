"""
LLM Offline Synthesis Refiner

Runs models locally via vLLM for high-throughput GPU inference without HTTP
overhead. Ideal for self-hosted models where you want maximum throughput on
your own hardware.

For calling remote APIs (OpenAI, Claude, Gemini), see LLMOnlineSynthesisRefiner.
"""

import base64
import json
import logging
import re
from collections import defaultdict
from typing import Any

import pyarrow as pa

from mega_data_factory.framework import Refiner

logger = logging.getLogger(__name__)

# Regex patterns for extracting thinking/reasoning from model outputs.
# Models like DeepSeek-R1, QwQ wrap reasoning in <think>...</think> tags.
THINKING_PATTERNS: dict[str, str] = {
    "deepseek": r"<think>(.*?)</think>",
    "qwq": r"<think>(.*?)</think>",
    "default": r"<think>(.*?)</think>",
}


def _extract_thinking(text: str, pattern_key: str = "default") -> tuple[str, str]:
    """Split model output into (thinking, response) using a regex pattern.

    Args:
        text: Raw model output text.
        pattern_key: Key into THINKING_PATTERNS, or a raw regex string.

    Returns:
        Tuple of (thinking_text, clean_response_text).
    """
    regex = THINKING_PATTERNS.get(pattern_key, pattern_key)
    match = re.search(regex, text, re.DOTALL)
    if match:
        thinking = match.group(1).strip()
        response = re.sub(regex, "", text, count=1, flags=re.DOTALL).strip()
        return thinking, response
    return "", text


class LLMOfflineSynthesisRefiner(Refiner):
    """Refiner that runs local models via vLLM for high-throughput synthesis.

    Loads a model directly onto GPUs and runs batch inference using vLLM's
    engine. No HTTP overhead, no account/proxy pools needed. vLLM handles
    continuous batching and GPU memory management internally.

    Best used with a single stage worker (num_replicas: 1) that owns all GPUs,
    letting vLLM manage parallelism internally via tensor_parallel_size.

    Features:
        - Local GPU inference via vLLM engine (no network I/O).
        - Continuous batching for maximum GPU utilization.
        - Tensor parallelism across multiple GPUs.
        - Multimodal support for vision-language models (VLMs).
        - Automatic thinking/reasoning extraction (DeepSeek-R1, QwQ, etc.).
        - Chat template application via the model's tokenizer.

    Config example (YAML)::

        - name: llm_offline_synthesis_refiner
          params:
            model: "Qwen/Qwen2.5-72B-Instruct"
            system_prompt: "You are a helpful assistant."
            prompt_field: prompt
            max_tokens: 4096
            temperature: 0.7
            tensor_parallel_size: 4
            gpu_memory_utilization: 0.90
    """

    def __init__(
        self,
        # Model
        model: str = "Qwen/Qwen2.5-7B-Instruct",
        system_prompt: str | None = None,
        # Input fields
        prompt_field: str = "prompt",
        prompt_template: str | None = None,
        image_field: str | None = None,
        # Output fields
        response_field: str = "llm_response",
        thinking_field: str = "llm_thinking",
        model_field: str = "llm_model",
        usage_field: str = "llm_usage",
        error_field: str = "llm_error",
        # Generation settings
        max_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 0.95,
        top_k: int = -1,
        repetition_penalty: float = 1.0,
        # Thinking extraction
        thinking_pattern: str = "default",
        # vLLM engine settings
        tensor_parallel_size: int = 1,
        gpu_memory_utilization: float = 0.90,
        max_model_len: int | None = None,
        dtype: str = "auto",
        quantization: str | None = None,
        trust_remote_code: bool = True,
        extra_engine_args: dict[str, Any] | None = None,
        extra_sampling_params: dict[str, Any] | None = None,
    ):
        """Initialize the offline synthesis refiner.

        Args:
            model: HuggingFace model name or local path.
            system_prompt: Optional system prompt prepended to every request.
            prompt_field: Record field containing the text prompt.
            prompt_template: Optional Python format string using record fields.
            image_field: Record field with image data (for VLMs).
            response_field: Output field for the LLM text response.
            thinking_field: Output field for extracted thinking/reasoning.
            model_field: Output field for the model name.
            usage_field: Output field for token usage JSON.
            error_field: Output field for errors (empty on success).
            max_tokens: Maximum tokens to generate per response.
            temperature: Sampling temperature.
            top_p: Nucleus sampling probability.
            top_k: Top-k sampling (-1 to disable).
            repetition_penalty: Repetition penalty (1.0 = no penalty).
            thinking_pattern: Key from THINKING_PATTERNS or a raw regex for
                extracting thinking traces from model output (e.g., "<think>...</think>").
            tensor_parallel_size: Number of GPUs for tensor parallelism.
            gpu_memory_utilization: Fraction of GPU memory vLLM may use.
            max_model_len: Maximum sequence length (None = model default).
            dtype: Data type for model weights ("auto", "float16", "bfloat16").
            quantization: Quantization method (None, "awq", "gptq", "squeezellm").
            trust_remote_code: Trust remote code in HuggingFace models.
            extra_engine_args: Additional kwargs passed to vllm.LLM().
            extra_sampling_params: Additional kwargs passed to SamplingParams().
        """
        super().__init__()

        self.model_name = model
        self.system_prompt = system_prompt
        self.prompt_field = prompt_field
        self.prompt_template = prompt_template
        self.image_field = image_field
        self.response_field = response_field
        self.thinking_field = thinking_field
        self.model_field = model_field
        self.usage_field = usage_field
        self.error_field = error_field
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repetition_penalty = repetition_penalty
        self.thinking_pattern = thinking_pattern
        self.extra_sampling_params = extra_sampling_params or {}

        # Lazy-init vLLM engine (deferred to first refine_batch for Ray compatibility)
        self._llm = None
        self._sampling_params = None
        self._engine_kwargs = {
            "model": model,
            "tensor_parallel_size": tensor_parallel_size,
            "gpu_memory_utilization": gpu_memory_utilization,
            "dtype": dtype,
            "trust_remote_code": trust_remote_code,
            **(extra_engine_args or {}),
        }
        if max_model_len is not None:
            self._engine_kwargs["max_model_len"] = max_model_len
        if quantization is not None:
            self._engine_kwargs["quantization"] = quantization

        logger.info(
            "LLM Offline Synthesis: model=%s tp=%d gpu_mem=%.0f%%",
            model,
            tensor_parallel_size,
            gpu_memory_utilization * 100,
        )

    def _ensure_engine(self):
        """Lazily initialize vLLM engine and sampling params on first use."""
        if self._llm is not None:
            return

        from vllm import LLM, SamplingParams

        logger.info("Loading vLLM engine: %s ...", self._engine_kwargs["model"])
        self._llm = LLM(**self._engine_kwargs)

        self._sampling_params = SamplingParams(
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            top_k=self.top_k,
            repetition_penalty=self.repetition_penalty,
            **self.extra_sampling_params,
        )
        logger.info("vLLM engine ready.")

    # ------------------------------------------------------------------
    # Prompt / media helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, record: dict) -> str:
        if self.prompt_template:
            return self.prompt_template.format_map(defaultdict(str, record))
        value = record.get(self.prompt_field, "")
        return str(value) if value is not None else ""

    def _extract_image(self, record: dict) -> bytes | None:
        """Extract raw image bytes from a record."""
        if not self.image_field:
            return None
        obj = record.get(self.image_field)
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get("bytes")
        if isinstance(obj, bytes):
            return obj
        return None

    def _build_messages(self, prompt: str, image_bytes: bytes | None) -> list[dict]:
        """Build an OpenAI-style messages list for vLLM chat()."""
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if image_bytes is not None:
            b64 = base64.b64encode(image_bytes).decode("ascii")
            content: list[dict[str, Any]] = [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]
            if prompt:
                content.insert(0, {"type": "text", "text": prompt})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})

        return messages

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Run batch inference via vLLM engine."""
        if not records:
            return

        self._ensure_engine()

        batch_messages = []
        valid_indices: list[int] = []
        errors: dict[int, str] = {}

        for i, record in enumerate(records):
            prompt = self._build_prompt(record)
            if not prompt:
                errors[i] = "empty_prompt"
                continue
            image_bytes = self._extract_image(record)
            messages = self._build_messages(prompt, image_bytes)
            batch_messages.append(messages)
            valid_indices.append(i)

        # Run vLLM batch inference
        outputs = []
        if batch_messages:
            try:
                outputs = self._llm.chat(
                    messages=batch_messages,
                    sampling_params=self._sampling_params,
                )
            except Exception as e:
                logger.error("vLLM batch inference failed: %s", e)
                for idx in valid_indices:
                    errors[idx] = f"vllm_error: {e}"

        # Write results back to records
        for result_idx, record_idx in enumerate(valid_indices):
            record = records[record_idx]
            if record_idx in errors:
                self._write_error(record, errors[record_idx])
                continue
            try:
                output = outputs[result_idx]
                generated = output.outputs[0]
                raw_text = generated.text

                thinking, response = _extract_thinking(raw_text, self.thinking_pattern)

                prompt_tokens = len(output.prompt_token_ids)
                completion_tokens = len(generated.token_ids)

                record[self.response_field] = response
                record[self.thinking_field] = thinking
                record[self.model_field] = self.model_name
                record[self.usage_field] = json.dumps(
                    {
                        "input_tokens": prompt_tokens,
                        "output_tokens": completion_tokens,
                        "thinking_tokens": 0,
                        "finish_reason": generated.finish_reason or "",
                    }
                )
                record[self.error_field] = ""
            except Exception as e:
                logger.error("Error processing output for record %d: %s", record_idx, e)
                self._write_error(record, f"output_parse_error: {e}")

        # Fill records that had errors before inference
        for idx, err in errors.items():
            if idx not in valid_indices or idx in errors:
                self._write_error(records[idx], err)

    def _write_error(self, record: dict, error: str):
        record[self.response_field] = ""
        record[self.thinking_field] = ""
        record[self.model_field] = self.model_name
        record[self.usage_field] = "{}"
        record[self.error_field] = error

    def get_output_schema(self) -> dict[str, pa.DataType]:
        return {
            self.response_field: pa.large_string(),
            self.thinking_field: pa.large_string(),
            self.model_field: pa.string(),
            self.usage_field: pa.string(),
            self.error_field: pa.string(),
        }

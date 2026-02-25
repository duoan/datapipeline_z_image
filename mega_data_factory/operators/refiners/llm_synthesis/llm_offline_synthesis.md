# LLMOfflineSynthesisRefiner

Runs models locally on GPUs via vLLM engine for high-throughput batch inference. No HTTP overhead, no account/proxy pools needed. Ideal for self-hosted models where you want maximum GPU utilization.

For calling remote APIs, see [LLMOnlineSynthesisRefiner](llm_online_synthesis.md).

## Requirements

```bash
pip install -e ".[llm-offline]"   # installs vllm
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | str | `"Qwen/Qwen2.5-7B-Instruct"` | HuggingFace model name or local path |
| `system_prompt` | str | `None` | System prompt prepended to every request |
| `prompt_field` | str | `"prompt"` | Record field containing the text prompt |
| `prompt_template` | str | `None` | Python format string using `{field_name}` syntax |
| `image_field` | str | `None` | Record field with image data (for VLMs) |
| `response_field` | str | `"llm_response"` | Output field for LLM response text |
| `thinking_field` | str | `"llm_thinking"` | Output field for extracted thinking content |
| `model_field` | str | `"llm_model"` | Output field for model name |
| `usage_field` | str | `"llm_usage"` | Output field for token usage (JSON) |
| `error_field` | str | `"llm_error"` | Output field for error messages |
| `max_tokens` | int | `4096` | Maximum tokens to generate |
| `temperature` | float | `0.7` | Sampling temperature |
| `top_p` | float | `0.95` | Nucleus sampling probability |
| `top_k` | int | `-1` | Top-k sampling (-1 = disabled) |
| `repetition_penalty` | float | `1.0` | Repetition penalty (1.0 = none) |
| `thinking_pattern` | str | `"default"` | Regex key or raw regex for thinking extraction |
| `tensor_parallel_size` | int | `1` | Number of GPUs for tensor parallelism |
| `gpu_memory_utilization` | float | `0.90` | Fraction of GPU memory vLLM may use |
| `max_model_len` | int | `None` | Maximum sequence length (None = model default) |
| `dtype` | str | `"auto"` | Weight dtype: `"auto"`, `"float16"`, `"bfloat16"` |
| `quantization` | str | `None` | Quantization: `None`, `"awq"`, `"gptq"`, `"squeezellm"` |
| `trust_remote_code` | bool | `True` | Trust remote code in HuggingFace models |
| `extra_engine_args` | dict | `None` | Additional kwargs passed to `vllm.LLM()` |
| `extra_sampling_params` | dict | `None` | Additional kwargs passed to `SamplingParams()` |

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `llm_response` | large_string | Generated response (thinking stripped if detected) |
| `llm_thinking` | large_string | Extracted thinking/reasoning trace |
| `llm_model` | string | Model name |
| `llm_usage` | string | JSON: `{"input_tokens", "output_tokens", "thinking_tokens", "finish_reason"}` |
| `llm_error` | string | Error message (empty on success) |

## Thinking Extraction

Models like DeepSeek-R1 and QwQ embed reasoning in `<think>...</think>` tags. The refiner automatically extracts this into `thinking_field` and returns the clean response in `response_field`.

Built-in patterns:

| `thinking_pattern` | Regex | Models |
|--------------------|-------|--------|
| `"default"` | `<think>(.*?)</think>` | Most reasoning models |
| `"deepseek"` | `<think>(.*?)</think>` | DeepSeek-R1 |
| `"qwq"` | `<think>(.*?)</think>` | Qwen QwQ |

Custom regex: set `thinking_pattern` to any regex with a capture group.

## Usage

```python
from mega_data_factory.operators.refiners.llm_synthesis import LLMOfflineSynthesisRefiner

refiner = LLMOfflineSynthesisRefiner(
    model="Qwen/Qwen2.5-72B-Instruct",
    system_prompt="You are a helpful assistant.",
    tensor_parallel_size=4,
    gpu_memory_utilization=0.90,
    max_tokens=4096,
)
refiner.refine_batch(records)
```

## Pipeline Config

### Qwen2.5 72B on 4 GPUs

```yaml
operators:
  - name: llm_offline_synthesis_refiner
    params:
      model: "Qwen/Qwen2.5-72B-Instruct"
      system_prompt: "You are a helpful assistant."
      prompt_field: prompt
      max_tokens: 4096
      temperature: 0.7
      tensor_parallel_size: 4
      gpu_memory_utilization: 0.90
```

Worker config (single worker owns all GPUs):

```yaml
worker:
  num_replicas: 1
  resources:
    cpu: 4
    gpu: 4
```

### DeepSeek-R1 with thinking extraction

```yaml
operators:
  - name: llm_offline_synthesis_refiner
    params:
      model: "deepseek-ai/DeepSeek-R1"
      prompt_field: prompt
      max_tokens: 8192
      thinking_pattern: deepseek
      tensor_parallel_size: 8
      gpu_memory_utilization: 0.95
```

### AWQ-quantized model (limited GPU memory)

```yaml
operators:
  - name: llm_offline_synthesis_refiner
    params:
      model: "Qwen/Qwen2.5-72B-Instruct-AWQ"
      prompt_field: prompt
      max_tokens: 4096
      quantization: awq
      tensor_parallel_size: 2
```

### Vision-language model

```yaml
operators:
  - name: llm_offline_synthesis_refiner
    params:
      model: "Qwen/Qwen2-VL-7B-Instruct"
      prompt_field: prompt
      image_field: image
      max_tokens: 2048
      tensor_parallel_size: 1
```

## Deployment Notes

- Use `num_replicas: 1` — let vLLM manage GPU parallelism internally via `tensor_parallel_size`.
- vLLM engine is lazy-initialized on first `refine_batch()` call (compatible with Ray serialization).
- vLLM handles continuous batching internally, so the pipeline `batch_size` mainly controls how many records are submitted at once.

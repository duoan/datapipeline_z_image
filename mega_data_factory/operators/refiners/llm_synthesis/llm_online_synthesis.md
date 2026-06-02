# LLMOnlineSynthesisRefiner

Calls remote LLM APIs (OpenAI, Claude, Gemini, MiniMax, DeepSeek, and any OpenAI-compatible endpoint) to synthesize responses from seed prompts. Features account pool rotation and proxy pool for anti-throttling.

For local GPU inference without HTTP overhead, see [LLMOfflineSynthesisRefiner](llm_offline_synthesis.md).

## Requirements

```bash
pip install -e ".[llm-online]"   # installs httpx[socks]
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `provider` | str | `"openai"` | LLM provider: `"openai"`, `"anthropic"`, `"gemini"`, `"minimax"` |
| `model` | str | `"gpt-4o"` | Model identifier |
| `system_prompt` | str | `None` | System prompt prepended to every request |
| `prompt_field` | str | `"prompt"` | Record field containing the text prompt |
| `prompt_template` | str | `None` | Python format string using `{field_name}` syntax. Overrides `prompt_field` |
| `image_field` | str | `None` | Record field with image data (for vision models) |
| `video_field` | str | `None` | Record field with video data (Gemini / Claude) |
| `response_field` | str | `"llm_response"` | Output field for LLM response text |
| `thinking_field` | str | `"llm_thinking"` | Output field for thinking/reasoning traces |
| `model_field` | str | `"llm_model"` | Output field for model identifier |
| `usage_field` | str | `"llm_usage"` | Output field for token usage (JSON) |
| `error_field` | str | `"llm_error"` | Output field for error messages |
| `max_tokens` | int | `4096` | Maximum tokens to generate |
| `temperature` | float | `0.7` | Sampling temperature |
| `enable_thinking` | bool | `False` | Enable extended thinking (Claude / Gemini 2.5) |
| `thinking_budget` | int | `10000` | Token budget for thinking |
| `accounts` | list[dict] | `None` | List of accounts: `[{"api_key": "...", "base_url": "...", "org_id": "..."}]` |
| `accounts_file` | str | `None` | Path to JSONL file with account dicts |
| `proxies` | list[str] | `None` | List of proxy URLs |
| `proxies_file` | str | `None` | Path to text file with proxy URLs |
| `max_concurrent` | int | `8` | Maximum concurrent API calls per batch |
| `retry_attempts` | int | `3` | Retry attempts per record |
| `retry_base_delay` | float | `1.0` | Base delay (seconds) for exponential backoff |
| `request_timeout` | float | `120.0` | HTTP request timeout (seconds) |
| `extra_params` | dict | `None` | Additional provider-specific request body parameters |

## Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `llm_response` | large_string | LLM response text |
| `llm_thinking` | large_string | Thinking/reasoning trace (if available) |
| `llm_model` | string | Actual model identifier returned by the API |
| `llm_usage` | string | JSON: `{"input_tokens", "output_tokens", "thinking_tokens", "finish_reason"}` |
| `llm_error` | string | Error message (empty string on success) |

## Supported Providers

| Provider | `provider` | Thinking support | Video support |
|----------|-----------|-----------------|---------------|
| OpenAI | `"openai"` | o-series `reasoning_content` | — |
| Anthropic Claude | `"anthropic"` | Extended thinking | Base64 video |
| Google Gemini | `"gemini"` | Gemini 2.5 thinking | Inline video |
| MiniMax | `"minimax"` | think-tag strip | — |
| DeepSeek | `"openai"` + `base_url` | R1 `reasoning_content` | — |
| Together / Groq / vLLM server | `"openai"` + `base_url` | — | — |

## Usage

```python
from mega_data_factory.operators.refiners.llm_synthesis import LLMOnlineSynthesisRefiner

refiner = LLMOnlineSynthesisRefiner(
    provider="anthropic",
    model="claude-sonnet-4-20250514",
    system_prompt="You are a helpful assistant.",
    prompt_field="prompt",
    accounts=[{"api_key": "sk-ant-..."}],
    max_concurrent=8,
)
refiner.refine_batch(records)
```

## Pipeline Config

### Claude with extended thinking

```yaml
operators:
  - name: llm_online_synthesis_refiner
    params:
      provider: anthropic
      model: claude-sonnet-4-20250514
      system_prompt: "Think step by step."
      prompt_field: prompt
      enable_thinking: true
      thinking_budget: 10000
      max_tokens: 8192
      accounts:
        - api_key: "${ANTHROPIC_API_KEY_1}"
        - api_key: "${ANTHROPIC_API_KEY_2}"
      proxies:
        - "http://user:pass@proxy1:8080"
      max_concurrent: 8
```

### DeepSeek-R1 via OpenAI-compatible API

```yaml
operators:
  - name: llm_online_synthesis_refiner
    params:
      provider: openai
      model: deepseek-reasoner
      prompt_field: prompt
      max_tokens: 8192
      accounts:
        - api_key: "${DEEPSEEK_API_KEY}"
          base_url: "https://api.deepseek.com/v1"
```

### MiniMax M3

```yaml
operators:
  - name: llm_online_synthesis_refiner
    params:
      provider: minimax
      model: MiniMax-M3
      system_prompt: "You are a helpful assistant."
      prompt_field: prompt
      max_tokens: 4096
      temperature: 0.7
      accounts:
        - api_key: "${MINIMAX_API_KEY}"
      max_concurrent: 8
```



```yaml
operators:
  - name: llm_online_synthesis_refiner
    params:
      provider: openai
      model: gpt-4o-mini
      prompt_template: |
        Given the following code:
        ```{language}
        {code}
        ```
        Explain what it does and suggest improvements.
      accounts:
        - api_key: "${OPENAI_API_KEY}"
```

## Account Pool

Accounts are rotated round-robin. Rate-limited accounts (HTTP 429) are temporarily skipped.

**Inline accounts:**

```yaml
accounts:
  - api_key: "sk-key1"
  - api_key: "sk-key2"
    base_url: "https://custom-endpoint.com"
  - api_key: "sk-key3"
    org_id: "org-xxx"
```

**From JSONL file** (one JSON object per line, `#` for comments):

```yaml
accounts_file: "secrets/accounts.jsonl"
```

## Proxy Pool

Proxies are rotated round-robin. Failed proxies get a 5-minute cooldown.

```yaml
proxies:
  - "http://user:pass@proxy1.example.com:8080"
  - "socks5://user:pass@proxy2.example.com:1080"
# Or from file:
proxies_file: "secrets/proxies.txt"
```

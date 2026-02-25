"""
LLM Online Synthesis Refiner

Calls remote LLM APIs (OpenAI, Claude, Gemini, and any OpenAI-compatible
endpoint) via HTTP to synthesize responses from seed prompts. Features
account pool rotation and proxy pool for anti-throttling.

For local GPU inference without HTTP overhead, see LLMOfflineSynthesisRefiner.
"""

import json
import logging
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx
import pyarrow as pa

from mega_data_factory.framework import Refiner

from .pool import AccountPool, ProxyPool
from .providers import PROVIDERS, LLMProvider, LLMResponse

logger = logging.getLogger(__name__)


class LLMOnlineSynthesisRefiner(Refiner):
    """Refiner that calls remote LLM APIs via HTTP to synthesize data.

    For each record, constructs a prompt (optionally with images or video),
    calls the configured LLM provider over HTTP, and stores the response,
    thinking trace, and usage metadata back into the record.

    Use this for cloud APIs (OpenAI, Claude, Gemini) or self-hosted endpoints
    (vLLM server, Ollama, TGI) that expose an HTTP interface.

    For local GPU inference without HTTP overhead, use LLMOfflineSynthesisRefiner.

    Features:
        - Multi-provider: OpenAI, Anthropic (Claude), Google Gemini, plus any
          OpenAI-compatible endpoint (DeepSeek, Together, Groq, vLLM, Ollama).
        - Account pool: round-robin rotation across API keys with automatic
          rate-limit detection and cooldown.
        - Proxy pool: round-robin rotation across HTTP/SOCKS proxies with
          failure tracking and recovery.
        - Multimodal: text, image, and video inputs.
        - Thinking/reasoning: captures extended thinking from Claude, Gemini 2.5,
          and reasoning traces from OpenAI o-series / DeepSeek-R1.
        - Concurrent: ThreadPoolExecutor for parallel API calls within a batch.
        - Retry: exponential backoff with account/proxy rotation on failures.

    Config example (YAML)::

        - name: llm_online_synthesis_refiner
          params:
            provider: anthropic
            model: claude-sonnet-4-20250514
            system_prompt: "You are a helpful assistant."
            prompt_field: prompt
            image_field: image
            max_tokens: 4096
            temperature: 0.7
            enable_thinking: true
            thinking_budget: 10000
            accounts:
              - api_key: "sk-ant-..."
              - api_key: "sk-ant-..."
            proxies:
              - "http://user:pass@proxy1:8080"
              - "socks5://proxy2:1080"
            max_concurrent: 8
    """

    def __init__(
        self,
        # Provider & model
        provider: str = "openai",
        model: str = "gpt-4o",
        system_prompt: str | None = None,
        # Input fields
        prompt_field: str = "prompt",
        prompt_template: str | None = None,
        image_field: str | None = None,
        video_field: str | None = None,
        # Output fields
        response_field: str = "llm_response",
        thinking_field: str = "llm_thinking",
        model_field: str = "llm_model",
        usage_field: str = "llm_usage",
        error_field: str = "llm_error",
        # Generation settings
        max_tokens: int = 4096,
        temperature: float = 0.7,
        enable_thinking: bool = False,
        thinking_budget: int = 10000,
        # Account pool
        accounts: list[dict] | None = None,
        accounts_file: str | None = None,
        # Proxy pool
        proxies: list[str] | None = None,
        proxies_file: str | None = None,
        # Execution settings
        max_concurrent: int = 8,
        retry_attempts: int = 3,
        retry_base_delay: float = 1.0,
        request_timeout: float = 120.0,
        extra_params: dict[str, Any] | None = None,
    ):
        """Initialize the LLM synthesis refiner.

        Args:
            provider: LLM provider name ("openai", "anthropic", "gemini").
            model: Model identifier (e.g., "gpt-4o", "claude-sonnet-4-20250514").
            system_prompt: Optional system prompt prepended to every request.
            prompt_field: Record field containing the text prompt.
            prompt_template: Optional Python format string that interpolates record
                fields, e.g. "Analyze this code:\\n{code}". Overrides prompt_field.
            image_field: Record field containing image data (bytes or dict with "bytes" key).
            video_field: Record field containing video data (bytes or dict with "bytes" key).
            response_field: Output field for the LLM text response.
            thinking_field: Output field for thinking/reasoning traces.
            model_field: Output field for the actual model identifier used.
            usage_field: Output field for token usage JSON.
            error_field: Output field for error messages (empty string on success).
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (ignored when thinking is enabled on Anthropic).
            enable_thinking: Enable extended thinking (Claude, Gemini 2.5).
            thinking_budget: Token budget for thinking (when enable_thinking=True).
            accounts: List of account dicts, each with at least "api_key".
                Optional keys: "base_url", "org_id".
            accounts_file: Path to JSONL file with account dicts (one per line).
            proxies: List of proxy URLs (http://, https://, socks5://).
            proxies_file: Path to text file with proxy URLs (one per line).
            max_concurrent: Maximum concurrent API calls per batch.
            retry_attempts: Number of retry attempts per record on failure.
            retry_base_delay: Base delay (seconds) for exponential backoff.
            request_timeout: HTTP request timeout in seconds.
            extra_params: Additional provider-specific parameters merged into the request body.
        """
        super().__init__()

        self.model = model
        self.system_prompt = system_prompt
        self.prompt_field = prompt_field
        self.prompt_template = prompt_template
        self.image_field = image_field
        self.video_field = video_field
        self.response_field = response_field
        self.thinking_field = thinking_field
        self.model_field = model_field
        self.usage_field = usage_field
        self.error_field = error_field
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_concurrent = max_concurrent
        self.retry_attempts = retry_attempts
        self.retry_base_delay = retry_base_delay
        self.request_timeout = request_timeout
        self.extra_params = extra_params or {}

        # Provider
        provider_key = provider.lower()
        if provider_key not in PROVIDERS:
            available = ", ".join(sorted(PROVIDERS.keys()))
            raise ValueError(f"Unknown provider '{provider}'. Available: {available}")

        provider_kwargs: dict[str, Any] = {}
        if provider_key in ("anthropic", "gemini"):
            provider_kwargs["enable_thinking"] = enable_thinking
            provider_kwargs["thinking_budget"] = thinking_budget
        self.provider: LLMProvider = PROVIDERS[provider_key](**provider_kwargs)

        # Account pool
        all_accounts = list(accounts or [])
        if accounts_file:
            all_accounts.extend(self._load_accounts_file(accounts_file))
        if not all_accounts:
            raise ValueError("At least one account required. Provide 'accounts' list or 'accounts_file' path.")
        self.account_pool = AccountPool(all_accounts)

        # Proxy pool
        all_proxies = list(proxies or [])
        if proxies_file:
            all_proxies.extend(self._load_proxies_file(proxies_file))
        self.proxy_pool = ProxyPool(all_proxies or None)

        # Lazy-init fields (not picklable for Ray serialization)
        self._executor: ThreadPoolExecutor | None = None
        self._clients: dict[str | None, httpx.Client] = {}
        self._clients_lock = threading.Lock()

        logger.info(
            "LLM Online Synthesis: provider=%s model=%s accounts=%d proxies=%d concurrent=%d",
            provider,
            model,
            self.account_pool.size,
            self.proxy_pool.size,
            max_concurrent,
        )

    # ------------------------------------------------------------------
    # File loaders
    # ------------------------------------------------------------------

    @staticmethod
    def _load_accounts_file(path: str) -> list[dict]:
        """Load accounts from a JSONL file (one JSON object per line).

        Lines starting with '#' are treated as comments.
        Each line must be a JSON object with at least an "api_key" field.
        """
        accounts: list[dict] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    accounts.append(json.loads(line))
        return accounts

    @staticmethod
    def _load_proxies_file(path: str) -> list[str]:
        """Load proxy URLs from a text file (one URL per line)."""
        proxies: list[str] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    proxies.append(line)
        return proxies

    # ------------------------------------------------------------------
    # Media extraction helpers
    # ------------------------------------------------------------------

    def _extract_media(self, record: dict, field: str | None) -> tuple[bytes | None, str]:
        """Extract binary data and MIME type from a record field."""
        if not field:
            return None, ""
        obj = record.get(field)
        if obj is None:
            return None, ""
        if isinstance(obj, dict):
            raw = obj.get("bytes")
            if raw:
                return raw, self._detect_mime(raw, field)
        elif isinstance(obj, bytes):
            return obj, self._detect_mime(obj, field)
        return None, ""

    @staticmethod
    def _detect_mime(data: bytes, field_hint: str = "") -> str:
        """Detect MIME type from magic bytes with a field-name fallback."""
        if len(data) >= 8:
            if data[:8] == b"\x89PNG\r\n\x1a\n":
                return "image/png"
            if data[:3] == b"\xff\xd8\xff":
                return "image/jpeg"
            if data[:6] in (b"GIF87a", b"GIF89a"):
                return "image/gif"
            if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                return "image/webp"
            if data[4:8] == b"ftyp":
                return "video/mp4"
            if data[:4] == b"\x1aE\xdf\xa3":
                return "video/webm"
        if "video" in field_hint.lower():
            return "video/mp4"
        return "image/jpeg"

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, record: dict) -> str:
        """Build the text prompt from a record.

        If prompt_template is set, interpolates record fields into the template
        using Python's str.format_map. Missing fields resolve to empty strings.
        Otherwise, returns the raw value of prompt_field.
        """
        if self.prompt_template:
            return self.prompt_template.format_map(defaultdict(str, record))
        value = record.get(self.prompt_field, "")
        return str(value) if value is not None else ""

    # ------------------------------------------------------------------
    # HTTP client management
    # ------------------------------------------------------------------

    def _get_client(self, proxy: str | None) -> httpx.Client:
        """Get or create a cached httpx.Client for the given proxy."""
        with self._clients_lock:
            if proxy not in self._clients:
                kwargs: dict[str, Any] = {
                    "timeout": self.request_timeout,
                    "follow_redirects": True,
                }
                if proxy:
                    kwargs["proxy"] = proxy
                self._clients[proxy] = httpx.Client(**kwargs)
            return self._clients[proxy]

    # ------------------------------------------------------------------
    # Single-record LLM call with retry
    # ------------------------------------------------------------------

    def _call_llm(self, record: dict) -> LLMResponse:
        """Make an LLM API call for one record with retry and pool rotation."""
        prompt = self._build_prompt(record)
        if not prompt:
            return LLMResponse(error="empty_prompt")

        image_data, image_mime = self._extract_media(record, self.image_field)
        video_data, video_mime = self._extract_media(record, self.video_field)

        last_error = ""
        for attempt in range(self.retry_attempts):
            account = self.account_pool.get_next()
            proxy = self.proxy_pool.get_next()

            try:
                url, headers, body = self.provider.build_request(
                    prompt=prompt,
                    system_prompt=self.system_prompt,
                    image_data=image_data,
                    image_media_type=image_mime,
                    video_data=video_data,
                    video_media_type=video_mime,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    extra_params=self.extra_params,
                    account=account,
                )

                client = self._get_client(proxy)
                response = client.post(url, headers=headers, json=body)

                if self.provider.is_rate_limited(response):
                    retry_after = self.provider.get_retry_after(response)
                    self.account_pool.mark_rate_limited(account, retry_after)
                    last_error = f"rate_limited (attempt {attempt + 1}/{self.retry_attempts})"
                    time.sleep(min(self.retry_base_delay * (2**attempt), retry_after))
                    continue

                if response.status_code >= 500:
                    last_error = f"server_error_{response.status_code} (attempt {attempt + 1}/{self.retry_attempts})"
                    time.sleep(self.retry_base_delay * (2**attempt))
                    continue

                if proxy:
                    self.proxy_pool.mark_success(proxy)
                self.account_pool.mark_success(account)

                result = self.provider.parse_response(response)
                if response.status_code >= 400 and not result.error:
                    result.error = f"http_{response.status_code}"
                return result

            except httpx.ConnectError:
                if proxy:
                    self.proxy_pool.mark_failed(proxy)
                last_error = f"connect_error (attempt {attempt + 1}/{self.retry_attempts})"
                time.sleep(self.retry_base_delay * (2**attempt))

            except httpx.TimeoutException:
                last_error = f"timeout (attempt {attempt + 1}/{self.retry_attempts})"
                time.sleep(self.retry_base_delay * (2**attempt))

            except Exception as e:
                last_error = f"{type(e).__name__}: {e} (attempt {attempt + 1}/{self.retry_attempts})"
                logger.debug("LLM call failed", exc_info=True)
                time.sleep(self.retry_base_delay * (2**attempt))

        return LLMResponse(error=f"all_{self.retry_attempts}_attempts_failed: {last_error}")

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def refine_batch(self, records: list[dict[str, Any]]) -> None:
        """Call LLM API for each record in the batch concurrently."""
        if not records:
            return

        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.max_concurrent)

        future_to_idx = {}
        for i, record in enumerate(records):
            future = self._executor.submit(self._call_llm, record)
            future_to_idx[future] = i

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            record = records[idx]
            try:
                result: LLMResponse = future.result()
                record[self.response_field] = result.content
                record[self.thinking_field] = result.thinking
                record[self.model_field] = result.model
                record[self.usage_field] = json.dumps(
                    {
                        "input_tokens": result.input_tokens,
                        "output_tokens": result.output_tokens,
                        "thinking_tokens": result.thinking_tokens,
                        "finish_reason": result.finish_reason,
                    }
                )
                record[self.error_field] = result.error
            except Exception as e:
                logger.error("Unexpected error processing record %d: %s", idx, e)
                record[self.response_field] = ""
                record[self.thinking_field] = ""
                record[self.model_field] = ""
                record[self.usage_field] = "{}"
                record[self.error_field] = f"unexpected: {e}"

    def get_output_schema(self) -> dict[str, pa.DataType]:
        return {
            self.response_field: pa.large_string(),
            self.thinking_field: pa.large_string(),
            self.model_field: pa.string(),
            self.usage_field: pa.string(),
            self.error_field: pa.string(),
        }

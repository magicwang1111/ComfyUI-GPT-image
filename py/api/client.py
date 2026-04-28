import asyncio
import time

import httpx

from .capabilities import DEFAULT_BASE_URL
from .exceptions import GPTImageAPIError

DEFAULT_MAX_RETRIES = 1
DEFAULT_RETRY_DELAY = 2.0
LOG_PREFIX = "[ComfyUI-GPT-image]"


def _build_timeout_config(timeout):
    return httpx.Timeout(connect=timeout, read=timeout, write=timeout, pool=timeout)


def _raise_timeout_error(exc, method, path, timeout):
    if isinstance(exc, httpx.ConnectTimeout):
        raise TimeoutError(
            f"API connection timed out after {timeout}s while connecting for {method} {path}."
        ) from exc

    if isinstance(exc, httpx.ReadTimeout):
        raise TimeoutError(
            f"API response timed out after {timeout}s while waiting for {method} {path}."
        ) from exc

    if isinstance(exc, httpx.WriteTimeout):
        raise TimeoutError(
            f"API upload timed out after {timeout}s while sending {method} {path}."
        ) from exc

    if isinstance(exc, httpx.PoolTimeout):
        raise TimeoutError(
            f"API connection pool timed out after {timeout}s while preparing {method} {path}."
        ) from exc

    raise TimeoutError(f"API request timed out after {timeout}s while waiting for {method} {path}.") from exc


def _normalize_optional_header(value):
    if value is None:
        return ""
    return str(value).strip()


def _is_retryable_http_error(exc):
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadError,
            httpx.RemoteProtocolError,
        ),
    )


def _format_http_error(exc, method, path, attempt, max_retries):
    detail = str(exc).strip() or exc.__class__.__name__
    retry_text = ""
    if max_retries > 0:
        retry_text = f" after {attempt + 1} attempt(s)"

    if isinstance(exc, httpx.ReadError):
        return (
            f"API connection was interrupted while waiting for {method} {path}{retry_text}: {detail}. "
            "The server or relay closed the connection before returning a response; retry the request or try a "
            "more stable base_url."
        )

    return f"API request failed for {method} {path}{retry_text}: {detail}"


def _format_bytes(size):
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _file_payload_size(file_item):
    try:
        payload = file_item[1]
        if isinstance(payload, tuple) and len(payload) >= 2:
            content = payload[1]
        else:
            content = payload

        if isinstance(content, (bytes, bytearray)):
            return len(content)
        if hasattr(content, "getbuffer"):
            return len(content.getbuffer())
        if hasattr(content, "tell") and hasattr(content, "seek"):
            current_position = content.tell()
            content.seek(0, 2)
            size = content.tell()
            content.seek(current_position)
            return size
    except Exception:
        return 0

    return 0


def _summarize_request_kwargs(kwargs):
    parts = []
    json_payload = kwargs.get("json")
    data_payload = kwargs.get("data")
    files_payload = kwargs.get("files")

    if isinstance(json_payload, dict):
        parts.append(f"json keys={list(json_payload.keys())}")
    if isinstance(data_payload, dict):
        parts.append(f"data keys={list(data_payload.keys())}")
    if files_payload:
        if isinstance(files_payload, (list, tuple)):
            total_size = sum(_file_payload_size(file_item) for file_item in files_payload)
            parts.append(f"files={len(files_payload)}")
            if total_size:
                parts.append(f"upload={_format_bytes(total_size)}")
        else:
            parts.append("files=provided")

    return ", ".join(parts) if parts else "no request body"


def _log_request_start(base_url, method, path, kwargs, attempt, total_attempts, timeout):
    print(
        f"{LOG_PREFIX} {method} {base_url}{path} attempt {attempt}/{total_attempts}: "
        f"{_summarize_request_kwargs(kwargs)}, timeout={timeout}s"
    )


def _log_request_retry(method, path, exc, attempt, total_attempts, retry_delay):
    detail = str(exc).strip() or exc.__class__.__name__
    print(
        f"{LOG_PREFIX} {method} {path} interrupted on attempt {attempt}/{total_attempts}: "
        f"{detail}; retrying in {retry_delay:g}s"
    )


def _log_response(method, path, status_code):
    print(f"{LOG_PREFIX} {method} {path} response status={status_code}")


def _build_headers(api_key, organization="", project=""):
    headers = {"Authorization": f"Bearer {api_key}"}
    organization = _normalize_optional_header(organization)
    project = _normalize_optional_header(project)

    if organization:
        headers["OpenAI-Organization"] = organization
    if project:
        headers["OpenAI-Project"] = project

    return headers


class Client:
    def __init__(
        self,
        api_key,
        timeout=60,
        base_url=DEFAULT_BASE_URL,
        organization="",
        project="",
        max_retries=DEFAULT_MAX_RETRIES,
        retry_delay=DEFAULT_RETRY_DELAY,
    ):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("api_key is required.")

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.organization = _normalize_optional_header(organization)
        self.project = _normalize_optional_header(project)
        self.max_retries = max(0, int(max_retries))
        self.retry_delay = max(0.0, float(retry_delay))
        timeout_config = _build_timeout_config(timeout)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_config,
            headers=_build_headers(self.api_key, organization=self.organization, project=self.project),
        )

    def request(self, method, path, **kwargs):
        total_attempts = self.max_retries + 1
        for attempt_index in range(total_attempts):
            attempt = attempt_index + 1
            _log_request_start(self.base_url, method, path, kwargs, attempt, total_attempts, self.timeout)
            try:
                response = self._client.request(method, path, **kwargs)
                _log_response(method, path, response.status_code)
                break
            except httpx.TimeoutException as exc:
                _raise_timeout_error(exc, method, path, self.timeout)
            except httpx.HTTPError as exc:
                if _is_retryable_http_error(exc) and attempt_index < self.max_retries:
                    _log_request_retry(method, path, exc, attempt, total_attempts, self.retry_delay)
                    time.sleep(self.retry_delay)
                    continue
                raise ConnectionError(_format_http_error(exc, method, path, attempt_index, self.max_retries)) from exc

        if response.status_code != 200:
            raise GPTImageAPIError.from_response(response)

        return response.json()

    def generate_image(self, payload):
        return self.request("POST", "/images/generations", json=payload)

    def edit_image(self, data, files):
        return self.request("POST", "/images/edits", data=data, files=files)

    def close(self):
        self._client.close()


class AsyncClient:
    def __init__(
        self,
        api_key,
        timeout=60,
        base_url=DEFAULT_BASE_URL,
        organization="",
        project="",
        max_retries=DEFAULT_MAX_RETRIES,
        retry_delay=DEFAULT_RETRY_DELAY,
    ):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("api_key is required.")

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        self.organization = _normalize_optional_header(organization)
        self.project = _normalize_optional_header(project)
        self.max_retries = max(0, int(max_retries))
        self.retry_delay = max(0.0, float(retry_delay))
        timeout_config = _build_timeout_config(timeout)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_config,
            headers=_build_headers(self.api_key, organization=self.organization, project=self.project),
        )

    async def request(self, method, path, **kwargs):
        total_attempts = self.max_retries + 1
        for attempt_index in range(total_attempts):
            attempt = attempt_index + 1
            _log_request_start(self.base_url, method, path, kwargs, attempt, total_attempts, self.timeout)
            try:
                response = await self._client.request(method, path, **kwargs)
                _log_response(method, path, response.status_code)
                break
            except httpx.TimeoutException as exc:
                _raise_timeout_error(exc, method, path, self.timeout)
            except httpx.HTTPError as exc:
                if _is_retryable_http_error(exc) and attempt_index < self.max_retries:
                    _log_request_retry(method, path, exc, attempt, total_attempts, self.retry_delay)
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise ConnectionError(_format_http_error(exc, method, path, attempt_index, self.max_retries)) from exc

        if response.status_code != 200:
            raise GPTImageAPIError.from_response(response)

        return response.json()

    async def generate_image(self, payload):
        return await self.request("POST", "/images/generations", json=payload)

    async def edit_image(self, data, files):
        return await self.request("POST", "/images/edits", data=data, files=files)

    async def close(self):
        await self._client.aclose()

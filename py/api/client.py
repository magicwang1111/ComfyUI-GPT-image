import asyncio
import time

import httpx

from .capabilities import DEFAULT_BASE_URL
from .exceptions import GPTImageAPIError

DEFAULT_MAX_RETRIES = 1
DEFAULT_RETRY_DELAY = 2.0


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
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method, path, **kwargs)
                break
            except httpx.TimeoutException as exc:
                _raise_timeout_error(exc, method, path, self.timeout)
            except httpx.HTTPError as exc:
                if _is_retryable_http_error(exc) and attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                    continue
                raise ConnectionError(_format_http_error(exc, method, path, attempt, self.max_retries)) from exc

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
        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.request(method, path, **kwargs)
                break
            except httpx.TimeoutException as exc:
                _raise_timeout_error(exc, method, path, self.timeout)
            except httpx.HTTPError as exc:
                if _is_retryable_http_error(exc) and attempt < self.max_retries:
                    await asyncio.sleep(self.retry_delay)
                    continue
                raise ConnectionError(_format_http_error(exc, method, path, attempt, self.max_retries)) from exc

        if response.status_code != 200:
            raise GPTImageAPIError.from_response(response)

        return response.json()

    async def generate_image(self, payload):
        return await self.request("POST", "/images/generations", json=payload)

    async def edit_image(self, data, files):
        return await self.request("POST", "/images/edits", data=data, files=files)

    async def close(self):
        await self._client.aclose()

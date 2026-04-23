import httpx

from .capabilities import DEFAULT_BASE_URL
from .exceptions import GPTImageAPIError


def _build_timeout_config(timeout):
    return httpx.Timeout(connect=10.0, read=timeout, write=timeout, pool=timeout)


def _build_headers(api_key):
    return {
        "Authorization": f"Bearer {api_key}",
    }


class Client:
    def __init__(self, api_key, timeout=60, base_url=DEFAULT_BASE_URL):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("api_key is required.")

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        timeout_config = _build_timeout_config(timeout)
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout_config,
            headers=_build_headers(self.api_key),
        )

    def request(self, method, path, **kwargs):
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"API request timed out after {self.timeout}s while waiting for {method} {path}.") from exc
        except httpx.HTTPError as exc:
            raise ConnectionError(f"API request failed for {method} {path}: {exc}") from exc

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
    def __init__(self, api_key, timeout=60, base_url=DEFAULT_BASE_URL):
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError("api_key is required.")

        self.api_key = api_key
        self.timeout = timeout
        self.base_url = (base_url or DEFAULT_BASE_URL).strip().rstrip("/")
        timeout_config = _build_timeout_config(timeout)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout_config,
            headers=_build_headers(self.api_key),
        )

    async def request(self, method, path, **kwargs):
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"API request timed out after {self.timeout}s while waiting for {method} {path}.") from exc
        except httpx.HTTPError as exc:
            raise ConnectionError(f"API request failed for {method} {path}: {exc}") from exc

        if response.status_code != 200:
            raise GPTImageAPIError.from_response(response)

        return response.json()

    async def generate_image(self, payload):
        return await self.request("POST", "/images/generations", json=payload)

    async def edit_image(self, data, files):
        return await self.request("POST", "/images/edits", data=data, files=files)

    async def close(self):
        await self._client.aclose()

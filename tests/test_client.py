import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from _loader import import_module

client_module = import_module("py.api.client")
nodes = import_module("py.nodes")


class FakeResolvedClient:
    def __init__(self, api_key, timeout=60, base_url=None, organization="", project=""):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = base_url
        self.organization = organization
        self.project = project

    def close(self):
        pass


class FakeResolvedAsyncClient(FakeResolvedClient):
    async def close(self):
        pass


class RuntimeConfigResolutionTests(unittest.TestCase):
    def test_json_values_have_highest_priority(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_key": "json-key",
                        "request_timeout": 90,
                        "base_url": "https://json.example.com/",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "GPT_IMAGE_API_KEY": "env-key",
                    "GPT_IMAGE_BASE_URL": "https://env.example.com",
                },
                clear=False,
            ):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "json-key")
                        self.assertEqual(client.timeout, 90)
                        self.assertEqual(client.base_url, "https://json.example.com")
                        self.assertEqual(client.organization, "")
                        self.assertEqual(client.project, "")
                        client.close()

    def test_env_values_are_used_when_json_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"

            with patch.dict(
                "os.environ",
                {
                    "GPT_IMAGE_API_KEY": "env-key",
                    "GPT_IMAGE_BASE_URL": "https://env.example.com/",
                },
                clear=False,
            ):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "env-key")
                        self.assertEqual(client.timeout, nodes.DEFAULT_REQUEST_TIMEOUT)
                        self.assertEqual(client.base_url, "https://env.example.com")
                        self.assertEqual(client.organization, "")
                        self.assertEqual(client.project, "")
                        client.close()

    def test_openai_provider_uses_openai_defaults_and_env_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_provider": "openai",
                        "request_timeout": 80,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "OPENAI_API_KEY": "openai-env-key",
                },
                clear=True,
            ):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "openai-env-key")
                        self.assertEqual(client.timeout, 80)
                        self.assertEqual(client.base_url, "https://api.openai.com/v1")
                        self.assertEqual(client.organization, "")
                        self.assertEqual(client.project, "")
                        client.close()

    def test_openai_headers_are_resolved_from_json_or_env(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_key": "json-key",
                        "openai_organization": "org_json",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "OPENAI_PROJECT_ID": "proj_env",
                },
                clear=True,
            ):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.organization, "org_json")
                        self.assertEqual(client.project, "proj_env")
                        client.close()

    def test_async_runtime_client_uses_same_resolved_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_key": "json-key",
                        "request_timeout": 75,
                        "base_url": "https://json.example.com/",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "AsyncClient", FakeResolvedAsyncClient):
                        client = nodes._create_runtime_async_client()
                        self.assertEqual(client.api_key, "json-key")
                        self.assertEqual(client.timeout, 75)
                        self.assertEqual(client.base_url, "https://json.example.com")
                        self.assertEqual(client.organization, "")
                        self.assertEqual(client.project, "")
                        asyncio.run(client.close())

    def test_missing_key_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"

            with patch.dict("os.environ", {}, clear=True):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with self.assertRaises(ValueError):
                        nodes._create_runtime_client()


class ClientTransportTests(unittest.TestCase):
    def test_timeout_config_uses_same_timeout_for_all_phases(self):
        timeout = client_module._build_timeout_config(1200)

        self.assertEqual(timeout.connect, 1200)
        self.assertEqual(timeout.read, 1200)
        self.assertEqual(timeout.write, 1200)
        self.assertEqual(timeout.pool, 1200)

    def test_builds_bearer_headers(self):
        client = client_module.Client(
            "relay-key",
            base_url="https://relay.example.com",
        )
        try:
            self.assertEqual(client.base_url, "https://relay.example.com")
            self.assertEqual(client._client.headers.get("Authorization"), "Bearer relay-key")
        finally:
            client.close()

    def test_async_client_builds_bearer_headers(self):
        client = client_module.AsyncClient(
            "relay-key",
            base_url="https://relay.example.com",
        )
        try:
            self.assertEqual(client.base_url, "https://relay.example.com")
            self.assertEqual(client._client.headers.get("Authorization"), "Bearer relay-key")
        finally:
            asyncio.run(client.close())

    def test_client_builds_optional_openai_headers(self):
        client = client_module.Client(
            "openai-key",
            base_url="https://api.openai.com/v1",
            organization="org_123",
            project="proj_456",
        )
        try:
            self.assertEqual(client._client.headers.get("Authorization"), "Bearer openai-key")
            self.assertEqual(client._client.headers.get("OpenAI-Organization"), "org_123")
            self.assertEqual(client._client.headers.get("OpenAI-Project"), "proj_456")
        finally:
            client.close()

    def test_client_surfaces_connect_timeout_with_real_timeout_value(self):
        client = client_module.Client(
            "relay-key",
            timeout=1200,
            base_url="https://relay.example.com",
        )
        try:
            request = httpx.Request("POST", "https://relay.example.com/images/edits")
            with patch.object(
                client._client,
                "request",
                side_effect=httpx.ConnectTimeout("boom", request=request),
            ):
                with self.assertRaisesRegex(
                    TimeoutError,
                    r"API connection timed out after 1200s while connecting for POST /images/edits\.",
                ):
                    client.edit_image({}, {})
        finally:
            client.close()

    def test_async_client_surfaces_read_timeout_with_real_timeout_value(self):
        client = client_module.AsyncClient(
            "relay-key",
            timeout=1200,
            base_url="https://relay.example.com",
        )
        try:
            request = httpx.Request("POST", "https://relay.example.com/images/edits")
            with patch.object(
                client._client,
                "request",
                new=AsyncMock(side_effect=httpx.ReadTimeout("boom", request=request)),
            ):
                with self.assertRaisesRegex(
                    TimeoutError,
                    r"API response timed out after 1200s while waiting for POST /images/edits\.",
                ):
                    asyncio.run(client.edit_image({}, {}))
        finally:
            asyncio.run(client.close())


if __name__ == "__main__":
    unittest.main()

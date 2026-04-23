import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _loader import import_module

client_module = import_module("py.api.client")
nodes = import_module("py.nodes")


class FakeResolvedClient:
    def __init__(self, api_key, timeout=60, base_url=None):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = base_url

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
                        asyncio.run(client.close())

    def test_missing_key_raises(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"

            with patch.dict("os.environ", {}, clear=True):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with self.assertRaises(ValueError):
                        nodes._create_runtime_client()


class ClientTransportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

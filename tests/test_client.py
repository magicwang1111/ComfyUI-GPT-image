import asyncio
import contextlib
import io
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
    def __init__(
        self,
        api_key,
        timeout=60,
        base_url=None,
        organization="",
        project="",
        api_provider="relay",
        max_retries=1,
        retry_delay=2.0,
    ):
        self.api_key = api_key
        self.timeout = timeout
        self.base_url = base_url
        self.organization = organization
        self.project = project
        self.api_provider = api_provider
        self.max_retries = max_retries
        self.retry_delay = retry_delay

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
                        "request_retries": 3,
                        "retry_delay": 0.5,
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
                        self.assertEqual(client.max_retries, 3)
                        self.assertEqual(client.retry_delay, 0.5)
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

    def test_azure_provider_uses_azure_env_key_and_endpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_provider": "azure",
                        "request_timeout": 300,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "AZURE_OPENAI_API_KEY": "azure-env-key",
                    "AZURE_OPENAI_ENDPOINT": "https://example-resource.services.ai.azure.com",
                },
                clear=True,
            ):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "azure-env-key")
                        self.assertEqual(client.timeout, 300)
                        self.assertEqual(
                            client.base_url,
                            "https://example-resource.services.ai.azure.com/openai/v1",
                        )
                        self.assertEqual(client.organization, "")
                        self.assertEqual(client.project, "")
                        client.close()

    def test_azure_provider_preserves_configured_openai_v1_endpoint(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_key": "azure-json-key",
                        "api_provider": "azure",
                        "base_url": "https://example-resource.services.ai.azure.com/openai/v1/",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "azure-json-key")
                        self.assertEqual(
                            client.base_url,
                            "https://example-resource.services.ai.azure.com/openai/v1",
                        )
                        client.close()

    def test_vapeur_provider_overrides_legacy_generic_azure_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"
            json_path.write_text(
                json.dumps(
                    {
                        "api_key": "legacy-azure-key",
                        "api_provider": "vapeur",
                        "base_url": "https://legacy-resource.services.ai.azure.com/openai/v1",
                        "VAPEUR_API_KEY": "vapeur-json-key",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict("os.environ", {}, clear=True):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "vapeur-json-key")
                        self.assertEqual(client.api_provider, "vapeur")
                        self.assertEqual(client.base_url, "https://api.vapeur.ai/v1")
                        client.close()

    def test_vapeur_env_key_selects_vapeur_provider(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path = Path(temp_dir) / "config.local.json"

            with patch.dict(
                "os.environ",
                {
                    "VAPEUR_API_KEY": "vapeur-env-key",
                },
                clear=True,
            ):
                with patch.object(nodes, "CONFIG_JSON_PATH", json_path):
                    with patch.object(nodes, "Client", FakeResolvedClient):
                        client = nodes._create_runtime_client()
                        self.assertEqual(client.api_key, "vapeur-env-key")
                        self.assertEqual(client.base_url, "https://api.vapeur.ai/v1")
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

    def test_async_client_retries_interrupted_read_once(self):
        client = client_module.AsyncClient(
            "relay-key",
            max_retries=1,
            retry_delay=0,
            base_url="https://relay.example.com",
        )
        try:
            request = httpx.Request("POST", "https://relay.example.com/images/edits")
            with patch.object(
                client._client,
                "request",
                new=AsyncMock(
                    side_effect=[
                        httpx.ReadError("", request=request),
                        httpx.Response(200, json={"ok": True}, request=request),
                    ]
                ),
            ) as request_mock:
                response = asyncio.run(client.edit_image({}, {}))

            self.assertEqual(response, {"ok": True})
            self.assertEqual(request_mock.call_count, 2)
        finally:
            asyncio.run(client.close())

    def test_vapeur_edit_uses_query_parameters_and_image_field(self):
        client = client_module.AsyncClient(
            "vapeur-key",
            api_provider="vapeur",
            base_url="https://api.vapeur.ai/v1",
        )
        try:
            request = httpx.Request("POST", "https://api.vapeur.ai/v1/images/edits")
            response = httpx.Response(200, json={"ok": True}, request=request)
            data = {
                "model": "gpt-image-2",
                "prompt": "secret prompt",
                "size": "1024x1024",
                "input_fidelity": "high",
            }
            files = [
                ("image[]", ("input_0.png", b"png-data", "image/png")),
                ("image[]", ("input_1.png", b"png-data", "image/png")),
            ]

            with patch.object(client._client, "request", new=AsyncMock(return_value=response)) as request_mock:
                result = asyncio.run(client.edit_image(data, files))

            self.assertEqual(result, {"ok": True})
            request_kwargs = request_mock.await_args.kwargs
            self.assertNotIn("data", request_kwargs)
            self.assertEqual(request_kwargs["params"]["model"], "gpt-image-2")
            self.assertEqual(request_kwargs["params"]["prompt"], "secret prompt")
            self.assertEqual(request_kwargs["params"]["response_format"], "b64_json")
            self.assertNotIn("input_fidelity", request_kwargs["params"])
            self.assertTrue(all(item[0] == "image" for item in request_kwargs["files"]))
        finally:
            asyncio.run(client.close())

    def test_read_error_message_names_interrupted_connection(self):
        client = client_module.Client(
            "relay-key",
            max_retries=0,
            base_url="https://relay.example.com",
        )
        try:
            request = httpx.Request("POST", "https://relay.example.com/images/edits")
            with patch.object(
                client._client,
                "request",
                side_effect=httpx.ReadError("", request=request),
            ):
                with self.assertRaisesRegex(
                    ConnectionError,
                    r"API connection was interrupted while waiting for POST /images/edits: ReadError",
                ):
                    client.edit_image({}, {})
        finally:
            client.close()

    def test_request_logging_summarizes_without_prompt_text(self):
        client = client_module.Client(
            "relay-key",
            max_retries=0,
            base_url="https://relay.example.com",
        )
        try:
            request = httpx.Request("POST", "https://relay.example.com/images/generations")
            response = httpx.Response(200, json={"ok": True}, request=request)

            output = io.StringIO()
            with patch.object(client._client, "request", return_value=response):
                with contextlib.redirect_stdout(output):
                    result = client.generate_image({"model": "gpt-image-2", "prompt": "secret prompt"})

            logged = output.getvalue()
            self.assertEqual(result, {"ok": True})
            self.assertIn("POST https://relay.example.com/images/generations attempt 1/1", logged)
            self.assertIn("json keys=['model', 'prompt']", logged)
            self.assertIn("response status=200", logged)
            self.assertNotIn("secret prompt", logged)
        finally:
            client.close()


if __name__ == "__main__":
    unittest.main()

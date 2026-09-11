import asyncio
import base64
import io
import json
import unittest
from unittest.mock import patch

import PIL.Image

from _loader import ensure_package_loaded, import_module

nodes = import_module("py.nodes")


def _make_base64_png(color):
    image = PIL.Image.new("RGB", (4, 4), color=color)
    bytes_io = io.BytesIO()
    image.save(bytes_io, format="PNG")
    return base64.b64encode(bytes_io.getvalue()).decode("utf-8")


class FakeAsyncClient:
    def __init__(self, usage=None, api_provider="vapeur"):
        self.generate_calls = []
        self.edit_calls = []
        self.closed = False
        self.usage = usage
        self.api_provider = api_provider

    async def generate_image(self, payload):
        self.generate_calls.append(payload)
        image_count = int(payload.get("n", 1))
        response = {
            "data": [
                {"b64_json": _make_base64_png((255, index, 0))}
                for index in range(image_count)
            ]
        }
        if self.usage is not None:
            response["usage"] = self.usage
        return response

    async def edit_image(self, data, files):
        self.edit_calls.append((data, files))
        image_count = int(data.get("n", 1))
        response = {
            "data": [
                {"b64_json": _make_base64_png((0, index, 255))}
                for index in range(image_count)
            ]
        }
        if self.usage is not None:
            response["usage"] = self.usage
        return response

    async def close(self):
        self.closed = True


class NodeExecutionTests(unittest.TestCase):
    def test_azure_25_omits_fidelity_but_other_models_and_providers_preserve_it(self):
        import torch

        for provider, model in (("azure", "gpt-image-2.5-flare"), ("azure", "gpt-image-2.5-sunburst"), ("azure", "gpt-image-2"), ("openai", "gpt-image-2.5-flare"), ("openai", "gpt-image-2.5-sunburst")):
            with self.subTest(provider=provider, model=model):
                client = FakeAsyncClient(api_provider=provider)
                with patch.object(nodes, "_create_runtime_async_client", return_value=client):
                    asyncio.run(nodes.GPTImageEditNode().generate(
                        prompt="test", images=torch.zeros((2, 8, 8, 3)), model=model, input_fidelity="high",
                    ))
                data, files = client.edit_calls[0]
                self.assertEqual(len(files), 2)
                if provider == "azure" and model in ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst"):
                    self.assertNotIn("input_fidelity", data)
                else:
                    self.assertEqual(data["input_fidelity"], "high")

    def test_unsupported_quality_fails_before_client_creation(self):
        with patch.object(nodes, "_create_runtime_async_client") as factory:
            with self.assertRaisesRegex(ValueError, "quality"):
                asyncio.run(nodes.GPTImageGenerateNode().generate(prompt="test", model="gpt-image-2", quality="max"))
            factory.assert_not_called()

    def test_25_quality_and_deployment_are_sent_unchanged(self):
        client = FakeAsyncClient(api_provider="azure")
        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(nodes.GPTImageGenerateNode().generate(
                prompt="test", model="gpt-image-2.5-flare", quality="max", model_override="my-flare-deployment",
            ))
        self.assertEqual(client.generate_calls[0]["quality"], "max")
        self.assertEqual(client.generate_calls[0]["model"], "my-flare-deployment")

    def test_generation_nodes_do_not_require_client_input(self):
        generate_inputs = nodes.GPTImageGenerateNode.INPUT_TYPES()
        edit_inputs = nodes.GPTImageEditNode.INPUT_TYPES()

        self.assertNotIn("client", generate_inputs["required"])
        self.assertNotIn("client", edit_inputs["required"])
        self.assertEqual(generate_inputs["optional"]["aspect_ratio"][0], nodes.ASPECT_RATIO_OPTIONS)
        self.assertEqual(edit_inputs["optional"]["aspect_ratio"][0], nodes.ASPECT_RATIO_OPTIONS)

    def test_generate_node_is_registered(self):
        package = ensure_package_loaded()

        self.assertIn("ComfyUI-GPT-image Generate", package.NODE_CLASS_MAPPINGS)
        self.assertIn("ComfyUI-GPT-image Edit", package.NODE_CLASS_MAPPINGS)

    def test_blank_model_override_uses_selected_model(self):
        client = FakeAsyncClient()

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageGenerateNode().generate(
                    "hello",
                    model="gpt-image-2",
                    model_override="",
                )
            )

        self.assertEqual(client.generate_calls[0]["model"], "gpt-image-2")
        self.assertTrue(client.closed)

    def test_model_override_changes_outbound_generate_model_name(self):
        client = FakeAsyncClient()

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageGenerateNode().generate(
                    "hello",
                    model="gpt-image-2",
                    model_override="relay-gpt-image",
                )
            )

        self.assertEqual(client.generate_calls[0]["model"], "relay-gpt-image")
        self.assertTrue(client.closed)

    def test_generate_node_returns_image_batch_for_n(self):
        client = FakeAsyncClient()

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            image, response_json = asyncio.run(
                nodes.GPTImageGenerateNode().generate(
                    "hello",
                    n=2,
                )
            )

        self.assertEqual(tuple(image.shape), (2, 4, 4, 3))
        self.assertIn("base64 omitted", response_json)
        self.assertTrue(client.closed)

    def test_generate_node_calculates_size_from_selected_ratio(self):
        client = FakeAsyncClient()

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageGenerateNode().generate(
                    "hello",
                    size="2K",
                    aspect_ratio="4:3",
                )
            )

        self.assertEqual(client.generate_calls[0]["size"], "2048x1536")
        self.assertTrue(client.closed)

    def test_generate_node_returns_vapeur_cost_ui_and_response_breakdown(self):
        usage = {
            "input_tokens": 972,
            "output_tokens": 196,
            "input_tokens_details": {
                "text_tokens": 12,
                "image_tokens": 960,
            },
            "output_tokens_details": {
                "text_tokens": 0,
                "image_tokens": 196,
            },
        }
        client = FakeAsyncClient(usage=usage)

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            node_result = asyncio.run(nodes.GPTImageGenerateNode().generate("hello"))

        self.assertEqual(
            node_result["ui"]["gpt_image_cost"],
            ["本次费用（预估）：$0.013620\n文本输入 12 · 图片输入 960 · 图片输出 196 tokens"],
        )
        response_payload = json.loads(node_result["result"][1])
        self.assertAlmostEqual(response_payload["cost_estimate"]["estimated_total_usd"], 0.01362)
        self.assertTrue(client.closed)

    def test_edit_node_uses_image_array_files(self):
        import torch

        client = FakeAsyncClient()
        images = torch.zeros((3, 8, 8, 3), dtype=torch.float32)

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageEditNode().generate(
                    "hello",
                    images=images,
                    model="gpt-image-1.5",
                    input_fidelity="high",
                )
            )

        data, files = client.edit_calls[0]
        self.assertEqual(data["model"], "gpt-image-1.5")
        self.assertEqual(data["input_fidelity"], "high")
        self.assertEqual(len(files), 3)
        self.assertTrue(all(item[0] == "image[]" for item in files))
        self.assertTrue(client.closed)

    def test_edit_node_resolves_auto_size_from_input_ratio(self):
        import torch

        client = FakeAsyncClient()
        images = torch.zeros((1, 1478, 833, 3), dtype=torch.float32)

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageEditNode().generate(
                    "hello",
                    images=images,
                    model="gpt-image-2",
                    size="auto",
                )
            )

        data, _files = client.edit_calls[0]
        self.assertEqual(data["size"], "864x1536")
        self.assertTrue(client.closed)

    def test_edit_node_resolves_2k_size_from_input_ratio(self):
        import torch

        client = FakeAsyncClient()
        images = torch.zeros((1, 1478, 833, 3), dtype=torch.float32)

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageEditNode().generate(
                    "hello",
                    images=images,
                    model="gpt-image-2",
                    size="2K",
                )
            )

        data, _files = client.edit_calls[0]
        self.assertEqual(data["size"], "1152x2048")
        self.assertTrue(client.closed)

    def test_edit_node_selected_ratio_overrides_input_ratio(self):
        import torch

        client = FakeAsyncClient()
        images = torch.zeros((1, 1478, 833, 3), dtype=torch.float32)

        with patch.object(nodes, "_create_runtime_async_client", return_value=client):
            asyncio.run(
                nodes.GPTImageEditNode().generate(
                    "hello",
                    images=images,
                    model="gpt-image-2",
                    size="2K",
                    aspect_ratio="1:1",
                )
            )

        data, _files = client.edit_calls[0]
        self.assertEqual(data["size"], "2048x2048")
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()

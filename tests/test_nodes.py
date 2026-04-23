import asyncio
import base64
import io
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
    def __init__(self):
        self.generate_calls = []
        self.edit_calls = []
        self.closed = False

    async def generate_image(self, payload):
        self.generate_calls.append(payload)
        image_count = int(payload.get("n", 1))
        return {
            "data": [
                {"b64_json": _make_base64_png((255, index, 0))}
                for index in range(image_count)
            ]
        }

    async def edit_image(self, data, files):
        self.edit_calls.append((data, files))
        image_count = int(data.get("n", 1))
        return {
            "data": [
                {"b64_json": _make_base64_png((0, index, 255))}
                for index in range(image_count)
            ]
        }

    async def close(self):
        self.closed = True


class NodeExecutionTests(unittest.TestCase):
    def test_generation_nodes_do_not_require_client_input(self):
        generate_inputs = nodes.GPTImageGenerateNode.INPUT_TYPES()
        edit_inputs = nodes.GPTImageEditNode.INPUT_TYPES()

        self.assertNotIn("client", generate_inputs["required"])
        self.assertNotIn("client", edit_inputs["required"])

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
        self.assertEqual(data["size"], "848x1504")
        self.assertTrue(client.closed)


if __name__ == "__main__":
    unittest.main()

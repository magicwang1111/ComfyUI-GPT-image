import base64
import io
import unittest

import PIL.Image

from _loader import import_module

import torch

image_generation = import_module("py.api.image_generation")


def _make_base64_png(color):
    image = PIL.Image.new("RGB", (4, 4), color=color)
    bytes_io = io.BytesIO()
    image.save(bytes_io, format="PNG")
    return base64.b64encode(bytes_io.getvalue()).decode("utf-8")


class ImageGenerationTests(unittest.TestCase):
    def test_build_generate_payload_includes_requested_options(self):
        payload = image_generation.build_generate_payload(
            model_name="gpt-image-2",
            prompt="hello",
            n=2,
            size="1024x1536",
            quality="high",
            background="transparent",
            output_format="webp",
        )

        self.assertEqual(payload["model"], "gpt-image-2")
        self.assertEqual(payload["prompt"], "hello")
        self.assertEqual(payload["n"], 2)
        self.assertEqual(payload["size"], "1024x1536")
        self.assertEqual(payload["quality"], "high")
        self.assertEqual(payload["background"], "transparent")
        self.assertEqual(payload["output_format"], "webp")

    def test_build_edit_request_uses_image_array_files(self):
        images = torch.zeros((2, 8, 8, 3), dtype=torch.float32)
        data, files = image_generation.build_edit_request(
            model_name="gpt-image-1.5",
            prompt="hello",
            images=images,
            input_fidelity="high",
        )

        self.assertEqual(data["model"], "gpt-image-1.5")
        self.assertEqual(data["prompt"], "hello")
        self.assertEqual(data["input_fidelity"], "high")
        self.assertEqual(len(files), 2)
        self.assertTrue(all(item[0] == "image[]" for item in files))
        self.assertTrue(all(item[1][0].endswith(".png") for item in files))

    def test_extract_generation_output_returns_image_batch(self):
        response_payload = {
            "data": [
                {"b64_json": _make_base64_png((255, 0, 0))},
                {"b64_json": _make_base64_png((0, 255, 0))},
            ]
        }

        output = image_generation.extract_generation_output(response_payload)
        self.assertEqual(tuple(output.shape), (2, 4, 4, 3))

    def test_sanitize_response_replaces_base64(self):
        payload = {
            "data": [
                {
                    "b64_json": "abc123",
                }
            ]
        }

        sanitized = image_generation.sanitize_response_for_debug(payload)
        self.assertIn("base64 omitted", sanitized["data"][0]["b64_json"])


if __name__ == "__main__":
    unittest.main()

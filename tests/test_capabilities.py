import unittest

from _loader import import_module

import torch

capabilities = import_module("py.api.capabilities")


class CapabilityTests(unittest.TestCase):
    def test_validate_generate_rejects_unknown_model(self):
        with self.assertRaises(ValueError):
            capabilities.validate_generate_request(
                "gpt-image-3",
                prompt="test",
            )

    def test_validate_edit_requires_images(self):
        with self.assertRaises(ValueError):
            capabilities.validate_edit_request(
                "gpt-image-2",
                prompt="test",
                images=None,
            )

    def test_validate_edit_accepts_large_reference_batch_without_local_limit(self):
        images = torch.zeros((17, 8, 8, 3), dtype=torch.float32)
        spec = capabilities.validate_edit_request(
            "gpt-image-1.5",
            prompt="test",
            images=images,
            input_fidelity="high",
        )
        self.assertEqual(spec["label"], "GPT Image 1.5")

    def test_validate_edit_rejects_invalid_input_fidelity(self):
        images = torch.zeros((1, 8, 8, 3), dtype=torch.float32)
        with self.assertRaises(ValueError):
            capabilities.validate_edit_request(
                "gpt-image-2",
                prompt="test",
                images=images,
                input_fidelity="auto",
            )

    def test_gpt_image_2_accepts_2k_preset(self):
        spec = capabilities.validate_generate_request(
            "gpt-image-2",
            prompt="test",
            size="2K",
        )
        self.assertEqual(spec["label"], "GPT Image 2")

    def test_gpt_image_15_rejects_2k_preset(self):
        with self.assertRaises(ValueError):
            capabilities.validate_generate_request(
                "gpt-image-1.5",
                prompt="test",
                size="2K",
            )

    def test_resolve_request_size_maps_gpt_image_15_auto_to_nearest_ratio(self):
        images = torch.zeros((1, 1478, 833, 3), dtype=torch.float32)
        size = capabilities.resolve_request_size("gpt-image-1.5", "auto", images=images)
        self.assertEqual(size, "1024x1536")

    def test_resolve_request_size_maps_gpt_image_2_auto_to_1k_preset_size(self):
        images = torch.zeros((1, 1478, 833, 3), dtype=torch.float32)
        size = capabilities.resolve_request_size("gpt-image-2", "auto", images=images)
        self.assertEqual(size, "1024x1536")

    def test_resolve_request_size_maps_gpt_image_2_2k_to_nearest_ratio(self):
        images = torch.zeros((1, 1478, 833, 3), dtype=torch.float32)
        size = capabilities.resolve_request_size("gpt-image-2", "2K", images=images)
        self.assertEqual(size, "1152x2048")

    def test_resolve_request_size_maps_gpt_image_2_4k_square_without_images(self):
        size = capabilities.resolve_request_size("gpt-image-2", "4K")
        self.assertEqual(size, "2880x2880")


if __name__ == "__main__":
    unittest.main()

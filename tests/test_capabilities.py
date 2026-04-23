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


if __name__ == "__main__":
    unittest.main()

import importlib
import importlib.util
import sys
import types
from pathlib import Path

import numpy

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "comfyui_gpt_image"


def _install_fake_torch():
    if "torch" in sys.modules:
        return

    try:
        import torch  # noqa: F401
        return
    except ImportError:
        pass

    fake_torch = types.ModuleType("torch")

    class FakeTensor:
        def __init__(self, array):
            self._array = numpy.array(array, dtype=numpy.float32, copy=False)

        @property
        def shape(self):
            return self._array.shape

        @property
        def ndim(self):
            return self._array.ndim

        def unsqueeze(self, axis):
            return FakeTensor(numpy.expand_dims(self._array, axis))

        def detach(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self._array

        def __iter__(self):
            return iter(self._array)

    def zeros(shape, dtype=None):
        return FakeTensor(numpy.zeros(shape, dtype=numpy.float32))

    def from_numpy(array):
        return FakeTensor(array)

    def stack(items):
        return FakeTensor(numpy.stack([item._array if isinstance(item, FakeTensor) else item for item in items]))

    fake_torch.Tensor = FakeTensor
    fake_torch.float32 = numpy.float32
    fake_torch.zeros = zeros
    fake_torch.from_numpy = from_numpy
    fake_torch.stack = stack
    sys.modules["torch"] = fake_torch


def ensure_package_loaded():
    _install_fake_torch()

    if PACKAGE_NAME in sys.modules:
        return sys.modules[PACKAGE_NAME]

    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


def import_module(module_name):
    ensure_package_loaded()
    return importlib.import_module(f"{PACKAGE_NAME}.{module_name}")


_install_fake_torch()

import sys
from unittest.mock import MagicMock


class DummyTensor:
    pass


# Mock out heavy ML libraries to allow running tests without them
mock_torch = MagicMock()
mock_torch.Tensor = DummyTensor
sys.modules["torch"] = mock_torch

sys.modules["transformers"] = MagicMock()
sys.modules["sentence_transformers"] = MagicMock()

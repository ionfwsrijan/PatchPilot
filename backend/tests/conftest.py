import pytest

@pytest.fixture(params=["asyncio"])
def anyio_backend():
    return "asyncio"

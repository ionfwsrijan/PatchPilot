import pytest

from app.main import app


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Start every test with an empty rate-limit counter."""
    app.state.limiter.reset()
    yield
    app.state.limiter.reset()

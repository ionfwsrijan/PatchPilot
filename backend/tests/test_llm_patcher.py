import pytest
from unittest.mock import patch, MagicMock
from app.ml.llm_patcher import generate_patch, OllamaUnavailableError, _extract_diff

@pytest.mark.asyncio
async def test_generate_patch_success():
    prompt = "Test prompt"
    expected_diff = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new"
    
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"response": expected_diff}

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        diff = await generate_patch(prompt)
        assert diff == expected_diff

@pytest.mark.asyncio
async def test_generate_patch_unavailable():
    prompt = "Test prompt"
    
    import httpx
    
    with patch("httpx.AsyncClient.post", side_effect=httpx.RequestError("Unavailable")):
        with pytest.raises(OllamaUnavailableError):
            await generate_patch(prompt)


def test_extract_diff_with_markdown():
    raw_response = "```diff\n--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new\n```"
    expected_diff = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new"
    
    diff = _extract_diff(raw_response)
    assert diff == expected_diff

def test_extract_diff_without_markdown():
    raw_response = "--- a/test.py\n+++ b/test.py\n@@ -1 +1 @@\n-old\n+new"
    expected_diff = raw_response
    
    diff = _extract_diff(raw_response)
    assert diff == expected_diff

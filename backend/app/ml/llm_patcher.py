import httpx
import logging
from app.config import OLLAMA_MODEL, OLLAMA_BASE_URL

logger = logging.getLogger(__name__)

class OllamaUnavailableError(Exception):
    pass

def _extract_diff(response_text: str) -> str:
    """
    Extracts unified diff from the raw LLM response.
    Sometimes models wrap the diff in markdown code blocks like ```diff ... ``` or just ``` ... ```
    """
    text = response_text.strip()
    
    # Check if the output is wrapped in a code block
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove the first line (e.g. ```diff)
        if len(lines) > 1:
            lines = lines[1:]
        # Remove the last line if it's ```
        if len(lines) > 0 and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    return text

async def generate_patch(prompt: str) -> str:
    """
    Calls Ollama to generate a patch.
    Raises OllamaUnavailableError if the service is unreachable.
    """
    url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            raw_output = data.get("response", "")
            return _extract_diff(raw_output)
    except httpx.RequestError as e:
        logger.error(f"Error connecting to Ollama: {e}")
        raise OllamaUnavailableError("Ollama service is unavailable.")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error from Ollama: {e}")
        raise OllamaUnavailableError("Ollama service returned an error.")

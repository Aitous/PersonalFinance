import json
from pathlib import Path
import anthropic
import google.generativeai as genai
from backend.credentials import credentials_store
from backend.llm.claude_provider import ClaudeProvider
from backend.llm.gemini_provider import GeminiProvider

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

def get_llm_provider():
    config = json.loads(CONFIG_PATH.read_text())
    provider_name = config.get("llm_provider", "claude")

    if provider_name == "claude":
        api_key = credentials_store.get_llm_key("claude")
        client = anthropic.Anthropic(api_key=api_key)
        return ClaudeProvider(client=client)

    if provider_name == "gemini":
        api_key = credentials_store.get_llm_key("gemini")
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        return GeminiProvider(model=model)

    raise ValueError(f"Unknown LLM provider: {provider_name}")

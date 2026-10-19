import json
from pathlib import Path
import anthropic
import google.generativeai as genai
from backend.credentials import credentials_store
from backend.llm.claude_provider import ClaudeProvider
from backend.llm.gemini_provider import GeminiProvider

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"
GEMINI_PRO_MODEL = "gemini-3.8-flash"


def get_llm_provider(provider_override: "str | None" = None, use_pro: bool = False):
    config = json.loads(CONFIG_PATH.read_text())
    provider_name = provider_override or config.get("llm_provider", "claude")

    if provider_name == "claude":
        api_key = credentials_store.get_llm_key("claude")
        client = anthropic.Anthropic(api_key=api_key)
        return ClaudeProvider(client=client)

    if provider_name == "gemini":
        api_key = credentials_store.get_llm_key("gemini")
        genai.configure(api_key=api_key)
        model_name = GEMINI_PRO_MODEL if use_pro else GEMINI_DEFAULT_MODEL
        model = genai.GenerativeModel(model_name)
        return GeminiProvider(model=model)

    raise ValueError(f"Unknown LLM provider: {provider_name}")

import json
import os
from pathlib import Path
import anthropic
import google.generativeai as genai
from openai import OpenAI
from backend.credentials import credentials_store
from backend.llm.claude_provider import ClaudeProvider
from backend.llm.gemini_provider import GeminiProvider
from backend.llm.openai_provider import OpenAIProvider
from backend.llm.metering import MeteredProvider
from backend.auth import hosted_auth_enabled

CONFIG_PATH = Path(__file__).parent.parent.parent / "config.json"

GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"
GEMINI_PRO_MODEL = "gemini-3.8-flash"


def get_llm_provider(provider_override: "str | None" = None, use_pro: bool = False):
    hosted = hosted_auth_enabled()
    if hosted:
        provider_name = os.environ["LLM_PROVIDER"].lower()
        keys = {"claude": "ANTHROPIC_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}
        api_key = os.getenv(keys.get(provider_name, ""), "")
    else:
        config = json.loads(CONFIG_PATH.read_text())
        provider_name = provider_override or config.get("llm_provider", "claude")
        api_key = credentials_store.get_llm_key(provider_name)

    if provider_name == "claude":
        if not api_key:
            raise ValueError("The managed Anthropic API key is not configured" if os.getenv("APP_ENV") in {"production", "staging"} else "Anthropic API key is not configured")
        client = anthropic.Anthropic(api_key=api_key)
        provider = ClaudeProvider(client=client)
        return MeteredProvider(provider, provider_name, provider.MODEL) if hosted else provider

    if provider_name == "gemini":
        if not api_key:
            raise ValueError("The managed Gemini API key is not configured" if os.getenv("APP_ENV") in {"production", "staging"} else "Gemini API key is not configured")
        genai.configure(api_key=api_key)
        model_name = GEMINI_PRO_MODEL if use_pro else GEMINI_DEFAULT_MODEL
        model = genai.GenerativeModel(model_name)
        return MeteredProvider(GeminiProvider(model=model), provider_name, model_name) if hosted else GeminiProvider(model=model)

    if provider_name == "openai":
        if not api_key:
            raise ValueError("OpenAI API key is not configured")
        provider = OpenAIProvider(client=OpenAI(api_key=api_key))
        return MeteredProvider(provider, provider_name, provider.MODEL) if hosted else provider

    raise ValueError(f"Unknown LLM provider: {provider_name}")

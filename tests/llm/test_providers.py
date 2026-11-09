import pytest
from unittest.mock import MagicMock, patch
from backend.llm.claude_provider import ClaudeProvider
from backend.llm.gemini_provider import GeminiProvider
from backend.llm.openai_provider import OpenAIProvider
from backend.llm.factory import get_llm_provider

def test_claude_provider_calls_api():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text="groceries")]
    )
    provider = ClaudeProvider(client=mock_client)
    result = provider.complete("Categorize: WHOLE FOODS $84")
    assert result == "groceries"
    mock_client.messages.create.assert_called_once()

def test_gemini_provider_calls_api():
    mock_model = MagicMock()
    mock_model.generate_content.return_value = MagicMock(text="dining")
    provider = GeminiProvider(model=mock_model)
    result = provider.complete("Categorize: UBER EATS $32")
    assert result == "dining"

def test_openai_provider_calls_api():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="transportation"))]
    )
    provider = OpenAIProvider(client=mock_client)
    assert provider.complete("Categorize: UBER $32") == "transportation"
    mock_client.chat.completions.create.assert_called_once_with(
        model="gpt-6-luna", messages=[{"role": "user", "content": "Categorize: UBER $32"}]
    )

def test_openai_provider_preserves_top_level_json_arrays():
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content='["transportation"]'))]
    )
    provider = OpenAIProvider(client=mock_client)
    assert provider.complete_json("Return an array of categories") == '["transportation"]'
    assert mock_client.chat.completions.create.call_args.kwargs == {
        "model": "gpt-6-luna",
        "messages": [{"role": "user", "content": "Return an array of categories"}],
    }

def test_factory_returns_claude(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "claude"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store") as mock_creds, \
         patch("backend.llm.factory.anthropic.Anthropic") as mock_anthropic:
        mock_creds.get_llm_key.return_value = "sk-ant-test"
        provider = get_llm_provider()
        assert isinstance(provider, ClaudeProvider)

def test_factory_raises_for_unknown_provider(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "not-a-provider"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store"):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            get_llm_provider()

def test_factory_returns_gemini(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "gemini"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store") as mock_creds, \
         patch("backend.llm.factory.genai.GenerativeModel") as mock_genai, \
         patch("backend.llm.factory.genai.configure"):
        mock_creds.get_llm_key.return_value = "AIza-test"
        provider = get_llm_provider()
        assert isinstance(provider, GeminiProvider)

def test_factory_returns_openai(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "openai"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store") as mock_creds, \
         patch("backend.llm.factory.OpenAI") as mock_openai:
        mock_creds.get_llm_key.return_value = "sk-test"
        provider = get_llm_provider()
        assert isinstance(provider, OpenAIProvider)
        mock_openai.assert_called_once_with(api_key="sk-test")

def test_factory_openai_without_key_does_not_create_client(tmp_path):
    config = tmp_path / "config.json"
    config.write_text('{"llm_provider": "openai"}')
    with patch("backend.llm.factory.CONFIG_PATH", config), \
         patch("backend.llm.factory.credentials_store") as mock_creds, \
         patch("backend.llm.factory.OpenAI") as mock_openai:
        mock_creds.get_llm_key.return_value = None
        with pytest.raises(ValueError, match="OpenAI API key is not configured"):
            get_llm_provider()
        mock_openai.assert_not_called()

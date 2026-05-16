import pytest

from app.config import settings
from app.services.llm import chat_model_id, embed_model_id


@pytest.fixture
def clear_openai(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "openai_api_base", None)
    monkeypatch.setattr(settings, "chat_provider", "auto")
    monkeypatch.setattr(settings, "embed_provider", "auto")


def test_auto_without_openai_uses_ollama(clear_openai):
    assert settings.resolved_chat_provider() == "ollama"
    assert settings.resolved_embed_provider() == "ollama"
    assert chat_model_id().startswith("ollama:")
    assert embed_model_id().startswith("ollama:")


def test_auto_with_openai_uses_openai(monkeypatch, clear_openai):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.example/v1")
    assert settings.resolved_chat_provider() == "openai"
    assert settings.resolved_embed_provider() == "openai"


def test_mixed_chat_ollama_embed_openai(monkeypatch, clear_openai):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.example/v1")
    monkeypatch.setattr(settings, "chat_provider", "ollama")
    monkeypatch.setattr(settings, "embed_provider", "openai")
    assert settings.resolved_chat_provider() == "ollama"
    assert settings.resolved_embed_provider() == "openai"
    assert chat_model_id().startswith("ollama:")
    assert embed_model_id() == f"openai:{settings.openai_embed_model}"


def test_mixed_chat_openai_embed_ollama(monkeypatch, clear_openai):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.example/v1")
    monkeypatch.setattr(settings, "chat_provider", "openai")
    monkeypatch.setattr(settings, "embed_provider", "ollama")
    assert settings.resolved_chat_provider() == "openai"
    assert settings.resolved_embed_provider() == "ollama"
    assert chat_model_id().startswith("openai:")
    assert embed_model_id().startswith("ollama:")


def test_openai_embed_model_override(monkeypatch, clear_openai):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "openai_api_base", "https://api.example/v1")
    monkeypatch.setattr(settings, "embed_provider", "openai")
    monkeypatch.setattr(settings, "openai_embed_model", "text-embedding-3-large")
    assert embed_model_id() == "openai:text-embedding-3-large"


def test_invalid_provider_rejected():
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="chat_provider"):
        Settings.model_validate({"CHAT_PROVIDER": "azure"})

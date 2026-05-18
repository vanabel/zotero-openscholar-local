"""OpenScholar Transformers 对话（配置，不加载权重）。"""

from app.config import _hf_chat_model_from_ollama_tag, is_usable_hf_model_dir, settings


def test_config_openscholar_chat_model_default():
    s = settings.effective_openscholar_chat_model()
    assert "OpenScholar" in s or "openscholar" in s.lower()


def test_hf_from_ollama_openscholar_gguf_tag():
    assert _hf_chat_model_from_ollama_tag(
        "hf.co/QuantFactory/Llama-3.1_OpenScholar-8B-GGUF:Q4_K_M"
    ) == "OpenSciLM/Llama-3.1_OpenScholar-8B"
    assert _hf_chat_model_from_ollama_tag("qwen2.5:7b") is None


def test_is_usable_hf_model_dir_requires_weights(tmp_path):
    d = tmp_path / "m"
    d.mkdir()
    (d / "config.json").write_text("{}")
    assert not is_usable_hf_model_dir(d)
    (d / "model.safetensors").write_bytes(b"x")
    assert is_usable_hf_model_dir(d)

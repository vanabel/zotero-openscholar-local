from __future__ import annotations

import logging

from app.pipeline_logging import _format_log_ctx, log_context, setup_logging


def test_log_context_prefix(monkeypatch):
    monkeypatch.setattr("app.pipeline_logging.settings.log_context", True)
    with log_context(task_id="e402cd5989ab42b6a1f7ee4807dc064a", paper_id="51e99e0a4272149f5421d5f233bf3d23"):
        assert "task=e402cd59" in _format_log_ctx()
        assert "paper=51e99e0a" in _format_log_ctx()


def test_log_context_disabled(monkeypatch):
    monkeypatch.setattr("app.pipeline_logging.settings.log_context", False)
    with log_context(paper_id="51e99e0a4272149f5421d5f233bf3d23"):
        assert _format_log_ctx() == ""


def test_setup_logging_injects_ctx(monkeypatch, caplog):
    monkeypatch.setattr("app.pipeline_logging.settings.log_context", True)
    setup_logging()
    caplog.set_level(logging.INFO)
    with log_context(paper_id="abcdef0123456789"):
        logging.getLogger("app.pipeline.index").info("BGE 嵌入开始")
    assert "paper=abcdef01" in caplog.text
    assert "BGE 嵌入开始" in caplog.text

from app.services.task_kind import task_kind, task_kind_label


def test_task_kind_parse_only():
    assert task_kind(task_type="index", payload={"parse_only": True}) == "parse"
    assert task_kind_label("parse") == "仅解析"


def test_task_kind_reindex():
    assert task_kind(task_type="index", payload={"reindex_only": True}) == "reindex"


def test_task_kind_default_index():
    assert task_kind(task_type="index", payload={}) == "index"

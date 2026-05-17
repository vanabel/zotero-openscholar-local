from __future__ import annotations

import json
import re
from pathlib import Path

from app.config import settings
from app.pipeline_logging import plog_info

_RULES_CACHE: dict[str, list[str]] | None = None


def _rules_path() -> Path | None:
    raw = (settings.retrieve_query_synonyms_path or "").strip()
    if raw:
        return Path(raw).expanduser()
    default = settings.data_dir / "query_synonyms.json"
    return default if default.is_file() else None


def load_synonym_rules(*, reload: bool = False) -> dict[str, list[str]]:
    global _RULES_CACHE
    if _RULES_CACHE is not None and not reload:
        return _RULES_CACHE

    path = _rules_path()
    rules: dict[str, list[str]] = {}
    if path and path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k, v in raw.items():
                    key = str(k).strip().lower()
                    if not key:
                        continue
                    if isinstance(v, str):
                        alts = [v.strip()]
                    elif isinstance(v, list):
                        alts = [str(x).strip() for x in v if str(x).strip()]
                    else:
                        continue
                    rules[key] = [a for a in alts if a and a.lower() != key]
        except (OSError, json.JSONDecodeError) as e:
            plog_info("retrieve", "query_synonyms 加载失败 path=%s err=%s", path, e)

    _RULES_CACHE = rules
    return rules


def expand_query_with_synonyms(
    query: str,
    rules: dict[str, list[str]] | None = None,
    *,
    force: bool = False,
) -> list[str]:
    """规则同义词扩展：返回除原问句外的额外检索串（去重、保序）。"""
    if not force and not settings.retrieve_query_synonyms_enabled:
        return []
    q = (query or "").strip()
    if not q:
        return []
    rules = rules if rules is not None else load_synonym_rules()
    if not rules:
        return []

    q_lower = q.lower()
    extras: list[str] = []
    seen = {q}

    def add_variant(s: str) -> None:
        t = s.strip()
        if not t or t in seen:
            return
        seen.add(t)
        extras.append(t)

    for term, alts in rules.items():
        if not term or not alts:
            continue
        if re.search(rf"(?<![\w\u4e00-\u9fff]){re.escape(term)}(?![\w\u4e00-\u9fff])", q_lower):
            for alt in alts:
                variant = re.sub(
                    rf"(?i)(?<![\w\u4e00-\u9fff]){re.escape(term)}(?![\w\u4e00-\u9fff])",
                    alt,
                    q,
                    count=1,
                )
                add_variant(variant)
            continue
        for alt in alts:
            alt_l = alt.lower()
            if re.search(rf"(?<![\w\u4e00-\u9fff]){re.escape(alt_l)}(?![\w\u4e00-\u9fff])", q_lower):
                variant = re.sub(
                    rf"(?i)(?<![\w\u4e00-\u9fff]){re.escape(alt)}(?![\w\u4e00-\u9fff])",
                    term,
                    q,
                    count=1,
                )
                add_variant(variant)

    return extras[: settings.retrieve_query_synonyms_max_variants]
